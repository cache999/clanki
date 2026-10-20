"""Cards from a prompt: while reading, the student asks for a card on something the document may
not cover (P); the model writes it from its own knowledge, with the document as context only."""
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

REQUEST = "why hypoglycaemia causes decerebrate posture"
QA = {"type": "qa", "kind": "concept", "front": "Hypoglycaemia → decerebrate posture (mechanism)",
      "back": "Brainstem neuronal energy failure", "why": "Glucose is the brain's main fuel."}


def reply(*cards):
    return json.dumps({"cards": list(cards), "left_out": [], "image_occlusion_candidates": [], "flags": []})


@pytest.fixture
def llm():
    return {"p": ScriptedLLM()}


@pytest.fixture
def client(tmp_path, llm, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    app = create_app(Config(data_dir=tmp_path / "d"), anki=AnkiConnect(transport=FakeAnki().transport()),
                     provider_for=lambda: llm["p"], jobs_inline=True)
    yield TestClient(app)
    keyring.set_keyring(old)


@pytest.fixture
def doc(client):
    pdf = make_pdf([["Coma"], ["Glasgow Coma Scale: eye, verbal and motor responses."]])
    return client.post("/api/documents", files={"file": ("coma.pdf", pdf, "application/pdf")}).json()


def ask(client, doc, prompt=REQUEST, page=2):
    r = client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "prompt", "prompt": prompt, "page": page})
    assert r.status_code == 200, r.text
    return r.json()["jobs"]


def test_a_prompt_makes_cards_from_the_request_with_the_document_as_context(client, doc, llm):
    llm["p"] = ScriptedLLM(reply(QA))
    [job] = ask(client, doc)
    assert (job["mode"], job["status"], job["pages"], job["target"]) == ("prompt", "done", [2, 2], REQUEST)
    [src] = client.get("/api/documents/%s/sources" % doc["id"]).json()
    assert (src["id"], src["kind"], src["page"], src["text"], src["rects"]) == (job["source_id"], "prompt", 2, REQUEST, [])
    [note] = client.get("/api/documents/%s/notes" % doc["id"]).json()
    assert note["front"] == QA["front"] and note["source_id"] == src["id"] and note["tags"] == ["ai-generated"]
    user = llm["p"].calls[0]["messages"][1]["content"]
    assert "Glasgow Coma Scale" in user and "<request>\n%s\n</request>" % REQUEST in user
    assert "<target" not in user and "Focus:" not in user


def test_a_prompt_must_ask_for_something(client, doc):
    r = client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "prompt", "prompt": "  ", "page": 1})
    assert r.status_code == 422


@pytest.mark.parametrize("page,kept", [(99, 2), (0, 1)])
def test_the_card_sits_on_a_page_of_the_document(client, doc, llm, page, kept):
    llm["p"] = ScriptedLLM(reply(QA))
    [job] = ask(client, doc, page=page)
    assert job["pages"] == [kept, kept]


def test_retry_asks_again(client, doc, llm):
    llm["p"] = ScriptedLLM(reply(QA), reply({**QA, "front": "Again"}))
    [job] = ask(client, doc)
    again = client.post("/api/jobs/%s/retry" % job["id"]).json()
    assert (again["mode"], again["source_id"], again["status"]) == ("prompt", job["source_id"], "done")
    assert "<request>" in llm["p"].calls[1]["messages"][1]["content"]


def test_ai_edits_of_a_prompted_card_see_the_request_not_a_source(client, doc, llm):
    llm["p"] = ScriptedLLM(reply(QA), reply({**QA, "back": "Shorter"}))
    ask(client, doc)
    [note] = client.get("/api/documents/%s/notes" % doc["id"]).json()
    client.post("/api/notes/%s/ai-edit" % note["id"], json={"instruction": "shorter back"})
    user = llm["p"].calls[1]["messages"][1]["content"]
    assert "<request>\n%s\n</request>" % REQUEST in user and "<source" not in user
