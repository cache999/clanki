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


def capture(client, doc, **kw):
    body = {"page": 2, "rect": [0.1, 0.2, 0.5, 0.3], "image": PNG_URL, **kw}
    r = client.post("/api/documents/%s/screenshots" % doc["id"], json=body)
    assert r.status_code == 200, r.text
    return r.json()


def read(client, doc, *srcs, force=False):
    r = client.post("/api/documents/%s/transcribe" % doc["id"], json={"source_ids": [x["id"] for x in srcs], "force": force})
    assert r.status_code == 200, r.text
    return r.json()["jobs"]


def source(client, doc, sid):
    return next(s for s in client.get("/api/documents/%s/sources" % doc["id"]).json() if s["id"] == sid)


def test_a_screenshot_is_cached_without_calling_the_model(client, doc, llm):
    src = capture(client, doc)
    assert (src["kind"], src["page"], src["rects"], src["text"]) == ("region", 2, [[0.1, 0.2, 0.5, 0.3]], "")
    assert llm["p"].calls == [] and client.get("/api/documents/%s/jobs" % doc["id"]).json() == []
    r = client.get("/api/sources/%s/image" % src["id"])
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"


def test_a_pasted_screenshot_has_no_box(client, doc):
    assert (capture(client, doc, rect=None)["kind"], capture(client, doc, rect=None)["rects"]) == ("image", [])


@pytest.mark.parametrize("image", ["not a data url", "data:image/png;base64,bm90IGFuIGltYWdl",
                                   "data:text/plain;base64," + base64.b64encode(PNG).decode()])
def test_only_images_are_accepted(client, doc, image):
    r = client.post("/api/documents/%s/screenshots" % doc["id"], json={"page": 1, "image": image})
    assert r.status_code == 422


def test_reading_transcribes_each_selected_image_separately(client, doc, llm):
    llm["p"] = ScriptedLLM("Figure A text", "Figure B text")
    a, b = capture(client, doc), capture(client, doc, rect=None)
    jobs = read(client, doc, a, b)
    assert [(j["mode"], j["status"], j["source_id"]) for j in jobs] == [("transcribe", "done", a["id"]), ("transcribe", "done", b["id"])]
    assert (source(client, doc, a["id"])["text"], source(client, doc, b["id"])["text"]) == ("Figure A text", "Figure B text")
    call = llm["p"].calls[0]
    assert call["kw"].get("json_mode") is False
    text, image = call["messages"][1]["content"]
    assert image == {"type": "image_url", "image_url": {"url": PNG_URL}}
    assert "carpal tunnel" in text["text"]  # the page's own text, to spell labels right


def test_reading_uses_a_model_that_reads_images_whatever_the_default(client, doc, llm):
    # deepseek-v4-pro drops images silently and replies that it can't see one
    client.put("/api/settings", json={"default_model": "deepseek-v4-pro"})
    llm["p"] = ScriptedLLM(TRANSCRIPT, "Re-read text")
    [job] = read(client, doc, capture(client, doc))
    assert job["model"] == "deepseek-flash" and llm["p"].calls[0]["model"] == "deepseek-flash"
    again = client.post("/api/jobs/%s/retry" % job["id"], json={"model": "deepseek-v4-pro"}).json()
    assert again["model"] == "deepseek-flash" and llm["p"].calls[1]["model"] == "deepseek-flash"


def test_reading_uses_the_image_model_setting(client, doc, llm, monkeypatch):
    import clanki.app
    monkeypatch.setattr(clanki.app, "IMAGE_MODELS", ("deepseek-flash", "deepseek-v4-pro"))  # as if pro read images
    assert client.put("/api/settings", json={"image_model": "deepseek-v4-pro"}).status_code == 200
    llm["p"] = ScriptedLLM(TRANSCRIPT)
    [job] = read(client, doc, capture(client, doc))
    assert job["model"] == "deepseek-v4-pro"


