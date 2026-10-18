"""Web pages by URL: the article is extracted and laid out as a PDF, so it reads like any document."""
import io
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from clanki.web import WebError, page_to_pdf
from fake_anki import FakeAnki
from make_pdf import make_pdf

PNG = (Path(__file__).parent / "fixtures" / "raas.png").read_bytes()
ARTICLE = """<!doctype html><html><head><title>The Median Nerve - Course - TeachMe</title></head><body>
<nav><a href="/">Home</a> <a href="/upper-limb">Upper limb</a> Cookie settings</nav>
<article>
<h1>The Median Nerve</h1>
<p>The median nerve arises from the lateral and medial cords of the brachial plexus. It carries fibres from
C5 to T1 and supplies most of the flexors of the forearm.<sup class="reference">[1]</sup></p>
<h2>Anatomical course</h2>
<p>It enters the hand through the carpal tunnel, deep to the flexor retinaculum, where compression causes
carpal tunnel syndrome. Na⁺ and K⁺ channels are not relevant here, but the symbols must survive.</p>
<figure><img src="/img/course.png" alt="Course of the median nerve"><figcaption>Fig 1. The course of the median nerve.</figcaption></figure>
<h2>Motor functions</h2>
<ul><li>Flexor digitorum superficialis</li><li>Pronator teres and pronator quadratus</li><li>Thenar muscles (LOAF)
<figure><img src="/img/thenar.png" alt=""><figcaption>Fig 2. Thenar muscles.</figcaption></figure></li></ul>
<table><tr><th>Branch</th><th>Supplies</th></tr><tr><td>Anterior interosseous</td><td>Deep flexors</td></tr></table>
<p>The palmar cutaneous branch arises proximal to the carpal tunnel, so sensation over the thenar eminence is spared.</p>
</article>
<footer>Copyright TeachMe Series. Privacy policy.</footer></body></html>"""


def transport(routes):
    def handle(request):
        status, ctype, body = routes.get(str(request.url), (404, "text/plain", b"not found"))
        return httpx.Response(status, headers={"content-type": ctype}, content=body)
    return httpx.Client(transport=httpx.MockTransport(handle))


SITE = {"https://anatomy.example/median": (200, "text/html; charset=utf-8", ARTICLE.encode()),
        "https://anatomy.example/img/course.png": (200, "image/png", PNG),
        "https://anatomy.example/img/thenar.png": (200, "image/png", PNG)}


