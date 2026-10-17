import httpx
import pytest

from clanki.anki_format import BASIC, BASIC_FIELDS, OVERLAP, OVERLAP_FIELDS
from clanki.ankiconnect import AnkiConnect, AnkiUnavailable
from clanki.models import Note

from fake_anki import FakeAnki


@pytest.fixture
def anki():
    return FakeAnki()


@pytest.fixture
def client(anki):
    return AnkiConnect(transport=anki.transport())


def test_status_ok_when_note_types_match(client):
    assert client.status() == {"connected": True, "version": 6, "problems": []}


def test_status_reports_missing_why_field():
    fake = FakeAnki(models={BASIC: ["Front", "Back", "Add Reverse"], OVERLAP: list(OVERLAP_FIELDS)})
    st = AnkiConnect(transport=fake.transport()).status()
    assert st["connected"]
    assert st["problems"] == ["Note type 'Basic (optional reversed card)' fields should start with: "
                              "Front, Back, Add Reverse, Why"]


def test_status_reports_missing_note_type():
    fake = FakeAnki(models={BASIC: list(BASIC_FIELDS)})
    assert AnkiConnect(transport=fake.transport()).status()["problems"] == [
        "Note type 'Cloze (overlapping)' not found in Anki"]


def test_extra_trailing_fields_are_fine():
    fake = FakeAnki(models={BASIC: BASIC_FIELDS + ["Extra"], OVERLAP: list(OVERLAP_FIELDS)})
    assert AnkiConnect(transport=fake.transport()).status()["problems"] == []


def test_status_when_anki_is_not_running():
    def refuse(request):
        raise httpx.ConnectError("refused")
    st = AnkiConnect(transport=httpx.MockTransport(refuse)).status()
    assert st == {"connected": False, "version": None,
                  "problems": ["AnkiConnect not reachable at http://127.0.0.1:8765: is Anki open "
                               "with the AnkiConnect add-on?"]}


def test_call_raises_unavailable_when_not_running():
    def refuse(request):
        raise httpx.ConnectError("refused")
    with pytest.raises(AnkiUnavailable):
        AnkiConnect(transport=httpx.MockTransport(refuse)).call("version")


def test_send_adds_new_notes_to_their_decks(client, anki):
    a = Note(id="a", type="qa", front="Capital of France", back="Paris", add_reverse=True,
             reverse_prompt="country?", tags=["geo"])
    b = Note(id="b", type="list", title="T", items=["x", "y"], deck="Other")
    results = client.send([a, b], default_deck="MVST1B::vision")
    assert [(r.note_id, r.action, r.error) for r in results] == [("a", "added", None), ("b", "added", None)]
    added = {r.note_id: anki.notes[r.anki_note_id] for r in results}
    assert added["a"]["deckName"] == "MVST1B::vision"
    assert added["a"]["fields"]["Back"] == "Paris<br>(r: country?)"
    assert added["a"]["tags"] == ["geo"]
    assert added["b"]["modelName"] == OVERLAP and added["b"]["deckName"] == "Other"
    assert {"MVST1B::vision", "Other"} <= anki.decks


def test_send_reports_duplicates_without_adding(client, anki):
    client.send([Note(id="a", type="qa", front="F", back="B")], default_deck="D")
    [r] = client.send([Note(id="b", type="qa", front="F", back="other")], default_deck="D")
    assert (r.action, r.anki_note_id) == ("failed", None)
    assert "duplicate" in r.error
    assert len(anki.notes) == 1


def test_send_updates_edited_notes_and_skips_unchanged(client, anki):
    [r] = client.send([Note(id="a", type="qa", front="F", back="B")], default_deck="D")
    edited = Note(id="a", type="qa", front="F", back="B2", status="edited", anki_note_id=r.anki_note_id)
    sent = Note(id="c", type="qa", front="G", back="C", status="sent", anki_note_id=999)
    results = client.send([edited, sent], default_deck="D")
    assert [(x.note_id, x.action) for x in results] == [("a", "updated"), ("c", "skipped")]
    assert anki.notes[r.anki_note_id]["fields"]["Back"] == "B2"


def test_updating_a_note_deleted_in_anki_fails_cleanly(client):
    gone = Note(id="a", type="qa", front="F", back="B", status="edited", anki_note_id=42)
    [r] = client.send([gone], default_deck="D")
    assert r.action == "failed" and "not found" in r.error.lower()
