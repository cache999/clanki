import pytest
from fastapi.testclient import TestClient

from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config

from fake_anki import FakeAnki

PDF = b"%PDF-1.4\n%fake\n"


@pytest.fixture
def anki():
    return FakeAnki()


@pytest.fixture
def client(tmp_path, anki):
    cfg = Config(data_dir=tmp_path / "data", default_deck="Default")
    return TestClient(create_app(cfg, anki=AnkiConnect(transport=anki.transport())))


@pytest.fixture
def doc(client):
    r = client.post("/api/documents", files={"file": ("vision.pdf", PDF, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def add_qa(client, doc, **kw):
    body = {"type": "qa", "front": "F", "back": "B", **kw}
    r = client.post("/api/documents/%s/notes" % doc["id"], json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_pdf_and_fetch_it_back(client, doc):
    assert (doc["title"], doc["kind"]) == ("vision", "pdf")
    assert client.get("/api/documents").json() == [doc]
    r = client.get("/api/documents/%s/pdf" % doc["id"])
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"


def test_unsupported_upload_is_rejected(client):
    r = client.post("/api/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_office_upload_is_converted(client, monkeypatch):
    from clanki import app as app_mod

    def fake_to_pdf(src, out_dir, soffice):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / (src.stem + ".pdf")).write_bytes(PDF)
        return out_dir / (src.stem + ".pdf")

    monkeypatch.setattr(app_mod.convert, "to_pdf", fake_to_pdf)
    r = client.post("/api/documents", files={"file": ("vision slides.pptx", b"PK", "application/zip")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["title"], d["kind"]) == ("vision slides", "pptx")
    assert client.get("/api/documents/%s/pdf" % d["id"]).content == PDF


def test_failed_conversion_reports_why(client, monkeypatch):
    from clanki import app as app_mod

    def boom(src, out_dir, soffice):
        raise app_mod.convert.ConversionError("LibreOffice is needed")

    monkeypatch.setattr(app_mod.convert, "to_pdf", boom)
    r = client.post("/api/documents", files={"file": ("a.docx", b"PK", "application/zip")})
    assert r.status_code == 422 and "LibreOffice" in r.json()["detail"]
    assert client.get("/api/documents").json() == []


def test_update_and_delete_document(client, doc):
    r = client.patch("/api/documents/%s" % doc["id"], json={"deck": "MVST1B::vision", "tags": ["NHB"]})
    assert r.json()["deck"] == "MVST1B::vision"
    assert client.patch("/api/documents/%s" % doc["id"], json={"kind": "x"}).status_code == 422
    assert client.delete("/api/documents/%s" % doc["id"]).status_code == 200
    assert client.get("/api/documents/%s" % doc["id"]).status_code == 404


def test_notes_crud_with_issues(client, doc):
    n = add_qa(client, doc, add_reverse=True)
    listed = client.get("/api/documents/%s/notes" % doc["id"]).json()
    assert [x["id"] for x in listed] == [n["id"]]
    assert [i["code"] for i in listed[0]["issues"]] == ["reverse_prompt_missing"]
    r = client.patch("/api/notes/%s" % n["id"], json={"reverse_prompt": "what?"})
    assert r.json()["reverse_prompt"] == "what?"
    assert client.get("/api/documents/%s/notes" % doc["id"]).json()[0]["issues"] == []


def test_note_patch_rejects_bookkeeping_fields(client, doc):
    n = add_qa(client, doc)
    assert client.patch("/api/notes/%s" % n["id"], json={"status": "sent"}).status_code == 422


def test_delete_and_undo(client, doc):
    n = add_qa(client, doc)
    client.delete("/api/notes/%s" % n["id"])
    assert client.get("/api/documents/%s/notes" % doc["id"]).json() == []
    client.post("/api/notes/%s/restore" % n["id"])
    assert len(client.get("/api/documents/%s/notes" % doc["id"]).json()) == 1


def test_sources(client, doc):
    body = {"page": 3, "text": "rods", "rects": [[0.1, 0.2, 0.3, 0.02]]}
    s = client.post("/api/documents/%s/sources" % doc["id"], json=body).json()
    assert s["id"] and s["document_id"] == doc["id"]
    assert client.get("/api/documents/%s/sources" % doc["id"]).json() == [s]


def test_export_merges_document_deck_and_tags(client, doc):
    client.patch("/api/documents/%s" % doc["id"], json={"deck": "MVST1B::vision", "tags": ["NHB::vision"]})
    add_qa(client, doc, tags=["kind::fact"])
    r = client.get("/api/documents/%s/export.txt" % doc["id"])
    assert r.status_code == 200
    assert 'filename="vision_anki.txt"' in r.headers["content-disposition"]
    row = r.text.splitlines()[-1].split("\t")
    assert row[1:4] == ["Basic (optional reversed card)", "MVST1B::vision", "NHB::vision kind::fact"]


def test_send_adds_then_updates_and_skips_cards_with_errors(client, doc, anki):
    good = add_qa(client, doc, front="Capital of France", back="Paris")
    bad = add_qa(client, doc, front="", back="x")
    r = client.post("/api/documents/%s/send" % doc["id"]).json()
    by_id = {x["note_id"]: x for x in r["results"]}
    assert by_id[good["id"]]["action"] == "added"
    assert by_id[bad["id"]]["action"] == "failed" and "Front is empty" in by_id[bad["id"]]["error"]
    assert len(anki.notes) == 1
    notes = {n["id"]: n for n in client.get("/api/documents/%s/notes" % doc["id"]).json()}
    assert notes[good["id"]]["status"] == "sent"

    client.patch("/api/notes/%s" % good["id"], json={"back": "Paris (Île-de-France)"})
    r = client.post("/api/documents/%s/send" % doc["id"]).json()
    assert {x["note_id"]: x["action"] for x in r["results"]}[good["id"]] == "updated"
    [anki_note] = anki.notes.values()
    assert anki_note["fields"]["Back"] == "Paris (Île-de-France)"
    assert client.get("/api/notes/%s" % good["id"]).json()["status"] == "sent"


def test_anki_status_endpoint(client):
    st = client.get("/api/anki/status").json()
    assert (st["connected"], st["version"], st["problems"], st["index"]["notes"]) == (True, 6, [], 0)


def test_unknown_document_404s(client):
    assert client.get("/api/documents/nope/notes").status_code == 404
    assert client.post("/api/documents/nope/notes", json={"type": "qa"}).status_code == 404
