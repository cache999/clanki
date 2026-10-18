"""HTTP API for the browser UI, plus the built frontend as static files."""
import base64
import re
import shutil
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path

import json
from datetime import datetime, timezone

import httpx
from typing import Literal

from fastapi import Body, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from . import convert, web
from . import keys as keystore
from .anki_format import export_txt
from .anki_index import AnkiIndex
from .ankiconnect import AnkiConnect, AnkiError, AnkiUnavailable, SendResult
from .config import Config
from .doctext import chunk_pages, document_text, page_texts
from .generation import GENERATED_TAG, note_to_card, parse_cards, to_notes
from .jobs import JobRunner
from .llm import DEFAULT_MODEL, PROVIDER_MODELS, DeepSeek, LLMError, Usage, cost, is_peak
from .models import Document, Job, Note, Source
from .prompts import facet_vocabulary, load_profile
from .store import NOTE_BOOKKEEPING, NOTE_METADATA, Store
from .validators import validate

STATIC = Path(__file__).parent / "static"
KINDS = {".pdf": "pdf", ".pptx": "pptx", ".ppt": "pptx", ".odp": "pptx",
         ".docx": "docx", ".doc": "docx", ".odt": "docx"}
LEFT_OUT_FOCUS = "Card this content regardless of UKMLA relevance."
PARALLEL_JOBS = 3
INDEX_MAX_AGE_S = 600  # re-read the Anki collection on a status poll after this long


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
    source_id: str | None = None  # generate from this (region or image) source, with the selection's text
    focus: str = ""
    model: str | None = None


class TranscribeIn(BaseModel):
    page: int
    rect: list[float] | None = None  # a dragged box; none for a pasted screenshot
    image: str  # data URL
    model: str | None = None


class SourceTextIn(BaseModel):
    text: str


class UrlIn(BaseModel):
    url: str


class ExportIn(BaseModel):
    document_ids: list[str]
    scope: Literal["unsent", "all"] = "unsent"  # unsent: new and edited cards
    types: list[Literal["qa", "list"]] = ["qa", "list"]
    tag: str = ""  # this tag or one under it (NHB matches NHB::vision), on the card or its document
    mark_exported: bool = True
    preview: bool = False  # only count


IMAGE_TYPES = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg", b"GIF8": "gif", b"RIFF": "webp"}
MAX_IMAGE_BYTES = 20_000_000


def decode_image(data_url: str) -> tuple[bytes, str]:
    """The bytes and file extension of a base64 image data URL, checked by content."""
    m = re.fullmatch(r"data:image/[\w.+-]+;base64,([A-Za-z0-9+/=\s]+)", data_url)
    if not m:
        raise ValueError("send the image as a base64 data URL")
    data = base64.b64decode(m.group(1))
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("the image is too large (over 20 MB)")
    ext = next((e for magic, e in IMAGE_TYPES.items() if data.startswith(magic)), None)
    if ext is None or (ext == "webp" and data[8:12] != b"WEBP"):
        raise ValueError("not a PNG, JPEG, GIF or WebP image")
    return data, ext


class RetryIn(BaseModel):
    model: str | None = None


class EditIn(BaseModel):
    instruction: str
    model: str | None = None


def _name(n: Note) -> str:
    """A card's first field, short, for the undo history."""
    s = " ".join((n.front if n.type == "qa" else n.title).split()) or "(empty)"
    return s if len(s) <= 50 else s[:49] + "…"


def _content(n: Note) -> dict:
    """What a card says (and would send to Anki), without clanki's bookkeeping."""
    return n.model_dump(exclude=NOTE_BOOKKEEPING | NOTE_METADATA)


def _replacement_patch(n: Note) -> dict:
    """Fields that make an existing note say what n says (possibly switching its type)."""
    if n.type == "qa":
        return {"type": "qa", "front": n.front, "back": n.back, "why": n.why, "add_reverse": n.add_reverse,
                "reverse_prompt": n.reverse_prompt, "facets": n.facets, "kind": n.kind, "flags": n.flags,
                "title": "", "items": []}
    return {"type": "list", "title": n.title, "items": n.items, "why": n.why, "mnemonic": n.mnemonic,
            "full": n.full, "kind": n.kind, "flags": n.flags, "front": "", "back": "", "add_reverse": False,
            "reverse_prompt": ""}


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_model: str | None = None


class KeyIn(BaseModel):
    key: str


