import json

import pytest

from clanki.jobs import JobRunner
from clanki.llm import LLMError
from clanki.models import Job, Source
from clanki.store import Store

from fake_llm import ScriptedLLM

GOOD = json.dumps({
    "cards": [{"type": "qa", "kind": "fact", "front": "Rhodopsin peak absorption (value + unit)", "back": "~498 nm",
               "add_reverse": True, "reverse_prompt": "visual pigment with this peak?"},
              {"type": "list", "kind": "set", "title": "Retinal layers (outer to inner)",
               "items": ["Photoreceptors", "Bipolar cells", "Ganglion cells", "Nerve fibres"]}],
    "left_out": [{"text": "Reading list", "reason": "not testable"}],
    "image_occlusion_candidates": ["p.2 retina diagram"],
    "flags": ["source date unclear"],
})


class ManualExecutor:
    """Holds submitted work until run() so tests control timing."""

    def __init__(self):
        self.pending = []

    def submit(self, fn, *args):
        self.pending.append((fn, args))

    def run(self):
        while self.pending:
            fn, args = self.pending.pop(0)
            fn(*args)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "c.db")


@pytest.fixture
def doc(store):
    return store.add_document(title="Vision", filename="v.pdf", kind="pdf")


def runner(store, llm, executor=None):
    pages = ["Rods and cones.", "Rhodopsin absorbs maximally near 498 nm."]
    return JobRunner(store, pages_for=lambda doc_id: pages, provider_for=lambda: llm,
                     executor=executor)


def job(store, doc, **kw):
    s = store.add_source(Source(document_id=doc.id, page=2, text="Rhodopsin absorbs maximally near 498 nm."))
    return Job(document_id=doc.id, source_id=s.id, mode="highlight", pages=(2, 2), target=s.text, **kw)


def test_a_successful_job_makes_cards_and_records_what_happened(store, doc):
    llm = ScriptedLLM(GOOD)
    j = runner(store, llm).submit(job(store, doc, focus="value", model="deepseek-v4-pro"))
    done = store.get_job(j.id)
    assert done.status == "done" and done.error is None and done.attempts == 1
    notes = store.list_notes(doc.id)
    assert [n.id for n in notes] == done.note_ids
    assert {n.source_id for n in notes} == {j.source_id}
    assert notes[0].reverse_prompt == "visual pigment with this peak?" and notes[1].type == "list"
    assert done.left_out == [{"text": "Reading list", "reason": "not testable"}]
    assert done.flags == ["source date unclear"] and done.image_occlusion == ["p.2 retina diagram"]
    assert done.usage == {"cache_hit": 100, "cache_miss": 50, "output": 20, "reasoning": 5}
    assert done.cost_usd == pytest.approx(0.001)
    assert done.started_at and done.finished_at
    [call] = llm.calls
    assert call["model"] == "deepseek-v4-pro"
    assert "Focus: value" in call["messages"][1]["content"]
    assert "[p.1]\nRods and cones." in call["messages"][1]["content"]


def test_an_unusable_reply_is_retried_once_with_the_reason(store, doc):
    llm = ScriptedLLM("not json", GOOD)
    j = runner(store, llm).submit(job(store, doc))
    done = store.get_job(j.id)
    assert done.status == "done" and done.attempts == 2
    assert done.cost_usd == pytest.approx(0.002) and done.usage["output"] == 40
    retry = llm.calls[1]["messages"]
    assert retry[-2] == {"role": "assistant", "content": "not json"}
    assert "not valid JSON" in retry[-1]["content"]


def test_two_unusable_replies_fail_the_job_without_cards(store, doc):
    j = runner(store, ScriptedLLM("nope", '{"cards": "x"}')).submit(job(store, doc))
    done = store.get_job(j.id)
    assert done.status == "failed" and "cards" in done.error
    assert done.cost_usd == pytest.approx(0.002)
    assert store.list_notes(doc.id) == []


def test_a_cut_off_reply_is_retried_then_reported(store, doc):
    llm = ScriptedLLM('{"cards": [', '{"cards": [', finish="length")
    done = store.get_job(runner(store, llm).submit(job(store, doc)).id)
    assert done.status == "failed" and "cut off" in done.error


def test_provider_errors_fail_the_job_with_their_message(store, doc):
    done = store.get_job(runner(store, ScriptedLLM(LLMError("DeepSeek rejected the API key"))).submit(job(store, doc)).id)
    assert (done.status, done.error) == ("failed", "DeepSeek rejected the API key")


def test_missing_key_fails_the_job(store, doc):
    def no_key():
        raise LLMError("No DeepSeek API key")
    r = JobRunner(store, pages_for=lambda d: ["x"], provider_for=no_key)
    done = store.get_job(r.submit(job(store, doc)).id)
    assert (done.status, done.error) == ("failed", "No DeepSeek API key")


def test_cancelling_a_queued_job(store, doc):
    ex = ManualExecutor()
    r = runner(store, ScriptedLLM(GOOD), executor=ex)
    j = r.submit(job(store, doc))
    assert store.get_job(j.id).status == "queued"
    r.cancel(j.id)
    ex.run()
    assert store.get_job(j.id).status == "cancelled" and store.list_notes(doc.id) == []


def test_cancelling_a_running_job_discards_its_cards(store, doc):
    ex = ManualExecutor()
    holder = {}
    llm = ScriptedLLM(GOOD, on_call=lambda: holder["r"].cancel(holder["id"]))
    r = holder["r"] = runner(store, llm, executor=ex)
    holder["id"] = r.submit(job(store, doc)).id
    ex.run()
    done = store.get_job(holder["id"])
    assert done.status == "cancelled" and done.cost_usd == pytest.approx(0.001)
    assert store.list_notes(doc.id) == []


def test_unfinished_jobs_are_failed_on_restart(store, doc):
    ex = ManualExecutor()
    j = runner(store, ScriptedLLM(GOOD), executor=ex).submit(job(store, doc))
    store.fail_unfinished_jobs()
    done = store.get_job(j.id)
    assert done.status == "failed" and "restarted" in done.error


def test_jobs_are_listed_newest_first(store, doc):
    r = runner(store, ScriptedLLM(GOOD, GOOD))
    a, b = r.submit(job(store, doc)), r.submit(job(store, doc))
    assert [x.id for x in store.list_jobs(doc.id)] == [b.id, a.id]
