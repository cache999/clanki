"""Cards from your own prompt: written from the model's knowledge, with no document context."""
import json

import keyring
import pytest
from fastapi.testclient import TestClient

from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from clanki.prompts import build_prompt_messages, load_profile
from fake_anki import FakeAnki
from fake_keyring import MemoryKeyring
from fake_llm import ScriptedLLM
from make_pdf import make_pdf

DOC_TEXT = "Rhodopsin absorbs maximally near 498 nm."
REQUEST = "Frank-Starling law of the heart"


def reply(*cards):
    return json.dumps({"cards": list(cards), "left_out": [], "image_occlusion_candidates": [], "flags": []})


QA = {"type": "qa", "front": "Frank-Starling law (definition)", "back": "Stroke volume rises with end-diastolic volume"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    e = {"llm": ScriptedLLM()}
    app = create_app(Config(data_dir=tmp_path / "d"), anki=AnkiConnect(transport=FakeAnki().transport()),
                     provider_for=lambda: e["llm"], jobs_inline=True)
    e["client"] = TestClient(app)
    pdf = make_pdf([[DOC_TEXT], ["Page two."]])
    e["doc"] = e["client"].post("/api/documents", files={"file": ("v.pdf", pdf, "application/pdf")}).json()
    yield e
    keyring.set_keyring(old)


def ask(env, prompt=REQUEST, page=2):
    return env["client"].post("/api/documents/%s/generate" % env["doc"]["id"],
                              json={"mode": "prompt", "prompt": prompt, "page": page})


def test_the_prompt_has_the_request_and_no_document():
    system, user = build_prompt_messages(load_profile("medical_ukmla"), request=REQUEST)
    assert system == {"role": "system", "content": load_profile("medical_ukmla").system}
    assert "<request>\n" + REQUEST + "\n</request>" in user["content"]
    assert "<document" not in user["content"] and "no document" in user["content"]


def test_cards_from_a_prompt_are_filed_at_the_page_being_read(env):
    env["llm"] = ScriptedLLM(reply(QA))
    r = ask(env)
    assert r.status_code == 200, r.text
    [job] = r.json()["jobs"]
    assert (job["mode"], job["status"], job["target"], job["pages"]) == ("prompt", "done", REQUEST, [2, 2])
    [src] = env["client"].get("/api/documents/%s/sources" % env["doc"]["id"]).json()
    assert (src["kind"], src["page"], src["text"], src["rects"]) == ("prompt", 2, REQUEST, [])
    [note] = env["client"].get("/api/documents/%s/notes" % env["doc"]["id"]).json()
    assert note["source_id"] == src["id"] and note["front"] == QA["front"]
    user = env["llm"].calls[0]["messages"][1]["content"]
    assert DOC_TEXT not in user and REQUEST in user
    history = env["client"].get("/api/documents/%s/history" % env["doc"]["id"]).json()
    assert history[0]["label"] == "Generate 1 card (your prompt)"


def test_an_empty_prompt_is_refused(env):
    assert ask(env, prompt="   ").status_code == 422


def test_the_documents_profile_writes_the_cards(env):
    env["client"].patch("/api/documents/%s" % env["doc"]["id"], json={"profile": "general"})
    env["llm"] = ScriptedLLM(reply(QA))
    ask(env)
    assert env["llm"].calls[0]["messages"][0]["content"] == load_profile("general").system


def test_ai_edits_of_such_cards_leave_the_document_out_too(env):
    env["llm"] = ScriptedLLM(reply(QA), reply(QA))
    ask(env)
    [note] = env["client"].get("/api/documents/%s/notes" % env["doc"]["id"]).json()
    env["client"].post("/api/notes/%s/ai-edit" % note["id"], json={"instruction": "shorter back"})
    user = env["llm"].calls[1]["messages"][1]["content"]
    assert DOC_TEXT not in user and "<document" not in user and REQUEST in user
