"""Export filters, and the exported status that keeps Send from adding imported cards again."""
import pytest
from fastapi.testclient import TestClient

from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from fake_anki import FakeAnki
from make_pdf import make_pdf


@pytest.fixture
def anki():
    return FakeAnki()


@pytest.fixture
def client(tmp_path, anki):
    return TestClient(create_app(Config(data_dir=tmp_path / "d"), anki=AnkiConnect(transport=anki.transport())))


def new_doc(client, name="vision"):
    return client.post("/api/documents", files={"file": (name + ".pdf", make_pdf([["x"]]), "application/pdf")}).json()


@pytest.fixture
def doc(client):
    return new_doc(client)


def add(client, doc, **kw):
    body = {"type": "qa", "front": "F%d" % len(kw), "back": "B", **kw}
    return client.post("/api/documents/%s/notes" % doc["id"], json=body).json()


def export(client, docs, **kw):
    body = {"document_ids": [d["id"] for d in docs], "scope": "unsent", "types": ["qa", "list"], "tag": "",
            "mark_exported": True, **kw}
    return client.post("/api/export", json=body)


def preview(client, docs, **kw):
    return client.post("/api/export", json={"document_ids": [d["id"] for d in docs], "preview": True, **kw}).json()


def fronts(r):
    return [line.split("\t")[4] for line in r.text.splitlines() if not line.startswith("#")]


def notes(client, doc):
    return {n["front"] or n["title"]: n for n in client.get("/api/documents/%s/notes" % doc["id"]).json()}


def test_unsent_export_marks_cards_exported_and_send_then_skips_them(client, doc, anki):
    add(client, doc, front="Capital of France", back="Paris")
    r = export(client, [doc])
    assert r.status_code == 200 and fronts(r) == ["Capital of France"]
    assert 'filename="vision_anki.txt"' in r.headers["content-disposition"] and r.headers["x-clanki-cards"] == "1"
    n = notes(client, doc)["Capital of France"]
    assert n["status"] == "exported" and n["exported_at"]
    s = client.post("/api/documents/%s/send" % doc["id"]).json()
    assert s["summary"]["skipped"] == 1 and anki.notes == {}
    assert fronts(export(client, [doc])) == []  # already exported


def test_an_edited_exported_card_is_exported_again_not_sent(client, doc, anki):
    n = add(client, doc, front="Capital of France", back="Paris")
    export(client, [doc])
    client.patch("/api/notes/%s" % n["id"], json={"back": "Paris (Île-de-France)"})
    assert notes(client, doc)["Capital of France"]["status"] == "edited"
    s = client.post("/api/documents/%s/send" % doc["id"]).json()
    [res] = s["results"]
    assert res["action"] == "failed" and "export it again" in res["error"] and anki.notes == {}
    r = export(client, [doc])
    assert fronts(r) == ["Capital of France"] and n["guid"] in r.text  # same guid: the import updates it


def test_exporting_without_marking_leaves_cards_new(client, doc):
    add(client, doc)
    export(client, [doc], mark_exported=False)
    assert notes(client, doc)["F0"]["status"] == "new"


def test_filters_by_scope_type_and_tag(client, doc):
    sent = add(client, doc, front="Sent card")
    client.post("/api/documents/%s/send" % doc["id"])
    add(client, doc, front="Vision fact", tags=["NHB::vision"])
    add(client, doc, front="Other fact", tags=["MVST"])
    client.post("/api/documents/%s/notes" % doc["id"], json={"type": "list", "title": "Layers", "items": ["a", "b"],
                                                              "tags": ["NHB::vision"]})
    assert fronts(export(client, [doc], mark_exported=False)) == ["Vision fact", "Other fact", "Layers"]
    assert fronts(export(client, [doc], scope="all", mark_exported=False))[0] == "Sent card"
    assert fronts(export(client, [doc], types=["list"], mark_exported=False)) == ["Layers"]
    assert fronts(export(client, [doc], tag="nhb", mark_exported=False)) == ["Vision fact", "Layers"]
    assert notes(client, doc)["Sent card"]["status"] == "sent"
    assert sent["id"]


def test_document_tags_count_for_the_tag_filter(client, doc):
    client.patch("/api/documents/%s" % doc["id"], json={"tags": ["NHB::vision"]})
    add(client, doc, front="Vision fact")
    assert fronts(export(client, [doc], tag="NHB::vision", mark_exported=False)) == ["Vision fact"]


def test_cards_with_errors_are_left_out_and_counted(client, doc):
    add(client, doc, front="Good")
    add(client, doc, front="", back="x")
    assert preview(client, [doc]) == {"cards": 1, "with_errors": 1}
    assert fronts(export(client, [doc])) == ["Good"]
    assert notes(client, doc)[""]["status"] == "new"


def test_several_documents_in_one_file(client, doc):
    other = new_doc(client, "renal")
    add(client, doc, front="Vision card")
    add(client, other, front="Renal card")
    r = export(client, [doc, other])
    assert fronts(r) == ["Vision card", "Renal card"] and 'filename="clanki_anki.txt"' in r.headers["content-disposition"]


def test_an_unknown_document_is_a_404(client):
    assert client.post("/api/export", json={"document_ids": ["nope"]}).status_code == 404
