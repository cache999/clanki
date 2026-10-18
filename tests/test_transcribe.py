"""Figures and screenshots: the model transcribes an image into text, which cards are then made from."""
import base64
import json

import keyring
import pytest
from fastapi.testclient import TestClient

from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from clanki.prompts import build_transcribe_messages, load_profile
from fake_anki import FakeAnki
from fake_keyring import MemoryKeyring
from fake_llm import ScriptedLLM
from make_pdf import make_pdf

# a 1x1 PNG
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
PNG_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()
TRANSCRIPT = "Median nerve: passes through the carpal tunnel\nUlnar nerve → Guyon's canal"


def cards(*cs):
    return json.dumps({"cards": list(cs), "left_out": [], "image_occlusion_candidates": [], "flags": []})


QA = {"type": "qa", "front": "Median nerve (course)", "back": "Carpal tunnel"}


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
    c = TestClient(app)
    c.data_dir = tmp_path / "d"
    yield c
    keyring.set_keyring(old)


@pytest.fixture
def doc(client):
    pdf = make_pdf([["Upper limb nerves"], ["The median nerve enters the hand through the carpal tunnel."]])
    return client.post("/api/documents", files={"file": ("nerves.pdf", pdf, "application/pdf")}).json()


def transcribe(client, doc, **kw):
    body = {"page": 2, "rect": [0.1, 0.2, 0.5, 0.3], "image": PNG_URL, **kw}
    r = client.post("/api/documents/%s/transcribe" % doc["id"], json=body)
    assert r.status_code == 200, r.text
    return r.json()


def source(client, doc, sid):
    return next(s for s in client.get("/api/documents/%s/sources" % doc["id"]).json() if s["id"] == sid)


def test_a_dragged_region_is_transcribed_into_its_source(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT)
    r = transcribe(client, doc)
    job, src = r["job"], r["source"]
    assert (job["mode"], job["status"], job["source_id"], job["cost_usd"] > 0) == ("transcribe", "done", src["id"], True)
    s = source(client, doc, src["id"])
    assert (s["kind"], s["page"], s["rects"], s["text"]) == ("region", 2, [[0.1, 0.2, 0.5, 0.3]], TRANSCRIPT)
    call = llm["p"].calls[0]
    assert call["kw"].get("json_mode") is False
    text, image = call["messages"][1]["content"]
    assert image == {"type": "image_url", "image_url": {"url": PNG_URL}}
    assert "carpal tunnel" in text["text"]  # the page's own text, to spell labels right


def test_a_pasted_screenshot_has_no_box(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT)
    src = transcribe(client, doc, rect=None)["source"]
    assert (source(client, doc, src["id"])["kind"], source(client, doc, src["id"])["rects"]) == ("image", [])


@pytest.mark.parametrize("image", ["not a data url", "data:image/png;base64,bm90IGFuIGltYWdl",
                                   "data:text/plain;base64," + base64.b64encode(PNG).decode()])
def test_only_images_are_accepted(client, doc, image):
    r = client.post("/api/documents/%s/transcribe" % doc["id"], json={"page": 1, "image": image})
    assert r.status_code == 422


def test_an_empty_reply_fails_the_job(client, doc, llm):
    llm["p"] = ScriptedLLM("   ")
    job = transcribe(client, doc)["job"]
    assert job["status"] == "failed" and "no text" in job["error"]


def test_retry_transcribes_the_saved_image_again(client, doc, llm):
    llm["p"] = ScriptedLLM("", TRANSCRIPT)
    r = transcribe(client, doc)
    again = client.post("/api/jobs/%s/retry" % r["job"]["id"]).json()
    assert again["status"] == "done" and source(client, doc, r["source"]["id"])["text"] == TRANSCRIPT
    assert llm["p"].calls[1]["messages"][1]["content"][1]["image_url"]["url"] == PNG_URL


def test_cards_are_generated_from_the_edited_transcript_on_the_same_source(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT, cards(QA))
    src = transcribe(client, doc)["source"]
    edited = "Median nerve: carpal tunnel"
    sel = {"page": 2, "text": edited, "rects": src["rects"]}
    [job] = client.post("/api/documents/%s/generate" % doc["id"],
                        json={"mode": "selection", "selection": sel, "source_id": src["id"]}).json()["jobs"]
    assert (job["mode"], job["source_id"], job["status"]) == ("figure", src["id"], "done")
    assert source(client, doc, src["id"])["text"] == edited
    assert len(client.get("/api/documents/%s/sources" % doc["id"]).json()) == 1
    user = llm["p"].calls[1]["messages"][1]["content"]
    assert "transcribed from a figure" in user and edited in user
    [note] = client.get("/api/documents/%s/notes" % doc["id"]).json()
    assert note["source_id"] == src["id"]


def test_a_source_of_another_document_cannot_be_used(client, doc, llm):
    other = client.post("/api/documents", files={"file": ("o.pdf", make_pdf([["x"]]), "application/pdf")}).json()
    llm["p"] = ScriptedLLM(TRANSCRIPT)
    src = transcribe(client, other)["source"]
    sel = {"page": 1, "text": "x", "rects": []}
    r = client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "selection", "selection": sel, "source_id": src["id"]})
    assert r.status_code == 404


def test_the_transcript_can_be_corrected(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT)
    src = transcribe(client, doc)["source"]
    r = client.patch("/api/sources/%s" % src["id"], json={"text": "Median nerve: carpal tunnel"})
    assert r.status_code == 200 and source(client, doc, src["id"])["text"] == "Median nerve: carpal tunnel"


def test_ai_edits_see_the_transcript_as_the_source(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT, cards(QA))
    src = transcribe(client, doc)["source"]
    note = client.post("/api/documents/%s/notes" % doc["id"],
                       json={"type": "qa", "front": "Median nerve (course)", "back": "x", "source_id": src["id"]}).json()
    client.post("/api/notes/%s/ai-edit" % note["id"], json={"instruction": "fix the back"})
    assert "<source pages=\"2\">\n" + TRANSCRIPT in llm["p"].calls[1]["messages"][1]["content"]


def test_transcribe_prompt_has_the_image_and_page_text():
    msgs = build_transcribe_messages(load_profile(), image=PNG_URL, page_text="Carpal tunnel.")
    assert msgs[0]["role"] == "system" and "transcribe" in msgs[0]["content"].lower()
    text, image = msgs[1]["content"]
    assert "Carpal tunnel." in text["text"] and image["image_url"]["url"] == PNG_URL
