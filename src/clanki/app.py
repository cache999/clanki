"""HTTP API for the browser UI, plus the built frontend as static files."""
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from . import convert
from .anki_format import export_txt
from .ankiconnect import AnkiConnect, AnkiUnavailable, SendResult
from .config import Config
from .models import Document, Note, Source
from .store import Store
from .validators import validate

STATIC = Path(__file__).parent / "static"
KINDS = {".pdf": "pdf", ".pptx": "pptx", ".ppt": "pptx", ".odp": "pptx",
         ".docx": "docx", ".doc": "docx", ".odt": "docx"}


class DocumentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    deck: str | None = None
    tags: list[str] | None = None


class SourceIn(BaseModel):
    page: int
    text: str
    rects: list[list[float]] = []


def create_app(cfg: Config, store: Store | None = None, anki: AnkiConnect | None = None) -> FastAPI:
    store = store or Store(cfg.data_dir / "clanki.db")
    anki = anki or AnkiConnect(cfg.anki_url)
    files = cfg.data_dir / "files"
    app = FastAPI(title="clanki")

    @app.exception_handler(AnkiUnavailable)
    def _anki_down(request: Request, e: AnkiUnavailable):
        return JSONResponse({"detail": str(e)}, status_code=503)

    @app.exception_handler(ValueError)
    def _bad_value(request: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=422)

    def get_doc(doc_id: str) -> Document:
        d = store.get_document(doc_id)
        if d is None:
            raise HTTPException(404, "document not found")
        return d

    def get_note(note_id: str) -> Note:
        n = store.get_note(note_id)
        if n is None:
            raise HTTPException(404, "card not found")
        return n

    def for_anki(doc: Document, n: Note) -> Note:
        return n.model_copy(update={"tags": doc.tags + n.tags, "deck": n.deck or doc.deck})

    # documents
    @app.get("/api/documents")
    def list_documents() -> list[Document]:
        return store.list_documents()

    @app.post("/api/documents")
    def upload(file: UploadFile) -> Document:
        name = Path(file.filename or "document.pdf")
        kind = KINDS.get(name.suffix.lower())
        if kind is None:
            raise HTTPException(415, "Open a PDF, PPTX or DOCX file")
        (cfg.data_dir / "tmp").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cfg.data_dir / "tmp") as tmp:
            src = Path(tmp) / ("source" + name.suffix.lower())
            with src.open("wb") as f:
                shutil.copyfileobj(file.file, f)
            if kind == "pdf":
                pdf = src
            else:
                try:
                    pdf = convert.to_pdf(src, Path(tmp) / "out", soffice=convert.find_soffice(cfg.soffice))
                except convert.ConversionError as e:
                    raise HTTPException(422, str(e))
            doc = store.add_document(title=name.stem, filename=name.name, kind=kind)
            (files / doc.id).mkdir(parents=True)
            shutil.move(str(pdf), files / doc.id / "document.pdf")
        return doc

    @app.get("/api/documents/{doc_id}")
    def document(doc_id: str) -> Document:
        return get_doc(doc_id)

    @app.patch("/api/documents/{doc_id}")
    def update_document(doc_id: str, patch: DocumentPatch) -> Document:
        get_doc(doc_id)
        return store.update_document(doc_id, patch.model_dump(exclude_unset=True))

    @app.delete("/api/documents/{doc_id}")
    def delete_document(doc_id: str):
        get_doc(doc_id)
        store.delete_document(doc_id)
        shutil.rmtree(files / doc_id, ignore_errors=True)
        return {"ok": True}

    @app.get("/api/documents/{doc_id}/pdf")
    def pdf(doc_id: str):
        get_doc(doc_id)
        return FileResponse(files / doc_id / "document.pdf", media_type="application/pdf")

    # sources
    @app.get("/api/documents/{doc_id}/sources")
    def list_sources(doc_id: str) -> list[Source]:
        get_doc(doc_id)
        return store.list_sources(doc_id)

    @app.post("/api/documents/{doc_id}/sources")
    def add_source(doc_id: str, body: SourceIn) -> Source:
        get_doc(doc_id)
        return store.add_source(Source(document_id=doc_id, **body.model_dump()))

    # notes
    @app.get("/api/documents/{doc_id}/notes")
    def list_notes(doc_id: str) -> list[dict]:
        get_doc(doc_id)
        notes = store.list_notes(doc_id)
        return [{**n.model_dump(), "issues": [i.model_dump() for i in iss]}
                for n, iss in zip(notes, validate(notes))]

    @app.post("/api/documents/{doc_id}/notes")
    def add_note(doc_id: str, note: dict = Body()) -> Note:
        get_doc(doc_id)
        return store.add_note(Note.model_validate({**note, "document_id": doc_id}))

    @app.get("/api/notes/{note_id}")
    def note(note_id: str) -> Note:
        return get_note(note_id)

    @app.patch("/api/notes/{note_id}")
    def update_note(note_id: str, patch: dict = Body()) -> Note:
        get_note(note_id)
        return store.update_note(note_id, patch)

    @app.delete("/api/notes/{note_id}")
    def delete_note(note_id: str) -> Note:
        get_note(note_id)
        return store.delete_note(note_id)

    @app.post("/api/notes/{note_id}/restore")
    def restore_note(note_id: str) -> Note:
        get_note(note_id)
        return store.restore_note(note_id)

    # Anki
    @app.get("/api/documents/{doc_id}/export.txt")
    def export(doc_id: str, scope: str = "all"):
        doc = get_doc(doc_id)
        notes = [n for n in store.list_notes(doc_id) if scope == "all" or n.status != "sent"]
        text = export_txt([for_anki(doc, n) for n in notes], default_deck=doc.deck or cfg.default_deck)
        fname = re.sub(r"[^A-Za-z0-9._ -]+", "_", doc.title).strip() or "clanki"
        return PlainTextResponse(text, headers={
            "Content-Disposition": 'attachment; filename="%s_anki.txt"' % fname})

    @app.post("/api/documents/{doc_id}/send")
    def send(doc_id: str):
        """Send new and edited cards to Anki. Cards with errors stay in clanki."""
        doc = get_doc(doc_id)
        notes = store.list_notes(doc_id)
        results: dict[str, SendResult] = {}
        ready = []
        for n, iss in zip(notes, validate(notes)):
            errors = [i.message for i in iss if i.level == "error"]
            if errors and n.status != "sent":
                results[n.id] = SendResult(n.id, "failed", n.anki_note_id, "; ".join(errors))
            else:
                ready.append(for_anki(doc, n))
        for r in anki.send(ready, default_deck=doc.deck or cfg.default_deck):
            results[r.note_id] = r
            if r.action in ("added", "updated"):
                store.mark_sent(r.note_id, r.anki_note_id)
        out = [asdict(results[n.id]) for n in notes]
        summary = {a: sum(r["action"] == a for r in out) for a in ("added", "updated", "skipped", "failed")}
        return {"results": out, "summary": summary}

    @app.get("/api/anki/status")
    def anki_status():
        return anki.status()

    @app.get("/api/anki/decks")
    def anki_decks() -> list[str]:
        return anki.deck_names()

    if (STATIC / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="ui")
    else:
        @app.get("/", response_class=HTMLResponse)
        def no_ui():
            return "<p>clanki API is running. Build the UI: <code>cd frontend && npm run build</code></p>"

    return app
