"""Screenshots dropped onto a card's field: shown in clanki, copied into Anki on send, kept from the AI."""
import json

import keyring
import pytest
from fastapi.testclient import TestClient

from clanki.anki_format import rich
from clanki.ankiconnect import AnkiConnect
from clanki.app import create_app
from clanki.config import Config
from clanki.models import Note
from clanki.validators import validate
from fake_anki import FakeAnki
from fake_keyring import MemoryKeyring
from fake_llm import ScriptedLLM
from make_pdf import make_pdf
from test_transcribe import PNG, PNG_URL

NAME = 'clanki-0123456789abcdef0123456789abcdef.png'


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    old = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    e = {"llm": ScriptedLLM(), "anki": FakeAnki()}
    app = create_app(Config(data_dir=tmp_path / "d"), anki=AnkiConnect(transport=e["anki"].transport()),
                     provider_for=lambda: e["llm"], jobs_inline=True)
    e["client"] = TestClient(app)
    pdf = make_pdf([["Rhodopsin absorbs maximally near 498 nm."]])
    e["doc"] = e["client"].post("/api/documents", files={"file": ("v.pdf", pdf, "application/pdf")}).json()
    yield e
    keyring.set_keyring(old)


def shot(env):
    return env["client"].post("/api/documents/%s/screenshots" % env["doc"]["id"],
                              json={"page": 1, "rect": [0.1, 0.1, 0.5, 0.3], "image": PNG_URL}).json()


def card(env, **kw):
    body = {"type": "qa", "front": "Rhodopsin peak (value)", "back": "~498 nm", **kw}
    return env["client"].post("/api/documents/%s/notes" % env["doc"]["id"], json=body).json()


def drop(env, note, src, field):
    return env["client"].post("/api/notes/%s/images" % note["id"], json={"source_id": src["id"], "field": field})


def tag(src):
    return '<img src="clanki-%s.png">' % src["id"]


def test_an_image_dropped_on_a_field_is_appended_on_its_own_line(env):
    s, n = shot(env), card(env)
    r = drop(env, n, s, "back")
    assert r.status_code == 200 and r.json()["back"] == "~498 nm\n" + tag(s)
    assert drop(env, card(env, front="Other", back=""), s, "back").json()["back"] == tag(s)
    undone = env["client"].post("/api/documents/%s/undo" % env["doc"]["id"]).json()
    assert undone["label"] == "Add image: Other"


def test_which_fields_take_images(env):
    s = shot(env)
    lst = card(env, type="list", title="Retinal layers", items=["a", "b"])
    assert drop(env, lst, s, "why").status_code == 200  # a list's Remarks
    assert drop(env, lst, s, "sources").status_code == 200
    assert drop(env, lst, s, "front").status_code == 422
    assert drop(env, card(env), s, "reverse_prompt").status_code == 422


def test_the_image_is_served_to_clanki(env):
    s = shot(env)
    assert env["client"].get("/api/media/clanki-%s.png" % s["id"]).content == PNG
    assert env["client"].get("/api/media/clanki-%s.png" % ("0" * 32)).status_code == 404
    assert env["client"].get("/api/media/..%2Fclanki.db").status_code == 404


def test_send_copies_the_image_into_anki(env):
    s, n = shot(env), card(env)
    drop(env, n, s, "back")
    r = env["client"].post("/api/documents/%s/send" % env["doc"]["id"]).json()
    assert r["summary"]["added"] == 1
    assert env["anki"].media == {"clanki-%s.png" % s["id"]: PNG}
    [anki_note] = env["anki"].notes.values()
    assert tag(s) in anki_note["fields"]["Back"]


def test_only_clanki_images_survive_into_anki_fields():
    assert rich('Diagram: <img src="%s">' % NAME) == 'Diagram: <img src="%s">' % NAME
    assert rich('<img src="http://x.example/a.png">') == '&lt;img src=&quot;http://x.example/a.png&quot;&gt;'
    assert validate([Note(type="qa", front="F", back='<img src="%s">' % NAME)]) == [[]]


def test_the_ai_never_sees_images_and_its_suggestion_keeps_them(env):
    s, n = shot(env), card(env)
    drop(env, n, s, "back")
    proposal = {"type": "qa", "front": "Rhodopsin peak absorption (value + unit)", "back": "~498 nm"}
    env["llm"] = ScriptedLLM(json.dumps({"cards": [proposal], "left_out": [], "image_occlusion_candidates": [], "flags": []}))
    job = env["client"].post("/api/notes/%s/ai-edit" % n["id"], json={"instruction": "clearer front"}).json()
    assert "<img" not in env["llm"].calls[0]["messages"][1]["content"]
    assert job["proposal"][0]["back"] == "~498 nm\n" + tag(s)
    env["client"].post("/api/jobs/%s/accept" % job["id"])
    [after] = env["client"].get("/api/documents/%s/notes" % env["doc"]["id"]).json()
    assert after["back"] == "~498 nm\n" + tag(s) and after["front"].startswith("Rhodopsin peak absorption")


def test_export_says_how_many_cards_have_images(env):
    s, n = shot(env), card(env)
    card(env, front="No image")
    drop(env, n, s, "why")
    r = env["client"].post("/api/export", json={"document_ids": [env["doc"]["id"]], "preview": True}).json()
    assert r == {"cards": 2, "with_errors": 0, "with_images": 1}
