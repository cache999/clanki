"""Undo history: every change to cards is recorded, per document, and survives restarts."""
import json

import keyring
import pytest
from fastapi.testclient import TestClient

from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from fake_anki import FakeAnki
from fake_keyring import MemoryKeyring
from fake_llm import ScriptedLLM
from make_pdf import make_pdf


def reply(*cards):
    return json.dumps({"cards": list(cards), "left_out": [], "image_occlusion_candidates": [], "flags": []})


QA = {"type": "qa", "front": "Rhodopsin peak (nm)", "back": "~498 nm"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    e = {"llm": ScriptedLLM(), "anki": FakeAnki(), "tmp": tmp_path}
    yield e
    keyring.set_keyring(old)


def make_client(env):
    app = create_app(Config(data_dir=env["tmp"] / "d"), anki=AnkiConnect(transport=env["anki"].transport()),
                     provider_for=lambda: env["llm"], jobs_inline=True)
    return TestClient(app)


@pytest.fixture
def client(env):
    return make_client(env)


@pytest.fixture
def doc(client):
    pdf = make_pdf([["Rhodopsin absorbs maximally near 498 nm."]])
    return client.post("/api/documents", files={"file": ("v.pdf", pdf, "application/pdf")}).json()


def add(client, doc, front="Peak absorption of rhodopsin", back="498 nm"):
    return client.post("/api/documents/%s/notes" % doc["id"], json={"type": "qa", "front": front, "back": back}).json()


def notes(client, doc):
    return client.get("/api/documents/%s/notes" % doc["id"]).json()


def undo(client, doc, **params):
    r = client.post("/api/documents/%s/undo" % doc["id"], params=params)
    assert r.status_code == 200, r.text
    return r.json()


def redo(client, doc, **params):
    return client.post("/api/documents/%s/redo" % doc["id"], params=params).json()


def history(client, doc):
    return client.get("/api/documents/%s/history" % doc["id"]).json()


def test_an_edit_is_undone_and_redone(client, doc):
    n = add(client, doc)
    client.patch("/api/notes/%s" % n["id"], json={"back": "~498 nm"})
    r = undo(client, doc)
    assert r["label"] == "Edit card: Peak absorption of rhodopsin" and r["message"] is None
    assert notes(client, doc)[0]["back"] == "498 nm"
    assert redo(client, doc)["label"] == "Edit card: Peak absorption of rhodopsin"
    assert notes(client, doc)[0]["back"] == "~498 nm"


def test_deleting_and_adding_are_undone(client, doc):
    n = add(client, doc)
    client.delete("/api/notes/%s" % n["id"])
    assert notes(client, doc) == []
    undo(client, doc)
    assert [x["id"] for x in notes(client, doc)] == [n["id"]]
    undo(client, doc)  # the add
    assert notes(client, doc) == []


def test_a_generation_job_is_one_step(client, doc, env):
    env["llm"] = ScriptedLLM(reply(QA, {**QA, "front": "Rhodopsin location", "back": "Rods"}))
    sel = {"page": 1, "text": "Rhodopsin absorbs maximally near 498 nm.", "rects": []}
    client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "selection", "selection": sel})
    assert len(notes(client, doc)) == 2
    assert undo(client, doc)["label"] == "Generate 2 cards (p.1)"
    assert notes(client, doc) == []


def test_accepting_a_split_ai_edit_is_one_step(client, doc, env):
    n = add(client, doc)
    env["llm"] = ScriptedLLM(reply(QA, {**QA, "front": "Rhodopsin location", "back": "Rods"}))
    job = client.post("/api/notes/%s/ai-edit" % n["id"], json={"instruction": "split"}).json()
    client.post("/api/jobs/%s/accept" % job["id"])
    assert len(notes(client, doc)) == 2
    assert undo(client, doc)["label"].startswith("Accept AI edit")
    [back] = notes(client, doc)
    assert (back["id"], back["front"]) == (n["id"], "Peak absorption of rhodopsin")


def test_undoing_an_edit_of_a_sent_card_marks_it_for_update(client, doc):
    n = add(client, doc)
    client.post("/api/documents/%s/send" % doc["id"])
    client.patch("/api/notes/%s" % n["id"], json={"back": "~498 nm"})
    client.post("/api/documents/%s/send" % doc["id"])  # Anki now has "~498 nm"
    undo(client, doc)
    [x] = notes(client, doc)
    assert (x["back"], x["status"], x["anki_note_id"] is not None) == ("498 nm", "edited", True)


def test_undoing_the_add_of_a_sent_card_says_it_is_still_in_anki(client, doc):
    add(client, doc)
    client.post("/api/documents/%s/send" % doc["id"])
    r = undo(client, doc)
    assert notes(client, doc) == [] and "still in Anki" in r["message"]


def test_a_new_change_clears_redo(client, doc):
    n = add(client, doc)
    client.patch("/api/notes/%s" % n["id"], json={"back": "a"})
    undo(client, doc)
    client.patch("/api/notes/%s" % n["id"], json={"back": "b"})
    assert redo(client, doc) == {"label": None, "message": None}
    assert notes(client, doc)[0]["back"] == "b"


def test_history_lists_changes_and_undoes_back_to_one(client, doc):
    n = add(client, doc)
    client.patch("/api/notes/%s" % n["id"], json={"back": "a"})
    client.patch("/api/notes/%s" % n["id"], json={"flags": ["x"]})
    client.patch("/api/notes/%s" % n["id"], json={"flags": []})
    h = history(client, doc)
    assert [x["label"].split(":")[0] for x in h] == ["Dismiss a flag", "Dismiss a flag", "Edit card", "Add card"]
    undo(client, doc, to=h[2]["id"])
    assert [x["undone"] for x in history(client, doc)] == [True, True, True, False]
    assert notes(client, doc)[0]["back"] == "498 nm"
    redo(client, doc, to=h[1]["id"])
    assert notes(client, doc)[0]["flags"] == ["x"]


def test_nothing_to_undo(client, doc):
    assert undo(client, doc) == {"label": None, "message": None}


def test_history_is_per_document_and_survives_a_restart(client, doc, env):
    add(client, doc)
    other = client.post("/api/documents", files={"file": ("o.pdf", make_pdf([["x"]]), "application/pdf")}).json()
    assert history(client, other) == []
    again = make_client(env)
    assert undo(again, doc)["label"] == "Add card: Peak absorption of rhodopsin"
