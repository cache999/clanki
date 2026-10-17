import pytest

from clanki.models import Note, Source
from clanki.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "clanki.db")


@pytest.fixture
def doc(store):
    return store.add_document(title="Vision", filename="vision.pdf", kind="pdf")


def test_documents_round_trip(store, doc):
    assert doc.id and doc.created_at
    assert store.get_document(doc.id) == doc
    assert [d.id for d in store.list_documents()] == [doc.id]


def test_update_document_deck_and_tags(store, doc):
    d = store.update_document(doc.id, {"deck": "MVST1B::vision", "tags": ["NHB::vision"]})
    assert (d.deck, d.tags) == ("MVST1B::vision", ["NHB::vision"])
    assert store.get_document(doc.id).deck == "MVST1B::vision"


def test_unknown_document_update_fields_are_rejected(store, doc):
    with pytest.raises(ValueError):
        store.update_document(doc.id, {"id": "other"})


def test_notes_are_listed_in_creation_order(store, doc):
    a = store.add_note(Note(type="qa", front="A", back="1", document_id=doc.id))
    b = store.add_note(Note(type="list", title="B", items=["x", "y"], document_id=doc.id))
    assert a.id and a.created_at and a.status == "new"
    assert [n.id for n in store.list_notes(doc.id)] == [a.id, b.id]
    assert store.get_note(b.id).items == ["x", "y"]


def test_editing_a_sent_note_marks_it_edited(store, doc):
    n = store.add_note(Note(type="qa", front="A", back="1", document_id=doc.id))
    assert store.update_note(n.id, {"back": "2"}).status == "new"
    store.mark_sent(n.id, anki_note_id=1234)
    sent = store.get_note(n.id)
    assert (sent.status, sent.anki_note_id) == ("sent", 1234) and sent.sent_at
    assert store.update_note(n.id, {"back": "3"}).status == "edited"


def test_saving_unchanged_content_keeps_sent_status(store, doc):
    n = store.add_note(Note(type="qa", front="A", back="1", document_id=doc.id))
    store.mark_sent(n.id, anki_note_id=1)
    assert store.update_note(n.id, {"back": "1"}).status == "sent"


def test_bookkeeping_fields_cannot_be_patched(store, doc):
    n = store.add_note(Note(type="qa", front="A", back="1", document_id=doc.id))
    with pytest.raises(ValueError):
        store.update_note(n.id, {"status": "sent"})


def test_unknown_note_fields_cannot_be_patched(store, doc):
    n = store.add_note(Note(type="qa", front="A", back="1", document_id=doc.id))
    with pytest.raises(ValueError):
        store.update_note(n.id, {"frnt": "typo"})


def test_soft_delete_and_restore(store, doc):
    n = store.add_note(Note(type="qa", front="A", back="1", document_id=doc.id))
    store.delete_note(n.id)
    assert store.list_notes(doc.id) == []
    assert [x.id for x in store.list_notes(doc.id, include_deleted=True)] == [n.id]
    store.restore_note(n.id)
    assert [x.id for x in store.list_notes(doc.id)] == [n.id]


def test_sources_round_trip(store, doc):
    s = store.add_source(Source(document_id=doc.id, page=3, text="rods and cones",
                                rects=[[0.1, 0.2, 0.3, 0.02]]))
    assert s.id
    assert store.list_sources(doc.id) == [s]


def test_deleting_a_document_removes_its_notes_and_sources(store, doc):
    store.add_note(Note(type="qa", front="A", back="1", document_id=doc.id))
    store.add_source(Source(document_id=doc.id, page=1, text="t"))
    store.delete_document(doc.id)
    assert store.get_document(doc.id) is None
    assert store.list_notes(doc.id, include_deleted=True) == []
    assert store.list_sources(doc.id) == []


def test_missing_records_return_none(store):
    assert store.get_note("nope") is None
    assert store.get_document("nope") is None


def test_store_reopens_existing_database(tmp_path):
    s1 = Store(tmp_path / "c.db")
    d = s1.add_document(title="t", filename="t.pdf", kind="pdf")
    assert Store(tmp_path / "c.db").get_document(d.id) == d
