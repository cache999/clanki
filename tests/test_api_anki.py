"""clanki's view of the student's Anki collection: duplicate warnings and the facet vocabulary."""
import json

import httpx
import keyring
import pytest
from fastapi.testclient import TestClient

import clanki.app
from clanki.anki_format import BASIC
from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from fake_anki import FakeAnki
from fake_keyring import MemoryKeyring
from fake_llm import ScriptedLLM
from make_pdf import make_pdf


def closed_anki():
    def refuse(request):
        raise httpx.ConnectError("connection refused")
    return AnkiConnect(transport=httpx.MockTransport(refuse))


@pytest.fixture
def fake():
    f = FakeAnki()
    f.add(BASIC, "Pharm::CVS", Front="Sacubitril (MoA, use) [2]", Back="Neprilysin inhibitor; HFrEF")
    for bug in ("Staph aureus", "Strep pyogenes", "E. coli", "Klebsiella", "Pseudomonas"):
        f.add(BASIC, "Micro", Front="%s (morphology)" % bug, Back="x")
    return f


@pytest.fixture
def llm():
    return {"p": ScriptedLLM()}


def make_client(tmp_path, anki, llm=None):
    app = create_app(Config(data_dir=tmp_path / "d"), anki=anki, jobs_inline=True,
                     provider_for=(lambda: llm["p"]) if llm else None)
    return TestClient(app)


@pytest.fixture
def client(tmp_path, fake, llm, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield make_client(tmp_path, AnkiConnect(transport=fake.transport()), llm)
    keyring.set_keyring(old)


@pytest.fixture
def doc(client):
    pdf = make_pdf([["Sacubitril inhibits neprilysin."]])
    return client.post("/api/documents", files={"file": ("pharm.pdf", pdf, "application/pdf")}).json()


def add_qa(client, doc, front, back="x"):
    return client.post("/api/documents/%s/notes" % doc["id"], json={"type": "qa", "front": front, "back": back}).json()


def issues(client, doc):
    return {n["front"]: [i["code"] for i in n["issues"]] for n in client.get("/api/documents/%s/notes" % doc["id"]).json()}


def test_status_reads_the_collection_once_and_reports_it(client, fake):
    st = client.get("/api/anki/status").json()
    assert st["connected"] and st["index"]["notes"] == 6 and st["index"]["refreshed_at"]
    client.get("/api/anki/status")
    assert fake.calls.count("findNotes") == 2  # one per note type, not again on the next poll


def test_a_stale_index_is_read_again(client, fake, monkeypatch):
    client.get("/api/anki/status")
    monkeypatch.setattr(clanki.app, "INDEX_MAX_AGE_S", 0)
    client.get("/api/anki/status")
    assert fake.calls.count("findNotes") == 4


def test_refresh_on_demand(client, fake):
    client.get("/api/anki/status")
    fake.add(BASIC, Front="Ivabradine (MoA)", Back="If blocker")
    assert client.post("/api/anki/refresh").json()["notes"] == 7


def test_refresh_needs_anki(tmp_path):
    assert make_client(tmp_path, closed_anki()).post("/api/anki/refresh").status_code == 503


def test_cards_that_repeat_anki_are_flagged(client, doc):
    client.get("/api/anki/status")
    add_qa(client, doc, "Sacubitril (MoA)")
    add_qa(client, doc, "Sacubitril (adverse effects)")
    assert issues(client, doc) == {"Sacubitril (MoA)": ["in_anki"], "Sacubitril (adverse effects)": []}


def test_warnings_still_show_while_anki_is_closed(tmp_path, client, doc):
    client.get("/api/anki/status")
    add_qa(client, doc, "Sacubitril (MoA)")
    again = make_client(tmp_path, closed_anki())
    assert again.get("/api/anki/status").json()["index"]["notes"] == 6
    assert issues(again, doc) == {"Sacubitril (MoA)": ["in_anki"]}


def test_the_students_facets_reach_the_prompt_and_settings(client, doc, llm):
    reply = {"cards": [{"type": "qa", "front": "Sacubitril (class)", "back": "ARNI"}], "left_out": [],
             "image_occlusion_candidates": [], "flags": []}
    llm["p"] = ScriptedLLM(json.dumps(reply))
    assert "morphology" not in client.get("/api/settings").json()["facets"]
    client.get("/api/anki/status")
    assert client.get("/api/settings").json()["facets"][-1] == "morphology"
    sel = {"page": 1, "text": "Sacubitril inhibits neprilysin.", "rects": []}
    client.post("/api/documents/%s/generate" % doc["id"], json={"mode": "selection", "selection": sel})
    system = llm["p"].calls[0]["messages"][0]["content"]
    assert ", why, morphology\n" in system
