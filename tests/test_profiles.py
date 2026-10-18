"""Prompt profiles: medical (UKMLA), general knowledge, and machine-learning papers (MathJax)."""
import json

import keyring
import pytest
from fastapi.testclient import TestClient

from clanki.anki_format import overlap_fields
from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from clanki.generation import parse_output
from clanki.models import Note
from clanki.prompts import build_messages, list_profiles, load_profile
from clanki.validators import validate
from fake_anki import FakeAnki
from fake_keyring import MemoryKeyring
from fake_llm import ScriptedLLM
from make_pdf import make_pdf

NAMES = {"medical_ukmla", "general", "ml_papers"}


def example_of(system: str) -> str:
    rest = system.split("in exactly this shape", 1)[1]
    return rest[rest.index("{"):rest.index("\n}\n") + 2]


def test_three_profiles_each_complete():
    profiles = {p.name: p for p in list_profiles()}
    assert set(profiles) == NAMES
    for p in profiles.values():
        assert p.label and p.transcribe and p.scope_none and p.left_out_focus
        assert "{EXAMPLE}" not in p.system and "{FACETS}" not in p.system and "JSON" in p.system
        assert parse_output(example_of(p.system)).cards


def test_only_the_medical_profile_is_about_the_ukmla():
    assert "UKMLA" in load_profile("medical_ukmla").system
    for name in ("general", "ml_papers"):
        p = load_profile(name)
        assert "UKMLA" not in p.system + p.transcribe + p.scope_none + p.left_out_focus


def test_the_ml_profile_writes_mathjax():
    p = load_profile("ml_papers")
    assert r"\(" in p.system and "MathJax" in p.system and "LaTeX" in p.transcribe
    assert r"\(" in parse_output(example_of(p.system)).cards[0].back


def test_the_scope_line_comes_from_the_profile():
    msgs = build_messages(load_profile("general"), title="T", pages=["x"], target="x", target_pages=(1, 1),
                          focus="", mode="highlight")
    assert "Focus: none (" + load_profile("general").scope_none + ")" in msgs[1]["content"]
    assert "UKMLA" not in msgs[1]["content"]


def test_facets_mined_from_anki_extend_only_the_medical_vocabulary():
    counts = {"gram": [20, "gram"], "morphology": [46, "morphology"]}
    assert "morphology" in load_profile("medical_ukmla", facet_counts=counts).system
    assert "morphology" not in load_profile("ml_papers", facet_counts=counts).system


def test_cloze_items_with_mathjax_keep_their_clozes_intact():
    fields = overlap_fields("Scaled dot-product attention", [r"\(\frac{QK^T}{\sqrt{d_k}}\)", r"softmax over keys"])
    assert r"\sqrt{d_k} }" in fields[6] and "}}}" not in fields[6] and fields[6].count("{{c1::") == 1
    n = Note(type="list", title="Steps", items=[r"\(\frac{1}{\sqrt{d_k}}\)", "b"])
    assert validate([n]) == [[]]


def test_math_is_not_mistaken_for_html():
    n = Note(type="qa", front=r"Condition for \(a<y\) in ReLU", back=r"\(x<0 \Rightarrow 0\)")
    assert [i.code for i in validate([n])[0]] == []


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    e = {"llm": ScriptedLLM()}
    app = create_app(Config(data_dir=tmp_path / "d"), anki=AnkiConnect(transport=FakeAnki().transport()),
                     provider_for=lambda: e["llm"], jobs_inline=True)
    e["client"] = TestClient(app)
    yield e
    keyring.set_keyring(old)


def upload(client):
    pdf = make_pdf([["Scaled dot-product attention divides by the square root of d_k."]])
    return client.post("/api/documents", files={"file": ("attention.pdf", pdf, "application/pdf")}).json()


def reply(**extra):
    return json.dumps({"cards": [{"type": "qa", "front": "Attention scaling factor", "back": r"\(1/\sqrt{d_k}\)"}],
                       "left_out": [{"text": "Hardware details", "reason": "not about the method"}],
                       "image_occlusion_candidates": [], "flags": [], **extra})


def test_documents_get_the_default_profile_and_can_change_it(env):
    c = env["client"]
    assert upload(c)["profile"] == "medical_ukmla"
    c.put("/api/settings", json={"default_profile": "ml_papers"})
    doc = upload(c)
    assert doc["profile"] == "ml_papers"
    assert c.patch("/api/documents/%s" % doc["id"], json={"profile": "general"}).json()["profile"] == "general"
    assert c.patch("/api/documents/%s" % doc["id"], json={"profile": "nope"}).status_code == 422
    profiles = {p["name"]: p for p in c.get("/api/settings").json()["profiles"]}
    assert set(profiles) == NAMES and profiles["medical_ukmla"]["left_out_label"] == "UKMLA scope"


def test_jobs_use_the_documents_profile(env):
    c = env["client"]
    doc = upload(c)
    c.patch("/api/documents/%s" % doc["id"], json={"profile": "ml_papers"})
    env["llm"] = ScriptedLLM(reply(), reply())
    sel = {"page": 1, "text": "Scaled dot-product attention divides by the square root of d_k.", "rects": []}
    [job] = c.post("/api/documents/%s/generate" % doc["id"], json={"mode": "selection", "selection": sel}).json()["jobs"]
    assert job["profile"] == "ml_papers"
    assert env["llm"].calls[0]["messages"][0]["content"] == load_profile("ml_papers").system
    again = c.post("/api/jobs/%s/left-out/0" % job["id"]).json()
    assert again["focus"] == load_profile("ml_papers").left_out_focus and again["profile"] == "ml_papers"


def test_the_general_profile_is_for_anyone():
    p = load_profile("general")
    text = (p.system + p.transcribe + p.scope_none + p.left_out_focus).lower()
    for personal in ("student", "engineering", "uk spelling", "ukmla"):
        assert personal not in text, personal