def create_app(cfg: Config, store: Store | None = None, anki: AnkiConnect | None = None,
               provider_for=None, jobs_inline: bool = False, web_client: httpx.Client | None = None) -> FastAPI:
    store = store or Store(cfg.data_dir / "clanki.db")
    anki = anki or AnkiConnect(cfg.anki_url)
    provider_for = provider_for or default_provider
    web_client = web_client or httpx.Client()
    files = cfg.data_dir / "files"
    app = FastAPI(title="clanki")

    def pages_for(doc_id: str) -> list[str]:
        cache = files / doc_id / "pages.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        pages = page_texts(files / doc_id / "document.pdf")
        cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        return pages

    # the student's Anki collection: duplicate warnings and facet vocabulary
    saved = store.get_setting("anki_index")
    index = {"now": AnkiIndex.from_dict(saved) if saved else AnkiIndex.empty()}
    index_lock = threading.Lock()

    def refresh_index() -> AnkiIndex:
        with index_lock:
            index["now"] = AnkiIndex.fetch(anki)
            store.set_setting("anki_index", index["now"].to_dict())
        return index["now"]

    def index_is_stale() -> bool:
        t = index["now"].refreshed_at
        return t is None or (datetime.now(timezone.utc) - datetime.fromisoformat(t)).total_seconds() >= INDEX_MAX_AGE_S

    def facet_counts() -> dict:
        return index["now"].facet_counts

    def image_path(src: Source) -> Path | None:
        return next((files / src.document_id / "images").glob(src.id + ".*"), None)

    def image_for(src: Source) -> str:
        p = image_path(src)
        if p is None:
            raise ValueError("the image for this source is missing")
        mime = {"jpg": "jpeg"}.get(p.suffix[1:], p.suffix[1:])
        return "data:image/%s;base64,%s" % (mime, base64.b64encode(p.read_bytes()).decode())

    jobs_kw = {"facet_counts": facet_counts, "image_for": image_for}
    runner = (JobRunner(store, pages_for, provider_for, **jobs_kw) if jobs_inline
              else JobRunner.threaded(store, pages_for, provider_for, workers=PARALLEL_JOBS, **jobs_kw))
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

    @app.post("/api/documents/url")
    def open_url(body: UrlIn) -> Document:
        """A web page's article (or a linked PDF), as a document."""
        try:
            title, pdf = web.page_to_pdf(body.url.strip(), web_client)
        except web.WebError as e:
            raise HTTPException(422, str(e))
        doc = store.add_document(title=title, filename=body.url.strip(), kind="web")
        (files / doc.id).mkdir(parents=True)
        (files / doc.id / "document.pdf").write_bytes(pdf)
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

    def get_source(doc_id: str, source_id: str) -> Source:
        s = store.get_source(source_id)
        if s is None or s.document_id != doc_id:
            raise HTTPException(404, "source not found")
        return s

    @app.patch("/api/sources/{source_id}")
    def correct_source(source_id: str, body: SourceTextIn) -> Source:
        s = store.get_source(source_id)
        if s is None:
            raise HTTPException(404, "source not found")
        return store.set_source_text(source_id, body.text)

    @app.post("/api/documents/{doc_id}/transcribe")
    def transcribe(doc_id: str, body: TranscribeIn):
        """Read a dragged box or a pasted screenshot into text (the source's text, when done)."""
        get_doc(doc_id)
        data, ext = decode_image(body.image)
        model = pick_model(body.model)
        src = store.add_source(Source(document_id=doc_id, kind="region" if body.rect else "image", page=body.page,
                                      text="", rects=[body.rect] if body.rect else []))
        (files / doc_id / "images").mkdir(parents=True, exist_ok=True)
        (files / doc_id / "images" / ("%s.%s" % (src.id, ext))).write_bytes(data)
        j = runner.submit(Job(document_id=doc_id, source_id=src.id, mode="transcribe",
                              pages=(body.page, body.page), target="", model=model))
        return {"job": store.get_job(j.id), "source": store.get_source(src.id)}

    # notes
    @app.get("/api/documents/{doc_id}/notes")
    def list_notes(doc_id: str) -> list[dict]:
        get_doc(doc_id)
        notes = store.list_notes(doc_id)
        return [{**n.model_dump(), "issues": [i.model_dump() for i in iss + in_anki]}
                for n, iss, in_anki in zip(notes, validate(notes), index["now"].check(notes))]

    @app.post("/api/documents/{doc_id}/notes")
    def add_note(doc_id: str, note: dict = Body()) -> Note:
        get_doc(doc_id)
        n = Note.model_validate({**note, "document_id": doc_id})
        with store.action(doc_id, "Add card: " + _name(n)):
            return store.add_note(n)

    @app.get("/api/notes/{note_id}")
    def note(note_id: str) -> Note:
        return get_note(note_id)

    @app.patch("/api/notes/{note_id}")
    def update_note(note_id: str, patch: dict = Body()) -> Note:
        n = get_note(note_id)
        what = ("Dismiss a flag" if set(patch) == {"flags"} else
                "Reverse card " + ("on" if patch["add_reverse"] else "off")
                if set(patch) <= {"add_reverse", "reverse_prompt"} and "add_reverse" in patch else "Edit card")
        with store.action(n.document_id, "%s: %s" % (what, _name(n))):
            return store.update_note(note_id, patch)

    @app.delete("/api/notes/{note_id}")
    def delete_note(note_id: str) -> Note:
        n = get_note(note_id)
        with store.action(n.document_id, "Delete card: " + _name(n)):
            return store.delete_note(note_id)

    @app.post("/api/notes/{note_id}/restore")
    def restore_note(note_id: str) -> Note:
        n = get_note(note_id)
        with store.action(n.document_id, "Restore card: " + _name(n)):
            return store.restore_note(note_id)

    # undo history
    def step_result(r: dict) -> dict:
        k = r["in_anki"]
        msg = (None if not k else "The removed card is still in Anki: delete it there if you don't want it."
               if k == 1 else "%d removed cards are still in Anki: delete them there if you don't want them." % k)
        return {"label": r["label"], "message": msg}

    @app.post("/api/documents/{doc_id}/undo")
    def undo(doc_id: str, to: int | None = None):
        get_doc(doc_id)
        return step_result(store.undo(doc_id, to))

    @app.post("/api/documents/{doc_id}/redo")
    def redo(doc_id: str, to: int | None = None):
        get_doc(doc_id)
        return step_result(store.redo(doc_id, to))

    @app.get("/api/documents/{doc_id}/history")
    def history(doc_id: str):
        get_doc(doc_id)
        return store.history(doc_id)

    # Anki
    @app.get("/api/documents/{doc_id}/export.txt")
    def export(doc_id: str, scope: str = "all"):
        doc = get_doc(doc_id)
        notes = [n for n in store.list_notes(doc_id) if scope == "all" or n.status != "sent"]
        text = export_txt([for_anki(doc, n) for n in notes], default_deck=doc.deck or cfg.default_deck)
        fname = re.sub(r"[^A-Za-z0-9._ -]+", "_", doc.title).strip() or "clanki"
        return PlainTextResponse(text, headers={
            "Content-Disposition": 'attachment; filename="%s_anki.txt"' % fname})

    @app.post("/api/export")
    def export_cards(body: ExportIn):
        """An import file of the chosen cards (cards with errors are left out); marks the new and
        edited ones exported, so Send skips them."""
        docs = [get_doc(d) for d in body.document_ids]
        tag = body.tag.strip().lower()
        chosen, with_errors = [], 0
        for doc in docs:
            notes = store.list_notes(doc.id)
            for n, iss in zip(notes, validate(notes)):
                tags = [t.lower() for t in doc.tags + n.tags]
                if (n.type not in body.types or (body.scope == "unsent" and n.status not in ("new", "edited"))
                        or (tag and not any(t == tag or t.startswith(tag + "::") for t in tags))):
                    continue
                if any(i.level == "error" for i in iss):
                    with_errors += 1
                else:
                    chosen.append((doc, n))
        if body.preview:
            return {"cards": len(chosen), "with_errors": with_errors}
        text = export_txt([for_anki(d, n) for d, n in chosen], default_deck=cfg.default_deck)
        if body.mark_exported:
            for _, n in chosen:
                if n.anki_note_id is None and n.status in ("new", "edited"):
                    store.mark_exported(n.id)
        name = re.sub(r"[^A-Za-z0-9._ -]+", "_", docs[0].title).strip() if len(docs) == 1 else "clanki"
        return PlainTextResponse(text, headers={"Content-Disposition": 'attachment; filename="%s_anki.txt"' % (name or "clanki"),
                                                "X-Clanki-Cards": str(len(chosen))})

    @app.post("/api/documents/{doc_id}/send")
    def send(doc_id: str):
        """Send new and edited cards to Anki. Cards with errors stay in clanki; cards imported from an
        export file are not sent (an edited one is updated by exporting it again)."""
        doc = get_doc(doc_id)
        notes = store.list_notes(doc_id)
        results: dict[str, SendResult] = {}
        ready = []
        for n, iss in zip(notes, validate(notes)):
            errors = [i.message for i in iss if i.level == "error"]
            if n.status == "exported":
                results[n.id] = SendResult(n.id, "skipped")
            elif n.exported_at and n.anki_note_id is None:
                results[n.id] = SendResult(n.id, "failed", None, "This card was imported into Anki from an export "
                                           "file: export it again (Shift+E) to update it there")
            elif errors and n.status != "sent":
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
            if body.source_id:  # a transcribed figure, with the text as the student corrected it
                src = store.set_source_text(get_source(doc.id, body.source_id).id, sel.text)
            else:
                src = store.add_source(Source(document_id=doc.id, **sel.model_dump()))
            mode = "figure" if src.kind in ("region", "image") else "highlight"
            jobs = [runner.submit(Job(document_id=doc.id, source_id=src.id, mode=mode,
                                      pages=(src.page, src.page), target=sel.text, focus=body.focus,
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
        prefix = (len(load_profile(facet_counts=facet_counts()).system) + sum(len(p) for p in pages)) // 4
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
        model = pick_model((body and body.model) or j.model)
        if j.mode == "edit":
            return submit_edit(get_note(j.note_id), j.focus, model)
        return resubmit(j, model=model)

    # AI edits of one card: a suggestion that waits for accept or discard
    def submit_edit(n: Note, instruction: str, model: str) -> Job:
        for old in store.list_jobs(n.document_id):  # a card has at most one open suggestion
            if old.mode == "edit" and old.note_id == n.id:
                if old.status in ("queued", "running"):
                    runner.cancel(old.id)
                elif old.status in ("done", "failed"):
                    store.update_job(old.id, status="discarded")
        src = store.get_source(n.source_id) if n.source_id else None
        pages = (src.page, src.page_end or src.page) if src else (1, 1)
        j = runner.submit(Job(document_id=n.document_id, source_id=n.source_id, note_id=n.id, mode="edit",
                              pages=pages, target=json.dumps(note_to_card(n), ensure_ascii=False),
                              focus=instruction, model=model, before=n.model_dump()))
        return store.get_job(j.id)

    @app.post("/api/notes/{note_id}/ai-edit")
    def ai_edit(note_id: str, body: EditIn) -> Job:
        n = get_note(note_id)
        if not body.instruction.strip():
            raise HTTPException(422, "say what to change")
        return submit_edit(n, body.instruction.strip(), pick_model(body.model))

    @app.post("/api/jobs/{job_id}/accept")
    def accept(job_id: str):
        j = get_job(job_id)
        if j.mode != "edit" or j.status != "done":
            raise HTTPException(409, "there is no suggestion to accept")
        n = store.get_note(j.note_id)
        if n is None or n.deleted:
            raise HTTPException(409, "the card was deleted")
        if _content(n) != _content(Note.model_validate(j.before)):
            raise HTTPException(409, "The card was changed after the suggestion was requested: discard it, or ask again.")
        first, *rest = to_notes(parse_cards(j.proposal), n.document_id, n.source_id)
        label = "Accept AI edit: " + _name(n) + (" (split into %d)" % (1 + len(rest)) if rest else "")
        with store.action(n.document_id, label):
            return accept_into(j, n, first, rest)

    def accept_into(j: Job, n: Note, first: Note, rest: list[Note]) -> dict:
        job_id = j.id
        message = None
        if first.type == n.type or n.anki_note_id is None:
            ids = [store.update_note(n.id, _replacement_patch(first)).id]
        else:  # Anki cannot change a note's type, so replace the card
            store.delete_note(n.id)
            ids = [store.add_note(first.model_copy(update={"tags": n.tags})).id]
            message = ("The card changed type, so clanki replaced it with a new card. The old card is still "
                       "in Anki: delete it there.")
        extra_tags = n.tags + ([GENERATED_TAG] if GENERATED_TAG not in n.tags else [])
        ids += [store.add_note(x.model_copy(update={"tags": extra_tags})).id for x in rest]
        return {"job": store.update_job(job_id, status="applied", note_ids=ids), "message": message}

    @app.post("/api/jobs/{job_id}/discard")
    def discard(job_id: str) -> Job:
        j = get_job(job_id)
        if j.mode == "edit" and j.status in ("done", "failed"):
            return store.update_job(job_id, status="discarded")
        return j

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
                "default_model": store.get_setting("default_model", DEFAULT_MODEL),
                "facets": facet_vocabulary(facet_counts=facet_counts())}

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
        st = anki.status()
        if st["connected"] and index_is_stale():
            try:
                refresh_index()
            except AnkiError as e:
                st["problems"].append("Could not read your Anki cards: %s" % e)
        return {**st, "index": index["now"].summary()}

    @app.post("/api/anki/refresh")
    def anki_refresh():
        return refresh_index().summary()

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