def text_of(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def test_an_article_becomes_a_pdf_with_its_text_and_figures():
    title, pdf = page_to_pdf("https://anatomy.example/median", transport(SITE))
    assert title == "The Median Nerve"
    text = text_of(pdf)
    for s in ("The Median Nerve", "Anatomical course", "carpal tunnel syndrome", "Na⁺ and K⁺",
              "• Flexor digitorum superficialis", "Branch | Supplies", "Anterior interosseous | Deep flexors",
              "Fig 1. The course of the median nerve.", "Source: https://anatomy.example/median"):
        assert s in text, s
    assert "Cookie settings" not in text and "Privacy policy" not in text and "[1]" not in text
    assert sum(len(p.images) for p in PdfReader(io.BytesIO(pdf)).pages) == 2  # one was inside a list item


def test_a_missing_image_is_left_out():
    title, pdf = page_to_pdf("https://anatomy.example/median", transport({**SITE, "https://anatomy.example/img/course.png": (404, "text/plain", b"")}))
    assert "carpal tunnel syndrome" in text_of(pdf)


def test_a_link_to_a_pdf_opens_that_pdf():
    doc = make_pdf([["Guideline text"]])
    title, pdf = page_to_pdf("https://nice.example/ng136.pdf", transport({"https://nice.example/ng136.pdf": (200, "application/pdf", doc)}))
    assert (title, pdf) == ("ng136", doc)


@pytest.mark.parametrize("url, routes, message", [
    ("ftp://x.example/a", {}, "http"),
    ("https://anatomy.example/median", {"https://anatomy.example/median": (403, "text/html", b"blocked")}, "Save as PDF"),
    ("https://anatomy.example/median", {"https://anatomy.example/median": (200, "image/png", PNG)}, "not a web page"),
    ("https://anatomy.example/median", {"https://anatomy.example/median": (200, "text/html", b"<html><body><nav>Menu</nav></body></html>")}, "No article"),
])
def test_pages_that_cannot_be_opened_say_why(url, routes, message):
    with pytest.raises(WebError, match=message):
        page_to_pdf(url, transport(routes))


@pytest.fixture
def client(tmp_path):
    app = create_app(Config(data_dir=tmp_path / "d"), anki=AnkiConnect(transport=FakeAnki().transport()),
                     web_client=transport(SITE))
    return TestClient(app)


def test_open_a_web_page_as_a_document(client):
    r = client.post("/api/documents/url", json={"url": "https://anatomy.example/median"})
    assert r.status_code == 200, r.text
    doc = r.json()
    assert (doc["title"], doc["kind"], doc["filename"]) == ("The Median Nerve", "web", "https://anatomy.example/median")
    assert "carpal tunnel syndrome" in text_of(client.get("/api/documents/%s/pdf" % doc["id"]).content)


def test_a_page_that_cannot_be_opened_is_a_422(client):
    r = client.post("/api/documents/url", json={"url": "https://anatomy.example/elsewhere"})
    assert r.status_code == 422 and "404" in r.json()["detail"]


PAPER_PDF = make_pdf([["Attention Is All You Need"], ["The Transformer relies entirely on attention."]])
ABS = b"""<html><head><title>[1706.03762] Attention Is All You Need</title>
<meta name="citation_title" content="Attention Is All You Need">
<meta name="citation_pdf_url" content="https://arxiv.org/pdf/1706.03762v7"></head>
<body><h1>Attention Is All You Need</h1><blockquote>Abstract: The dominant sequence transduction models...</blockquote></body></html>"""
ARXIV = {"https://arxiv.org/abs/1706.03762": (200, "text/html", ABS),
         "https://arxiv.org/abs/1706.03762v7": (200, "text/html", ABS),
         "https://arxiv.org/pdf/1706.03762v7": (200, "application/pdf", PAPER_PDF)}


@pytest.mark.parametrize("url", ["https://arxiv.org/abs/1706.03762", "https://arxiv.org/pdf/1706.03762v7",
                                 "https://arxiv.org/html/1706.03762v7"])
def test_an_arxiv_link_opens_the_paper_pdf_with_its_title(url):
    assert page_to_pdf(url, transport(ARXIV)) == ("Attention Is All You Need", PAPER_PDF)


def test_any_paper_landing_page_with_a_citation_pdf_opens_the_pdf():
    landing = b"""<html><head><meta name="citation_title" content="Protein structure from sequence">
    <meta name="citation_pdf_url" content="/content/10.1101/2024.01.01.123456v1.full.pdf"></head><body>Abstract</body></html>"""
    routes = {"https://www.biorxiv.org/content/10.1101/2024.01.01.123456v1": (200, "text/html", landing),
              "https://www.biorxiv.org/content/10.1101/2024.01.01.123456v1.full.pdf": (200, "application/pdf", PAPER_PDF)}
    assert page_to_pdf("https://www.biorxiv.org/content/10.1101/2024.01.01.123456v1", transport(routes)) == (
        "Protein structure from sequence", PAPER_PDF)


def test_a_paper_whose_pdf_is_refused_says_to_download_it():
    landing = b"""<html><head><meta name="citation_title" content="Paywalled">
    <meta name="citation_pdf_url" content="https://journal.example/paper.pdf"></head><body>Abstract</body></html>"""
    routes = {"https://journal.example/paper": (200, "text/html", landing),
              "https://journal.example/paper.pdf": (403, "text/html", b"denied")}
    with pytest.raises(WebError, match="download the PDF"):
        page_to_pdf("https://journal.example/paper", transport(routes))
