import json

import keyring
import pytest
from fastapi.testclient import TestClient

from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from clanki.prompts import build_edit_messages, build_messages, load_profile
from fake_anki import FakeAnki
from fake_keyring import MemoryKeyring
from fake_llm import ScriptedLLM
from make_pdf import make_pdf


def reply(*cards, flags=()):
    return json.dumps({"cards": list(cards), "left_out": [], "image_occlusion_candidates": [], "flags": list(flags)})


QA = {"type": "qa", "kind": "fact", "front": "Rhodopsin peak (nm)", "back": "~498 nm", "why": "",
      "add_reverse": True, "reverse_prompt": "pigment with this peak?", "facets": ["value"], "flags": ["shortened"]}
LIST = {"type": "list", "kind": "set", "title": "Retinal layers (outer to inner)",
        "items": ["Photoreceptors", "Bipolar", "Ganglion", "Nerve fibres"], "full": True}


@pytest.fixture
def llm():
    return {"p": ScriptedLLM()}


@pytest.fixture
def client(tmp_path, llm, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    fake_anki = FakeAnki()
    app = create_app(Config(data_dir=tmp_path / "d"), anki=AnkiConnect(transport=fake_anki.transport()),
                     provider_for=lambda: llm["p"], jobs_inline=True)
    c = TestClient(app)
    c.fake_anki = fake_anki
    yield c
    keyring.set_keyring(old)


@pytest.fixture
def doc(client):
    pdf = make_pdf([["Rhodopsin absorbs maximally near 498 nm."], ["Retinal layers"]])
    return client.post("/api/documents", files={"file": ("vision.pdf", pdf, "application/pdf")}).json()


@pytest.fixture
def note(client, doc):
    src = client.post("/api/documents/%s/sources" % doc["id"],
                      json={"page": 1, "text": "Rhodopsin absorbs maximally near 498 nm.", "rects": []}).json()
    body = {"type": "qa", "front": "Peak absorption wavelength of the rod visual pigment rhodopsin (value + unit)",
            "back": "~498 nm", "source_id": src["id"], "tags": ["NHB::vision"]}
    return client.post("/api/documents/%s/notes" % doc["id"], json=body).json()


def ask(client, note, instruction="shorter front", **kw):
    r = client.post("/api/notes/%s/ai-edit" % note["id"], json={"instruction": instruction, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def notes(client, doc):
    return client.get("/api/documents/%s/notes" % doc["id"]).json()


def test_ai_edit_makes_a_suggestion_without_changing_the_card(client, doc, note, llm):
    llm["p"] = ScriptedLLM(reply(QA))
    job = ask(client, note)
    assert (job["mode"], job["status"], job["note_id"], job["focus"]) == ("edit", "done", note["id"], "shorter front")
    assert job["proposal"][0]["front"] == "Rhodopsin peak (nm)"
    assert job["before"]["front"] == note["front"]
    [n] = notes(client, doc)
    assert n["front"] == note["front"]
    user = llm["p"].calls[0]["messages"][1]["content"]
    assert "<card>" in user and '"front": "Peak absorption wavelength' in user
    assert "Instruction: shorter front" in user and "Rhodopsin absorbs maximally" in user


def test_accepting_applies_the_suggestion_in_place(client, doc, note, llm):
    llm["p"] = ScriptedLLM(reply(QA))
    job = ask(client, note)
    r = client.post("/api/jobs/%s/accept" % job["id"]).json()
    assert r["job"]["status"] == "applied" and r["message"] is None
    [n] = notes(client, doc)
    assert (n["id"], n["guid"], n["front"], n["reverse_prompt"], n["flags"]) == (
        note["id"], note["guid"], "Rhodopsin peak (nm)", "pigment with this peak?", ["shortened"])
    assert n["tags"] == ["NHB::vision"] and n["status"] == "new"


def test_accepting_an_edit_of_a_sent_card_marks_it_for_update_in_anki(client, doc, note, llm):
    client.post("/api/documents/%s/send" % doc["id"])
    llm["p"] = ScriptedLLM(reply(QA))
    client.post("/api/jobs/%s/accept" % ask(client, note)["id"])
    assert notes(client, doc)[0]["status"] == "edited"
    client.post("/api/documents/%s/send" % doc["id"])
    [anki_note] = client.fake_anki.notes.values()
    assert anki_note["fields"]["Front"] == "Rhodopsin peak (nm)"


def test_a_split_adds_cards_from_the_same_source(client, doc, note, llm):
    second = {**QA, "front": "Rhodopsin location", "back": "Rod outer segment discs", "add_reverse": False}
    llm["p"] = ScriptedLLM(reply(QA, second))
    job = ask(client, note, "split into two cards")
    r = client.post("/api/jobs/%s/accept" % job["id"]).json()
    ns = notes(client, doc)
    assert [n["front"] for n in ns] == ["Rhodopsin peak (nm)", "Rhodopsin location"]
    assert ns[1]["source_id"] == note["source_id"] and ns[1]["tags"] == ["NHB::vision", "ai-generated"]
    assert r["job"]["note_ids"] == [n["id"] for n in ns]


def test_changing_type_of_an_unsent_card_happens_in_place(client, doc, note, llm):
    llm["p"] = ScriptedLLM(reply(LIST))
    client.post("/api/jobs/%s/accept" % ask(client, note, "make it a list")["id"])
    [n] = notes(client, doc)
    assert (n["id"], n["type"], n["items"][0]) == (note["id"], "list", "Photoreceptors")


def test_changing_type_of_a_sent_card_replaces_it_and_says_so(client, doc, note, llm):
    client.post("/api/documents/%s/send" % doc["id"])
    llm["p"] = ScriptedLLM(reply(LIST))
    r = client.post("/api/jobs/%s/accept" % ask(client, note, "make it a list")["id"]).json()
    [n] = notes(client, doc)
    assert n["id"] != note["id"] and n["type"] == "list" and n["status"] == "new"
    assert "still in Anki" in r["message"]


def test_accept_is_refused_if_the_card_changed_meanwhile(client, doc, note, llm):
    llm["p"] = ScriptedLLM(reply(QA))
    job = ask(client, note)
    client.patch("/api/notes/%s" % note["id"], json={"back": "498 nm"})
    r = client.post("/api/jobs/%s/accept" % job["id"])
    assert r.status_code == 409 and "changed" in r.json()["detail"]


def test_discard(client, doc, note, llm):
    llm["p"] = ScriptedLLM(reply(QA))
    job = ask(client, note)
    assert client.post("/api/jobs/%s/discard" % job["id"]).json()["status"] == "discarded"
    assert client.post("/api/jobs/%s/accept" % job["id"]).status_code == 409
    assert notes(client, doc)[0]["front"] == note["front"]


def test_a_failed_edit_can_be_dismissed(client, note, llm):
    llm["p"] = ScriptedLLM(reply())
    job = ask(client, note)
    assert client.post("/api/jobs/%s/discard" % job["id"]).json()["status"] == "discarded"


def test_retrying_an_edit_uses_the_card_as_it_is_now(client, note, llm):
    llm["p"] = ScriptedLLM(reply(), reply(QA))
    job = ask(client, note)
    client.patch("/api/notes/%s" % note["id"], json={"back": "498 nm"})
    again = client.post("/api/jobs/%s/retry" % job["id"]).json()
    assert again["status"] == "done" and again["before"]["back"] == "498 nm" and again["focus"] == "shorter front"


def statuses(client, doc):
    return {j["id"]: j["status"] for j in client.get("/api/documents/%s/jobs" % doc["id"]).json()}


def test_asking_again_replaces_the_open_suggestion(client, doc, note, llm):
    llm["p"] = ScriptedLLM(reply(QA), reply(QA))
    first = ask(client, note)
    second = ask(client, note, "add a why")
    assert statuses(client, doc) == {first["id"]: "discarded", second["id"]: "done"}


def test_retrying_a_failed_edit_closes_the_failure(client, doc, note, llm):
    llm["p"] = ScriptedLLM(reply(), reply(QA))
    failed = ask(client, note)
    again = client.post("/api/jobs/%s/retry" % failed["id"]).json()
    assert statuses(client, doc) == {failed["id"]: "discarded", again["id"]: "done"}


def test_suggestions_for_other_cards_are_left_alone(client, doc, note, llm):
    other = client.post("/api/documents/%s/notes" % doc["id"], json={"type": "qa", "front": "Q", "back": "A"}).json()
    llm["p"] = ScriptedLLM(reply(QA), reply(QA))
    first = ask(client, note)
    second = ask(client, other)
    assert statuses(client, doc) == {first["id"]: "done", second["id"]: "done"}


def test_instruction_is_required(client, note):
    assert client.post("/api/notes/%s/ai-edit" % note["id"], json={"instruction": "  "}).status_code == 422


def test_a_reply_without_cards_fails_the_edit(client, note, llm):
    llm["p"] = ScriptedLLM(reply())
    job = ask(client, note)
    assert job["status"] == "failed" and "no card" in job["error"]


def test_edit_prompt_shares_the_generation_prefix():
    p, pages = load_profile(), ["Rods.", "Cones."]
    gen = build_messages(p, title="V", pages=pages, target="Rods.", target_pages=(1, 1), focus="", mode="highlight")
    edit = build_edit_messages(p, title="V", pages=pages, card={"type": "qa", "front": "F", "back": "B"},
                               source_text="Rods.", source_pages=(1, 1), instruction="shorter")
    assert gen[0] == edit[0]
    end = gen[1]["content"].index("</document>")
    assert gen[1]["content"][:end] == edit[1]["content"][:end]