def test_a_read_image_is_not_sent_again_unless_forced(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT, "Re-read text")
    a = capture(client, doc)
    read(client, doc, a)
    assert read(client, doc, a) == [] and len(llm["p"].calls) == 1
    [job] = read(client, doc, a, force=True)
    assert job["status"] == "done" and source(client, doc, a["id"])["text"] == "Re-read text"


def test_an_empty_reply_fails_the_job(client, doc, llm):
    llm["p"] = ScriptedLLM("   ")
    [job] = read(client, doc, capture(client, doc))
    assert job["status"] == "failed" and "no text" in job["error"]


def test_retry_transcribes_the_saved_image_again(client, doc, llm):
    llm["p"] = ScriptedLLM("", TRANSCRIPT)
    a = capture(client, doc)
    [job] = read(client, doc, a)
    again = client.post("/api/jobs/%s/retry" % job["id"]).json()
    assert again["status"] == "done" and source(client, doc, a["id"])["text"] == TRANSCRIPT
    assert llm["p"].calls[1]["messages"][1]["content"][1]["image_url"]["url"] == PNG_URL


def test_cards_from_one_image_use_its_corrected_transcript(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT, cards(QA))
    src = capture(client, doc)
    read(client, doc, src)
    edited = "Median nerve: carpal tunnel"
    sel = {"page": 2, "text": edited, "rects": src["rects"]}
    [job] = client.post("/api/documents/%s/generate" % doc["id"],
                        json={"mode": "selection", "selection": sel, "source_ids": [src["id"]]}).json()["jobs"]
    assert (job["mode"], job["source_id"], job["status"]) == ("figure", src["id"], "done")
    assert source(client, doc, src["id"])["text"] == edited
    assert len(client.get("/api/documents/%s/sources" % doc["id"]).json()) == 1
    user = llm["p"].calls[1]["messages"][1]["content"]
    assert "transcribed from a figure" in user and edited in user
    [note] = client.get("/api/documents/%s/notes" % doc["id"]).json()
    assert note["source_id"] == src["id"]


def test_cards_from_several_images_attach_to_the_first_and_keep_each_transcript(client, doc, llm):
    llm["p"] = ScriptedLLM("A text", "B text", cards(QA))
    a, b = capture(client, doc), capture(client, doc, rect=None)
    read(client, doc, a, b)
    combined = "[Image 1, p.2]\nA text\n\n[Image 2, p.2]\nB text"
    sel = {"page": 2, "text": combined, "rects": a["rects"]}
    [job] = client.post("/api/documents/%s/generate" % doc["id"],
                        json={"mode": "selection", "selection": sel, "source_ids": [a["id"], b["id"]]}).json()["jobs"]
    assert (job["source_id"], job["target"]) == (a["id"], combined)
    assert (source(client, doc, a["id"])["text"], source(client, doc, b["id"])["text"]) == ("A text", "B text")


def test_a_source_of_another_document_cannot_be_used(client, doc):
    other = client.post("/api/documents", files={"file": ("o.pdf", make_pdf([["x"]]), "application/pdf")}).json()
    src = capture(client, other)
    sel = {"page": 1, "text": "x", "rects": []}
    r = client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "selection", "selection": sel, "source_ids": [src["id"]]})
    assert r.status_code == 404
    assert client.post("/api/documents/%s/transcribe" % doc["id"], json={"source_ids": [src["id"]]}).status_code == 404


def test_the_transcript_can_be_corrected(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT)
    src = capture(client, doc)
    read(client, doc, src)
    r = client.patch("/api/sources/%s" % src["id"], json={"text": "Median nerve: carpal tunnel"})
    assert r.status_code == 200 and source(client, doc, src["id"])["text"] == "Median nerve: carpal tunnel"


