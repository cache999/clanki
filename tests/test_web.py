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
