"""HTTP API for the browser UI, plus the built frontend as static files."""
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from . import convert
from . import keys as keystore
from .anki_format import export_txt
from .ankiconnect import AnkiConnect, AnkiUnavailable, SendResult
from .config import Config
from .doctext import chunk_pages, document_text, page_texts
from .jobs import JobRunner
from .llm import DEFAULT_MODEL, PROVIDER_MODELS, DeepSeek, LLMError, Usage, cost, is_peak
from .models import Document, Job, Note, Source
from .prompts import load_profile
from .store import Store
from .validators import validate

STATIC = Path(__file__).parent / "static"
KINDS = {".pdf": "pdf", ".pptx": "pptx", ".ppt": "pptx", ".odp": "pptx",
         ".docx": "docx", ".doc": "docx", ".odt": "docx"}
LEFT_OUT_FOCUS = "Card this content regardless of UKMLA relevance."
PARALLEL_JOBS = 3


def default_provider():
    key = keystore.get_key("deepseek")
    if not key:
        raise LLMError("No DeepSeek API key: add one in Settings, or set DEEPSEEK_API_KEY")
    return DeepSeek(key)


class DocumentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    deck: str | None = None
    tags: list[str] | None = None


class SourceIn(BaseModel):
    page: int
    text: str
    rects: list[list[float]] = []


class GenerateIn(BaseModel):
    mode: Literal["selection", "document"]
    selection: SourceIn | None = None
    focus: str = ""
    model: str | None = None


class RetryIn(BaseModel):
    model: str | None = None


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_model: str | None = None


class KeyIn(BaseModel):
    key: str


def create_app(cfg: Config, store: Store | None = None, anki: AnkiConnect | None = None,
               provider_for=None, jobs_inline: bool = False) -> FastAPI:
    store = store or Store(cfg.data_dir / "clanki.db")
    anki = anki or AnkiConnect(cfg.anki_url)
    provider_for = provider_for or default_provider
    files = cfg.data_dir / "files"
    app = FastAPI(title="clanki")

    def pages_for(doc_id: str) -> list[str]:
        cache = files / doc_id / "pages.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        pages = page_texts(files / doc_id / "document.pdf")
        cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        return pages

    runner = (JobRunner(store, pages_for, provider_for) if jobs_inline
              else JobRunner.threaded(store, pages_for, provider_for, workers=PARALLEL_JOBS))
    store.fail_unfinished_jobs()

    def pick_model(model: str | None) -> str:
        model = model or store.get_setting("default_model", DEFAULT_MODEL)
        if model not in PROVIDER_MODELS["deepseek"]:
            raise HTTPException(422, "unknown model %r" % model)
        return model

    def get_job(job_id: str) -> Job:
        j = store.get_job(job_id)
        if j is None:
            raise HTTPException(404, "job not found")
        return j

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

    # generation
    @app.post("/api/documents/{doc_id}/generate")
    def generate(doc_id: str, body: GenerateIn):
        doc = get_doc(doc_id)
        model = pick_model(body.model)
        if body.mode == "selection":
            sel = body.selection
            if sel is None or not sel.text.strip():
                raise HTTPException(422, "select some text first")
            src = store.add_source(Source(document_id=doc.id, **sel.model_dump()))
            jobs = [runner.submit(Job(document_id=doc.id, source_id=src.id, mode="highlight",
                                      pages=(sel.page, sel.page), target=sel.text, focus=body.focus,
                                      model=model))]
        else:
            pages = pages_for(doc.id)
            chunks = chunk_pages(pages)
            if not chunks:
                raise HTTPException(422, "No text found in this document (a scan?). Text recognition "
                                         "for scans comes later.")
            jobs = []
            for a, b in chunks:
                src = store.add_source(Source(document_id=doc.id, kind="chunk", page=a, page_end=b, text=""))
                jobs.append(runner.submit(Job(document_id=doc.id, source_id=src.id, mode="chunk",
                                              pages=(a, b), target=document_text(pages, a, b),
                                              focus=body.focus, model=model)))
        return {"jobs": [store.get_job(j.id) for j in jobs]}

    @app.get("/api/documents/{doc_id}/estimate")
    def estimate(doc_id: str, model: str | None = None):
        """Rough cost of whole-document generation: tokens ≈ characters / 4, the document prefix
        cached after the first parallel batch, ~3k reasoning tokens per chunk."""
        get_doc(doc_id)
        model = pick_model(model)
        pages = pages_for(doc_id)
        chunks = chunk_pages(pages)
        prefix = (len(load_profile().system) + sum(len(p) for p in pages)) // 4
        hit = miss = out = 0
        for i, (a, b) in enumerate(chunks):
            target = sum(len(p) for p in pages[a - 1:b]) // 4
            if i < PARALLEL_JOBS:
                miss += prefix + target
            else:
                hit, miss = hit + prefix, miss + target
            out += int(target * 0.8) + 3000
        now = datetime.now(timezone.utc)
        usage = Usage(cache_hit=hit, cache_miss=miss, output=out, reasoning=0)
        return {"chunks": len(chunks), "input_tokens": hit + miss, "output_tokens": out, "model": model,
                "cost_usd": round(cost(model, usage, now), 4), "peak": is_peak(now)}

    @app.get("/api/documents/{doc_id}/jobs")
    def list_jobs(doc_id: str) -> list[Job]:
        get_doc(doc_id)
        return store.list_jobs(doc_id)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> Job:
        return get_job(job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> Job:
        get_job(job_id)
        return runner.cancel(job_id)

    def resubmit(j: Job, **update) -> Job:
        fields = j.model_dump(include={"document_id", "source_id", "mode", "pages", "target", "focus",
                                       "profile", "model"})
        new = runner.submit(Job(**{**fields, **update}))
        return store.get_job(new.id)

    @app.post("/api/jobs/{job_id}/retry")
    def retry_job(job_id: str, body: RetryIn | None = None) -> Job:
        j = get_job(job_id)
        return resubmit(j, model=pick_model((body and body.model) or j.model))

    @app.post("/api/jobs/{job_id}/left-out/{index}")
    def card_left_out(job_id: str, index: int) -> Job:
        j = get_job(job_id)
        if not 0 <= index < len(j.left_out):
            raise HTTPException(404, "no such left-out item")
        return resubmit(j, mode="highlight", target=j.left_out[index]["text"], focus=LEFT_OUT_FOCUS)

    # settings
    def settings():
        return {"providers": {"deepseek": {"models": PROVIDER_MODELS["deepseek"],
                                           "key": keystore.key_status("deepseek")}},
                "default_model": store.get_setting("default_model", DEFAULT_MODEL)}

    @app.get("/api/settings")
    def get_settings():
        return settings()

    @app.put("/api/settings")
    def put_settings(body: SettingsIn):
        if body.default_model is not None:
            store.set_setting("default_model", pick_model(body.default_model))
        return settings()

    @app.put("/api/settings/keys/{provider}")
    def put_key(provider: str, body: KeyIn):
        try:
            keystore.set_key(provider, body.key)
        except keystore.KeyStoreError as e:
            raise HTTPException(422, str(e))
        return keystore.key_status(provider)

    @app.delete("/api/settings/keys/{provider}")
    def delete_key(provider: str):
        keystore.delete_key(provider)
        return keystore.key_status(provider)

    @app.post("/api/settings/keys/{provider}/test")
    def test_key(provider: str):
        keystore.key_status(provider)  # validates the provider name
        try:
            provider_for().check()
        except LLMError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "error": None}

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