def test_ai_edits_see_the_transcript_as_the_source(client, doc, llm):
    llm["p"] = ScriptedLLM(TRANSCRIPT, cards(QA))
    src = capture(client, doc)
    read(client, doc, src)
    note = client.post("/api/documents/%s/notes" % doc["id"],
                       json={"type": "qa", "front": "Median nerve (course)", "back": "x", "source_id": src["id"]}).json()
    client.post("/api/notes/%s/ai-edit" % note["id"], json={"instruction": "fix the back"})
    assert "<source pages=\"2\">\n" + TRANSCRIPT in llm["p"].calls[1]["messages"][1]["content"]


def test_an_unused_screenshot_can_be_deleted_but_not_one_cards_use(client, doc):
    unused, used = capture(client, doc), capture(client, doc)
    client.post("/api/documents/%s/notes" % doc["id"], json={"type": "qa", "front": "F", "back": "B", "source_id": used["id"]})
    assert client.delete("/api/sources/%s" % unused["id"]).status_code == 200
    assert client.get("/api/sources/%s/image" % unused["id"]).status_code == 404
    r = client.delete("/api/sources/%s" % used["id"])
    assert r.status_code == 409 and "card" in r.json()["detail"]
    assert [s["id"] for s in client.get("/api/documents/%s/sources" % doc["id"]).json()] == [used["id"]]


def test_transcribe_prompt_has_the_image_and_page_text():
    msgs = build_transcribe_messages(load_profile(), image=PNG_URL, page_text="Carpal tunnel.")
    assert msgs[0]["role"] == "system" and "transcribe" in msgs[0]["content"].lower()
    text, image = msgs[1]["content"]
    assert "Carpal tunnel." in text["text"] and image["image_url"]["url"] == PNG_URL


def big_png_url():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1300, 1300), "white").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.mark.parametrize("refusal", ["NO_IMAGE", "The image is unsupported, so I cannot transcribe it.",
                                     "I can't see any image attached."])
def test_a_reply_that_never_saw_the_image_is_retried_then_fails(client, doc, llm, refusal):
    llm["p"] = ScriptedLLM(refusal, refusal)
    a = capture(client, doc)
    [job] = read(client, doc, a)
    assert job["status"] == "failed" and "did not receive the image" in job["error"] and job["attempts"] == 2
    assert source(client, doc, a["id"])["text"] == ""  # nothing cached: T reads it again


def test_one_missed_image_then_a_good_reply_is_fine(client, doc, llm):
    llm["p"] = ScriptedLLM("NO_IMAGE", TRANSCRIPT)
    a = capture(client, doc)
    [job] = read(client, doc, a)
    assert job["status"] == "done" and source(client, doc, a["id"])["text"] == TRANSCRIPT


def test_too_few_prompt_tokens_for_a_large_image_means_it_was_not_read(client, doc, llm):
    from clanki.llm import Usage
    llm["p"] = ScriptedLLM("A transcript invented from the page text", "Another", usage=Usage(cache_hit=460, cache_miss=4, output=50, reasoning=0))  # about the text alone
    [job] = read(client, doc, capture(client, doc, image=big_png_url()))
    assert job["status"] == "failed" and "did not receive the image" in job["error"]


def test_enough_prompt_tokens_for_a_large_image_is_accepted(client, doc, llm):
    from clanki.llm import Usage
    llm["p"] = ScriptedLLM(TRANSCRIPT, usage=Usage(cache_hit=0, cache_miss=2400, output=50, reasoning=0))
    [job] = read(client, doc, capture(client, doc, image=big_png_url()))
    assert job["status"] == "done"


def test_a_refusal_cached_by_an_older_version_is_read_again(client, doc, llm):
    a = capture(client, doc)
    client.patch("/api/sources/%s" % a["id"], json={"text": "The image is unsupported, so I cannot transcribe it."})
    llm["p"] = ScriptedLLM(TRANSCRIPT)
    [job] = read(client, doc, a)
    assert job["status"] == "done" and source(client, doc, a["id"])["text"] == TRANSCRIPT
