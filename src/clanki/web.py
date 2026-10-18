"""Web pages by URL: fetch the page, keep the article (readability), and lay it out as a PDF with its
figures, so the reader, highlights and figure transcription work as for any document."""
import io
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from fpdf import FPDF
from lxml import html as lhtml
from PIL import Image
from readability import Document as Readable

FONTS = Path(__file__).parent / "fonts"
# Sites such as Wikipedia refuse anonymous clients; identify clanki as their policies ask.
USER_AGENT = "clanki/0.1 (https://github.com/cache999/clanki; personal study tool)"
BROWSER_HINT = "save the page from your browser instead (Ctrl+P, Save as PDF) and open that file"
MAX_IMAGES = 30
MAX_IMAGE_BYTES = 8_000_000
MIN_IMAGE_PX = 80  # smaller ones are icons
MIN_ARTICLE_CHARS = 200
MAX_FIGURE_MM = 140

_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 4, "h6": 4}
_SKIP = {"script", "style", "noscript", "nav", "footer", "form", "button", "svg", "iframe"}
_BLOCKS = set(_HEADINGS) | {"p", "ul", "ol", "table", "img", "figure", "div", "section", "article", "blockquote",
                            "pre", "dl", "figcaption", "header", "main", "aside"}
_CITATION = re.compile(r"\[\d+(?:[–-]\d+)?\]")


class WebError(Exception):
    pass


def page_to_pdf(url: str, client: httpx.Client) -> tuple[str, bytes]:
    """The page's title and a PDF of its article. A link to a PDF gives that PDF."""
    if urlparse(url).scheme not in ("http", "https"):
        raise WebError("Give a web address starting with http:// or https://")
    try:
        r = client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20)
    except httpx.HTTPError as e:
        raise WebError("Could not reach %s (%s)" % (urlparse(url).netloc, e)) from e
    if r.status_code != 200:
        raise WebError("The site answered %d: it may block apps like clanki or need a login, so %s"
                       % (r.status_code, BROWSER_HINT))
    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype == "application/pdf" or r.content.startswith(b"%PDF"):
        return Path(urlparse(str(r.url)).path).stem or "document", r.content
    if ctype not in ("text/html", "application/xhtml+xml"):
        raise WebError("%s is not a web page (%s)" % (url, ctype or "unknown type"))
    title = _title(r.text) or Readable(r.text).short_title()
    article = lhtml.fromstring(Readable(r.text, url=str(r.url)).summary(html_partial=True))
    blocks = list(_blocks(article, str(r.url)))
    if blocks and blocks[0] == ("h", 1, title):
        blocks = blocks[1:]
    if sum(len(b[-1]) for b in blocks if b[0] != "img") < MIN_ARTICLE_CHARS:
        raise WebError("No article text found on the page (it may need JavaScript or a login): " + BROWSER_HINT)
    return title, _render(title, str(r.url), blocks, client)


def _title(page: str) -> str:
    h1 = lhtml.fromstring(page).xpath("//h1")
    t = " ".join(h1[0].text_content().split()) if h1 else ""
    return t if 0 < len(t) <= 150 else ""


def _text(el) -> str:
    for br in el.iter("br"):
        br.tail = "\n" + (br.tail or "")
    for junk in el.xpath('.//sup[contains(@class, "reference")] | .//*[contains(@class, "mw-editsection")]'):
        junk.drop_tree()
    s = _CITATION.sub("", el.text_content()).replace("­", "").replace("​", "")
    return "\n".join(" ".join(line.split()) for line in s.split("\n") if line.strip())


def _blocks(el, base: str):
    """("h", level, text), ("p" | "li" | "row" | "cap", text) and ("img", url), in reading order."""
    for child in el.iterchildren():
        tag = child.tag if isinstance(child.tag, str) else ""
        if tag in _SKIP:
            continue
        if tag in _HEADINGS:
            if t := _text(child):
                yield ("h", _HEADINGS[tag], t)
        elif tag in ("ul", "ol"):
            for i, li in enumerate(child.findall("li"), 1):
                if t := _text(li):
                    yield ("li", ("%d. " % i if tag == "ol" else "• ") + t)
                yield from _images(li, base)
        elif tag == "table":
            for tr in child.iter("tr"):
                cells = [_text(c) for c in tr if c.tag in ("td", "th")]
                if any(cells):
                    yield ("row", " | ".join(cells))
        elif tag == "img":
            yield from _images(child, base)
        elif tag in ("figcaption", "caption"):
            if t := _text(child):
                yield ("cap", t)
        elif tag in ("p", "blockquote", "pre", "dt", "dd") or not any(
                d.tag in _BLOCKS for d in child.iterdescendants() if isinstance(d.tag, str)):
            if t := _text(child):
                yield ("p", t)
            yield from _images(child, base)
        else:  # a container of blocks
            if child.text and child.text.strip():
                yield ("p", " ".join(child.text.split()))
            yield from _blocks(child, base)


def _images(el, base: str):
    """The images at or inside el (text blocks keep only their text, so their figures come here)."""
    for img in ([el] if el.tag == "img" else el.iter("img")):
        src = img.get("src") or img.get("data-src") or (img.get("srcset") or "").split(" ")[0]
        if src and not src.startswith("data:"):
            yield ("img", urljoin(base, src))


def _image(client: httpx.Client, url: str) -> Image.Image | None:
    try:
        r = client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=15)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or not ctype.startswith("image/") or "svg" in ctype or len(r.content) > MAX_IMAGE_BYTES:
            return None
        im = Image.open(io.BytesIO(r.content))
        im.load()
    except Exception:  # a figure that will not load is left out
        return None
    if min(im.size) < MIN_IMAGE_PX:
        return None
    return im.convert("RGBA") if im.mode in ("P", "LA") else im.convert("RGB") if im.mode not in ("RGB", "RGBA", "L") else im


def _render(title: str, url: str, blocks: list[tuple], client: httpx.Client) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_font("DejaVu", "", FONTS / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", FONTS / "DejaVuSans-Bold.ttf")
    pdf.set_title(title)
    pdf.add_page()

    def para(text: str, size: float = 11, style: str = "", indent: float = 0, gap: float = 2):
        pdf.set_font("DejaVu", style, size)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(pdf.epw - indent, size * 0.5, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    para(title, 18, "B")
    para("Source: %s (%s)" % (url, date.today().isoformat()), 8.5, gap=5)
    seen = set()
    for kind, *rest in blocks:
        if kind == "h":
            level, text = rest
            pdf.ln(2)
            para(text, {1: 16, 2: 14, 3: 12.5}.get(level, 11.5), "B", gap=1.5)
        elif kind == "p":
            para(rest[0])
        elif kind == "li":
            para(rest[0], indent=4, gap=1)
        elif kind == "row":
            para(rest[0], 9.5, gap=0.5)
        elif kind == "cap":
            para(rest[0], 9, gap=4)
        elif kind == "img" and rest[0] not in seen and len(seen) < MAX_IMAGES:
            seen.add(rest[0])
            im = _image(client, rest[0])
            if im is None:
                continue
            w = min(pdf.epw, im.width * 25.4 / 96)
            h = w * im.height / im.width
            if h > MAX_FIGURE_MM:
                w, h = w * MAX_FIGURE_MM / h, MAX_FIGURE_MM
            if pdf.get_y() + h > pdf.page_break_trigger:
                pdf.add_page()
            pdf.image(im, x=pdf.l_margin + (pdf.epw - w) / 2, y=pdf.get_y(), w=w, h=h)
            pdf.set_y(pdf.get_y() + h + 2)
    return bytes(pdf.output())
