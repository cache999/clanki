"""SQLite persistence. Each record is stored whole as JSON next to the few columns that are
queried, so new card fields need no schema migration."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import Document, Note, Source

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, document_id TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY, document_id TEXT, deleted INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sources_doc ON sources(document_id);
CREATE INDEX IF NOT EXISTS notes_doc ON notes(document_id);
"""

DOCUMENT_EDITABLE = {"title", "deck", "tags"}
NOTE_BOOKKEEPING = {"id", "guid", "document_id", "status", "deleted", "anki_note_id",
                    "created_at", "updated_at", "sent_at"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return uuid.uuid4().hex


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(_SCHEMA)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    # documents
    def add_document(self, *, title: str, filename: str, kind: str) -> Document:
        d = Document(id=_id(), title=title, filename=filename, kind=kind, created_at=_now())
        with self._db() as db:
            db.execute("INSERT INTO documents VALUES (?, ?)", (d.id, d.model_dump_json()))
        return d

    def get_document(self, doc_id: str) -> Document | None:
        with self._db() as db:
            row = db.execute("SELECT data FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return Document.model_validate_json(row[0]) if row else None

    def list_documents(self) -> list[Document]:
        with self._db() as db:
            rows = db.execute("SELECT data FROM documents ORDER BY rowid").fetchall()
        return [Document.model_validate_json(r[0]) for r in rows]

    def update_document(self, doc_id: str, patch: dict) -> Document | None:
        if set(patch) - DOCUMENT_EDITABLE:
            raise ValueError("cannot update: %s" % ", ".join(sorted(set(patch) - DOCUMENT_EDITABLE)))
        d = self.get_document(doc_id)
        if d is None:
            return None
        d = Document.model_validate({**d.model_dump(), **patch})
        with self._db() as db:
            db.execute("UPDATE documents SET data = ? WHERE id = ?", (d.model_dump_json(), doc_id))
        return d

    def delete_document(self, doc_id: str) -> None:
        with self._db() as db:
            for table in ("notes", "sources"):
                db.execute("DELETE FROM %s WHERE document_id = ?" % table, (doc_id,))
            db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # sources
    def add_source(self, s: Source) -> Source:
        s = s.model_copy(update={"id": _id(), "created_at": _now()})
        with self._db() as db:
            db.execute("INSERT INTO sources VALUES (?, ?, ?)", (s.id, s.document_id, s.model_dump_json()))
        return s

    def list_sources(self, doc_id: str) -> list[Source]:
        with self._db() as db:
            rows = db.execute("SELECT data FROM sources WHERE document_id = ? ORDER BY rowid",
                              (doc_id,)).fetchall()
        return [Source.model_validate_json(r[0]) for r in rows]

    # notes
    def _put_note(self, db, n: Note) -> None:
        db.execute("INSERT OR REPLACE INTO notes VALUES (?, ?, ?, ?)",
                   (n.id, n.document_id, int(n.deleted), n.model_dump_json()))

    def add_note(self, n: Note) -> Note:
        now = _now()
        n = n.model_copy(update={"id": _id(), "status": "new", "deleted": False,
                                 "anki_note_id": None, "created_at": now, "updated_at": now})
        with self._db() as db:
            self._put_note(db, n)
        return n

    def get_note(self, note_id: str) -> Note | None:
        with self._db() as db:
            row = db.execute("SELECT data FROM notes WHERE id = ?", (note_id,)).fetchone()
        return Note.model_validate_json(row[0]) if row else None

    def list_notes(self, doc_id: str, include_deleted: bool = False) -> list[Note]:
        sql = "SELECT data FROM notes WHERE document_id = ?" + ("" if include_deleted else " AND deleted = 0")
        with self._db() as db:
            rows = db.execute(sql + " ORDER BY rowid", (doc_id,)).fetchall()
        return [Note.model_validate_json(r[0]) for r in rows]

    def _replace(self, note_id: str, **update) -> Note | None:
        n = self.get_note(note_id)
        if n is None:
            return None
        n = Note.model_validate({**n.model_dump(), **update, "updated_at": _now()})
        with self._db() as db:
            self._put_note(db, n)
        return n

    def update_note(self, note_id: str, patch: dict) -> Note | None:
        """Change card content. A note already in Anki becomes 'edited' so the next send
        updates it there."""
        bad = (set(patch) & NOTE_BOOKKEEPING) | (set(patch) - set(Note.model_fields))
        if bad:
            raise ValueError("cannot update: %s" % ", ".join(sorted(bad)))
        n = self.get_note(note_id)
        if n is None:
            return None
        changed = any(getattr(n, k) != v for k, v in patch.items())
        status = "edited" if changed and n.status == "sent" else n.status
        return self._replace(note_id, **patch, status=status)

    def mark_sent(self, note_id: str, anki_note_id: int) -> Note | None:
        return self._replace(note_id, status="sent", anki_note_id=anki_note_id, sent_at=_now())

    def delete_note(self, note_id: str) -> Note | None:
        return self._replace(note_id, deleted=True)

    def restore_note(self, note_id: str) -> Note | None:
        return self._replace(note_id, deleted=False)
