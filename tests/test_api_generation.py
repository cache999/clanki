import json

import keyring
import pytest
from fastapi.testclient import TestClient

from clanki.app import create_app
from clanki.ankiconnect import AnkiConnect
from clanki.config import Config
from clanki.llm import LLMError
from fake_anki import FakeAnki
from fake_llm import EchoLLM, ScriptedLLM
from make_pdf import make_pdf
from fake_keyring import MemoryKeyring

PAGES = [["The Visual System", "Rhodopsin absorbs maximally near 498 nm."],
         ["Retinal cell layers:", "Photoreceptors", "Bipolar cells", "Ganglion cells"]]


@pytest.fixture
def llm():
    return {"provider": EchoLLM()}


@pytest.fixture
def client(tmp_path, llm, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    cfg = Config(data_dir=tmp_path / "data")
    app = create_app(cfg, anki=AnkiConnect(transport=FakeAnki().transport()),
                     provider_for=lambda: llm["provider"], jobs_inline=True)
    yield TestClient(app)
    keyring.set_keyring(old)


@pytest.fixture
def doc(client):
    r = client.post("/api/documents", files={"file": ("vision.pdf", make_pdf(PAGES), "application/pdf")})
    return r.json()


def generate(client, doc, **body):
    r = client.post("/api/documents/%s/generate" % doc["id"], json=body)
    assert r.status_code == 200, r.text
    return r.json()["jobs"]


SEL = {"page": 1, "text": "Rhodopsin absorbs maximally near 498 nm.", "rects": [[0.1, 0.1, 0.5, 0.02]]}


def test_generate_from_a_selection_makes_a_highlight_and_cards(client, doc):
    [job] = generate(client, doc, mode="selection", selection=SEL, focus="value")
    assert job["status"] == "done" and job["mode"] == "highlight" and job["pages"] == [1, 1]
    [src] = client.get("/api/documents/%s/sources" % doc["id"]).json()
    assert src["id"] == job["source_id"] and src["rects"] == SEL["rects"]
    notes = client.get("/api/documents/%s/notes" % doc["id"]).json()
    assert [n["id"] for n in notes] == job["note_ids"]
    assert notes[0]["front"] == "Generated: Rhodopsin absorbs maximally near 498 nm."
    assert notes[0]["why"] == "focus was value" and notes[0]["tags"] == ["ai-generated"]
    assert client.get("/api/documents/%s/jobs" % doc["id"]).json()[0]["id"] == job["id"]


def test_generate_whole_document_makes_one_job_per_chunk(client, doc):
    jobs = generate(client, doc, mode="document")
    assert [j["pages"] for j in jobs] == [[1, 2]]
    assert all(j["status"] == "done" for j in jobs)
    [src] = client.get("/api/documents/%s/sources" % doc["id"]).json()
    assert (src["kind"], src["page"], src["page_end"]) == ("chunk", 1, 2)
    notes = client.get("/api/documents/%s/notes" % doc["id"]).json()
    lst = [n for n in notes if n["type"] == "list"][0]
    assert [i["code"] for i in lst["issues"]] == ["model_flag"]


def test_model_must_be_known(client, doc):
    r = client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "document", "model": "gpt-4"})
    assert r.status_code == 422


def test_selection_mode_needs_a_selection(client, doc):
    r = client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "selection"})
    assert r.status_code == 422


def test_failed_job_is_reported_and_can_be_retried_with_another_model(client, doc, llm):
    llm["provider"] = ScriptedLLM(LLMError("DeepSeek rejected the API key"))
    [job] = generate(client, doc, mode="selection", selection=SEL)
    assert (job["status"], job["error"]) == ("failed", "DeepSeek rejected the API key")
    llm["provider"] = EchoLLM()
    r = client.post("/api/jobs/%s/retry" % job["id"], json={"model": "deepseek-v4-pro"}).json()
    assert r["status"] == "done" and r["model"] == "deepseek-v4-pro" and r["source_id"] == job["source_id"]
    assert len(client.get("/api/documents/%s/sources" % doc["id"]).json()) == 1


def test_left_out_content_can_be_carded_anyway(client, doc):
    [job] = generate(client, doc, mode="selection", selection=SEL)
    assert job["left_out"] == [{"text": "a left-out sentence", "reason": "not testable"}]
    r = client.post("/api/jobs/%s/left-out/0" % job["id"]).json()
    assert r["status"] == "done" and r["target"] == "a left-out sentence"
    assert "regardless of UKMLA relevance" in r["focus"]


def test_cancel_a_finished_job_changes_nothing(client, doc):
    [job] = generate(client, doc, mode="selection", selection=SEL)
    assert client.post("/api/jobs/%s/cancel" % job["id"]).json()["status"] == "done"


def test_estimate_whole_document_cost(client, doc):
    e = client.get("/api/documents/%s/estimate" % doc["id"]).json()
    assert e["chunks"] == 1 and e["input_tokens"] > 0 and e["output_tokens"] > 0
    pro = client.get("/api/documents/%s/estimate?model=deepseek-v4-pro" % doc["id"]).json()
    assert pro["cost_usd"] > e["cost_usd"] > 0


def test_document_without_text_cannot_be_generated(client):
    r = client.post("/api/documents", files={"file": ("scan.pdf", make_pdf([[]]), "application/pdf")})
    resp = client.post("/api/documents/%s/generate" % r.json()["id"], json={"mode": "document"})
    assert resp.status_code == 422 and "no text" in resp.json()["detail"].lower()


def test_settings_show_models_key_status_and_default(client):
    s = client.get("/api/settings").json()
    assert s["providers"]["deepseek"]["models"] == ["deepseek-flash", "deepseek-v4-pro"]
    assert s["providers"]["deepseek"]["key"] == {"set": False, "source": None, "hint": None, "store": True}
    assert s["default_model"] == "deepseek-flash"
    assert client.put("/api/settings", json={"default_model": "deepseek-v4-pro"}).json()["default_model"] == "deepseek-v4-pro"
    assert client.put("/api/settings", json={"default_model": "nope"}).status_code == 422


def test_default_model_is_used_when_none_is_given(client, doc):
    client.put("/api/settings", json={"default_model": "deepseek-v4-pro"})
    [job] = generate(client, doc, mode="selection", selection=SEL)
    assert job["model"] == "deepseek-v4-pro"


def test_keys_are_stored_masked_and_never_returned(client):
    r = client.put("/api/settings/keys/deepseek", json={"key": "sk-secret-abcd"})
    assert r.json() == {"set": True, "source": "keyring", "hint": "…abcd", "store": True}
    assert "sk-secret" not in json.dumps(client.get("/api/settings").json())
    assert client.post("/api/settings/keys/deepseek/test").json() == {"ok": True, "error": None}
    client.delete("/api/settings/keys/deepseek")
    assert client.get("/api/settings").json()["providers"]["deepseek"]["key"]["set"] is False


def test_key_test_reports_provider_errors(client, llm):
    class Bad:
        def check(self):
            raise LLMError("DeepSeek rejected the API key")
    llm["provider"] = Bad()
    assert client.post("/api/settings/keys/deepseek/test").json() == {"ok": False, "error": "DeepSeek rejected the API key"}
