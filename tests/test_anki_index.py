import pytest

from clanki.anki_format import BASIC, OVERLAP
from clanki.anki_index import AnkiIndex
from clanki.ankiconnect import AnkiConnect
from clanki.models import Note
from fake_anki import FakeAnki


@pytest.fixture
def fake():
    f = FakeAnki()
    f.add(BASIC, "Pharm::CVS", Front="<b>Sacubitril</b> (MoA, use) [2]", Back="Neprilysin inhibitor; HFrEF")
    f.add(BASIC, "Vision", Front="Rhodopsin peak absorption wavelength (value)", Back="~498 nm<br>(r: pigment?)",
          Add_Reverse="y")
    f.add(BASIC, "Anat", Front="Aorta (def)", Back="Main artery")
    f.add(OVERLAP, "Vision", Title="Retinal layers (outer to inner)", Original="Photoreceptors<br>Bipolar<br>Ganglion")
    return f


@pytest.fixture
def index(fake):
    return AnkiIndex.fetch(AnkiConnect(transport=fake.transport()))


def qa(front, back="x", **kw):
    return Note(document_id="d", type="qa", front=front, back=back, **kw)


def codes(issues):
    return [i.code for i in issues]


def test_fetch_reads_both_note_types_with_decks_and_facets(index):
    assert index.summary()["notes"] == 4 and index.refreshed_at
    assert index.facet_counts == {"moa": [1, "MoA"], "use": [1, "use"], "value": [1, "value"],
                                  "definition": [1, "definition"]}


def test_same_entity_and_a_shared_facet_is_a_duplicate(index):
    [issues] = index.check([qa("Sacubitril (MoA)")])
    assert codes(issues) == ["in_anki"]
    assert issues[0].level == "warning"
    assert issues[0].message == 'Similar card in Anki: "Sacubitril (MoA, use) [2]" → Neprilysin inhibitor; HFrEF (Pharm::CVS)'


def test_word_order_and_small_words_do_not_hide_a_duplicate(index):
    [issues] = index.check([qa("Peak absorption wavelength of rhodopsin (value)")])
    assert codes(issues) == ["in_anki"]


def test_an_exact_front_says_already_in_anki(index):
    [issues] = index.check([qa("Aorta (definition)")])
    assert issues[0].message.startswith('Similar card in Anki: "Aorta (def)"')
    [issues] = index.check([qa("aorta (def)")])
    assert issues[0].message.startswith('Already in Anki: "Aorta (def)"')


def test_a_different_facet_of_the_same_entity_is_not_a_duplicate(index):
    assert index.check([qa("Sacubitril (adverse effects)")]) == [[]]


def test_a_card_without_facets_matches_any_card_on_its_entity(index):
    assert codes(index.check([qa("Sacubitril")])[0]) == ["in_anki"]


def test_list_titles_are_checked_too(index):
    lst = Note(document_id="d", type="list", title="Retinal layers", items=["a", "b"])
    [issues] = index.check([lst])
    assert issues[0].message == 'Similar card in Anki: "Retinal layers (outer to inner)" → Photoreceptors Bipolar Ganglion (Vision)'


def test_a_reverse_card_sharing_a_back_with_a_reversed_anki_card_is_ambiguous(index):
    [issues] = index.check([qa("Iodopsin peak", "~498 nm", add_reverse=True, reverse_prompt="pigment?")])
    assert codes(issues) == ["anki_shared_back"]
    assert "Rhodopsin peak absorption wavelength (value)" in issues[0].message
    assert index.check([qa("Iodopsin peak", "~498 nm")]) == [[]]  # no reverse card, no ambiguity


def test_sent_and_deleted_cards_are_not_checked(index):
    sent = qa("Sacubitril (MoA)", anki_note_id=5, status="sent")
    gone = qa("Sacubitril (MoA)", deleted=True)
    assert index.check([sent, gone]) == [[], []]


def test_round_trips_through_a_dict(index):
    again = AnkiIndex.from_dict(index.to_dict())
    assert again.summary() == index.summary() and again.facet_counts == index.facet_counts
    assert codes(again.check([qa("Sacubitril (MoA)")])[0]) == ["in_anki"]


def test_an_empty_index_checks_nothing():
    empty = AnkiIndex.empty()
    assert empty.check([qa("Sacubitril (MoA)")]) == [[]]
    assert empty.summary() == {"notes": 0, "refreshed_at": None}
