"""LLM jobs: build the prompt, call the model, turn the reply into cards (or a suggestion, or a
transcription)."""
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from .doctext import document_text
from .generation import GenerationError, GenOutput, parse_output, to_notes
from .llm import LLMError
from .models import Job
from .prompts import build_edit_messages, build_messages, build_transcribe_messages, load_profile
from .store import Store

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 2
MAX_PAGE_CONTEXT = 4000  # characters of the page's text sent with an image


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRunner:
    """Runs jobs on a thread pool (inline when executor=None, for tests). pages_for gives a
    document's page texts; provider_for gives the LLM provider or raises LLMError; facet_counts
    gives the student's facet usage from Anki, for the prompt's vocabulary; image_for gives a
    region or image source's picture as a data URL."""

    def __init__(self, store: Store, pages_for: Callable[[str], list[str]], provider_for: Callable,
                 executor=None, facet_counts: Callable[[], dict] = dict, image_for: Callable | None = None):
        self.store = store
        self.pages_for = pages_for
        self.provider_for = provider_for
        self.executor = executor
        self.facet_counts = facet_counts
        self.image_for = image_for
        self._lock = threading.Lock()

    @classmethod
    def threaded(cls, store, pages_for, provider_for, workers: int = 3, **kw) -> "JobRunner":
        return cls(store, pages_for, provider_for, executor=ThreadPoolExecutor(workers, thread_name_prefix="job"), **kw)

    def submit(self, job: Job) -> Job:
        j = self.store.add_job(job)
        if self.executor is None:
            self._run(j.id)
        else:
            self.executor.submit(self._run, j.id)
        return self.store.get_job(j.id)

    def cancel(self, job_id: str) -> Job | None:
        with self._lock:
            j = self.store.get_job(job_id)
            if j and j.status in ("queued", "running"):
                return self.store.update_job(job_id, status="cancelled", finished_at=_now())
            return j

    def _finish(self, job_id: str, **fields) -> None:
        with self._lock:
            if self.store.get_job(job_id).status == "cancelled":
                keep = {k: v for k, v in fields.items() if k in ("usage", "cost_usd", "attempts")}
                self.store.update_job(job_id, **keep)
            else:
                self.store.update_job(job_id, finished_at=_now(), **fields)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self.store.get_job(job_id)
            if job is None or job.status != "queued":
                return
            self.store.update_job(job_id, status="running", started_at=_now())
        usage = dict(job.usage)
        spent = {"usage": usage, "cost_usd": 0.0, "attempts": 0}
        try:
            doc = self.store.get_document(job.document_id)
            if job.mode == "transcribe":
                return self._transcribe(job, spent)
            messages = self._messages(job, doc.title, self.pages_for(doc.id))
            provider = self.provider_for()
            out = self._complete(provider, messages, job.model, spent)
            if self.store.get_job(job_id).status == "cancelled":
                return self._finish(job_id, **spent)
            if job.mode == "edit":
                if not out.cards:
                    raise GenerationError("the model returned no card")
                return self._finish(job_id, status="done", proposal=[c.model_dump() for c in out.cards],
                                    flags=out.flags, **spent)
            notes = [self.store.add_note(n) for n in to_notes(out, doc.id, job.source_id)]
            self._finish(job_id, status="done", note_ids=[n.id for n in notes],
                         left_out=[x.model_dump() for x in out.left_out], flags=out.flags,
                         image_occlusion=out.image_occlusion_candidates, **spent)
        except (LLMError, GenerationError) as e:
            self._finish(job_id, status="failed", error=str(e), **spent)
        except Exception as e:  # keep the queue alive; the job shows what went wrong
            log.exception("job %s crashed", job_id)
            self._finish(job_id, status="failed", error="internal error: %s" % e, **spent)

    def _messages(self, job: Job, title: str, pages: list[str]) -> list[dict]:
        profile = load_profile(job.profile, facet_counts=self.facet_counts())
        if job.mode != "edit":
            return build_messages(profile, title=title, pages=pages, target=job.target,
                                  target_pages=job.pages, focus=job.focus, mode=job.mode)
        src = self.store.get_source(job.source_id) if job.source_id else None
        source_text = ""
        if src and src.kind != "chunk":
            source_text = src.text
        elif src:
            source_text = document_text(pages, src.page, src.page_end or src.page)
        return build_edit_messages(profile, title=title, pages=pages, card=json.loads(job.target),
                                   source_text=source_text, source_pages=job.pages, instruction=job.focus)

    def _transcribe(self, job: Job, spent: dict) -> None:
        """Read the source's image into its text."""
        src = self.store.get_source(job.source_id)
        pages = self.pages_for(job.document_id)
        page = pages[src.page - 1] if 0 < src.page <= len(pages) else ""
        messages = build_transcribe_messages(load_profile(job.profile), image=self.image_for(src),
                                             page_text=page[:MAX_PAGE_CONTEXT])
        r = self.provider_for().complete(messages, model=job.model, json_mode=False)
        _spend(spent, r)
        if self.store.get_job(job.id).status == "cancelled":
            return self._finish(job.id, **spent)
        if not r.text.strip():
            raise GenerationError("the model returned no text for the image")
        self.store.set_source_text(src.id, r.text.strip())
        self._finish(job.id, status="done", **spent)

    def _complete(self, provider, messages: list[dict], model: str, spent: dict) -> GenOutput:
        error = None
        for _ in range(MAX_ATTEMPTS):
            r = provider.complete(messages, model=model)
            _spend(spent, r)
            if r.finish_reason == "length":
                error = GenerationError("the reply was cut off: select a shorter passage")
                retry = "Your reply was cut off. Reply again, more concisely, with only the JSON object."
            else:
                try:
                    return parse_output(r.text)
                except GenerationError as e:
                    error = e
                    retry = "That reply could not be used: %s. Reply again with only the JSON object." % e
            messages = messages + [{"role": "assistant", "content": r.text}, {"role": "user", "content": retry}]
        raise error


def _spend(spent: dict, r) -> None:
    spent["attempts"] += 1
    spent["cost_usd"] += r.cost_usd
    for k in spent["usage"]:
        spent["usage"][k] += getattr(r.usage, k)
