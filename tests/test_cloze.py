"""Cloze cards: Anki's own Cloze note type (Text, Extra), for properties asked together and for facts
that fit no Front/Back."""
import json

import pytest

from clanki import anki_format as af
from clanki.anki_index import AnkiIndex
from clanki.ankiconnect import AnkiConnect
from clanki.generation import EXAMPLE_OUTPUT, GenerationError, note_to_card, parse_output, to_notes
from clanki.models import Note
from clanki.validators import validate
from fake_anki import FakeAnki
from fake_llm import ScriptedLLM
from test_card_images import card, drop, env, shot, tag  # noqa: F401  (env is a fixture)

MOTOR = ("Slow vs fast-fatiguable motor units: physiological properties\n\n"
         "Speed of conduction: {{c1::slow vs fast}}\nSpeed of contraction: {{c1::slow vs fast}}\n"
         "Tension generated: {{c1::low vs high}}\nFatigue: {{c1::resistant vs prone}}")
MOTOR_HTML = MOTOR.replace("\n", "<br>")


def cloze(**kw):
    return Note(type="cloze", **{"text": MOTOR, **kw})


def reply(*cards):
    return json.dumps({"cards": list(cards), "left_out": [], "image_occlusion_candidates": [], "flags": []})


# the model's reply

def test_the_medical_example_shows_a_cloze_card():
    out = parse_output(json.dumps(EXAMPLE_OUTPUT))
    [c] = [c for c in out.cards if c.type == "cloze"]
    assert "{{c1::" in c.text and c.why


def test_cloze_cards_become_notes_and_back_again():
    out = parse_output(reply({"type": "cloze", "kind": "set", "text": MOTOR, "why": "Size principle", "flags": ["check"]}))
    [n] = to_notes(out, "d", "s")
    assert (n.type, n.text, n.why, n.kind, n.flags, n.tags) == ("cloze", MOTOR, "Size principle", "set", ["check"],
                                                                ["ai-generated"])
    assert note_to_card(n) == {"type": "cloze", "kind": "set", "text": MOTOR, "why": "Size principle", "flags": []}


def test_cloze_type_is_inferred_from_text():
    out = parse_output('{"cards": [{"text": "Aside from histamine, mast cells make {{c1::leukotrienes}}"}]}')
    assert out.cards[0].type == "cloze"


def test_a_cloze_card_needs_text():
    with pytest.raises(GenerationError):
        parse_output(reply({"type": "cloze", "text": ""}))


# Anki fields

def test_cloze_note_fields_keep_the_deletions_and_lines():
    assert af.note_fields(cloze(why="Small neurons, <b>oxidative</b> fibres")) == (
        "Cloze", {"Text": MOTOR_HTML, "Extra": "Small neurons, <b>oxidative</b> fibres"})


def test_cloze_text_is_escaped_like_other_fields():
    _, f = af.note_fields(cloze(text="a < b: {{c1::<script>x</script>}}"))
    assert f["Text"] == "a &lt; b: {{c1::&lt;script&gt;x&lt;/script&gt;}}"


def test_mathjax_braces_inside_a_cloze_are_spaced():
    _, f = af.note_fields(cloze(text=r"Attention scale: {{c1::\(\frac{1}{\sqrt{d_k}}\)}}"))
    assert f["Text"] == r"Attention scale: {{c1::\(\frac{1}{\sqrt{d_k} }\)}}"


def test_a_cloze_inside_mathjax_is_left_alone():
    _, f = af.note_fields(cloze(text=r"\(E = {{c1::mc^2}}\)"))
    assert f["Text"] == r"\(E = {{c1::mc^2}}\)"


def test_an_export_row_for_a_cloze():
    row = af.export_txt([cloze(guid="clankiC01", deck="D", why="w")]).splitlines()[-1].split("\t")
    assert row[:6] == ["clankiC01", "Cloze", "D", "", MOTOR_HTML, "w"]
    assert len(row) == 4 + af.N_FIELDS


# checks

def test_a_clean_cloze_has_no_issues():
    assert validate([cloze()]) == [[]]


@pytest.mark.parametrize("text, code", [("  ", "empty_text"), ("Fatigue: resistant vs prone", "no_cloze"),
                                        ("Fatigue: {{c1::resistant vs prone", "unclosed_cloze")])
def test_cloze_errors(text, code):
    [issues] = validate([cloze(text=text)])
    assert [(i.level, i.code) for i in issues] == [("error", code)]


def test_the_same_cloze_text_twice_is_a_duplicate():
    a, b = validate([cloze(), cloze()])
    assert [i.code for i in a] == [i.code for i in b] == ["duplicate_first_field"]


def test_unsupported_html_in_a_cloze_warns():
    [issues] = validate([cloze(text="<div>Fatigue: {{c1::resistant}}</div>")])
    assert [i.code for i in issues] == ["unsupported_html"]


# AnkiConnect

def test_status_wants_the_cloze_note_type():
    fake = FakeAnki(models={af.BASIC: list(af.BASIC_FIELDS), af.OVERLAP: list(af.OVERLAP_FIELDS)})
    assert AnkiConnect(transport=fake.transport()).status()["problems"] == ["Note type 'Cloze' not found in Anki"]


def test_status_reports_a_cloze_note_type_with_other_fields():
    fake = FakeAnki(models={**FakeAnki().models, af.CLOZE: ["Front", "Back"]})
    assert AnkiConnect(transport=fake.transport()).status()["problems"] == [
        "Note type 'Cloze' fields should start with: Text, Extra (or Back Extra)"]


def test_send_adds_and_updates_a_cloze_note():
    fake = FakeAnki()
    a = AnkiConnect(transport=fake.transport())
    [r] = a.send([cloze(id="c", deck="D", tags=["t"], why="w")], "Default")
    assert r.action == "added"
    assert fake.notes[r.anki_note_id] == {"modelName": "Cloze", "deckName": "D", "tags": ["t"],
                                          "fields": {"Text": MOTOR_HTML, "Extra": "w"}}
    [u] = a.send([cloze(id="c", why="w2", anki_note_id=r.anki_note_id, status="edited")], "Default")
    assert u.action == "updated" and fake.notes[r.anki_note_id]["fields"]["Extra"] == "w2"


def test_newer_ankis_back_extra_field_is_used():
    fake = FakeAnki(models={**FakeAnki().models, af.CLOZE: ["Text", "Back Extra"]})
    a = AnkiConnect(transport=fake.transport())
    assert a.status()["problems"] == []
    [r] = a.send([cloze(id="c", why="w")], "Default")
    assert fake.notes[r.anki_note_id]["fields"] == {"Text": MOTOR_HTML, "Back Extra": "w"}
    a.send([cloze(id="c", why="w2", anki_note_id=r.anki_note_id, status="edited")], "Default")
    assert fake.notes[r.anki_note_id]["fields"] == {"Text": MOTOR_HTML, "Back Extra": "w2"}


def test_cloze_notes_already_in_anki_are_matched_by_their_first_line():
    fake = FakeAnki()
    fake.add(af.CLOZE, "Physio", Text="Slow vs fast-fatiguable motor units: physiological properties<br><br>"
                                      "Fatigue: {{c1::resistant vs prone}}")
    index = AnkiIndex.fetch(AnkiConnect(transport=fake.transport()))
    [issues] = index.check([cloze(document_id="d")])
    assert [i.code for i in issues] == ["in_anki"]
    assert issues[0].message.startswith('Already in Anki: "Slow vs fast-fatiguable motor units: physiological '
                                        'properties" → Fatigue: resistant vs prone (Physio)')


# through the API

def test_a_cloze_card_is_made_sent_and_exported(env):
    c = env["client"]
    card(env, type="cloze", text=MOTOR, why="Size principle")
    [listed] = c.get("/api/documents/%s/notes" % env["doc"]["id"]).json()
    assert (listed["type"], listed["text"], listed["issues"]) == ("cloze", MOTOR, [])
    assert c.get("/api/documents/%s/history" % env["doc"]["id"]).json()[0]["label"] == (
        "Add card: Slow vs fast-fatiguable motor units: physiologica…")
    assert c.post("/api/documents/%s/send" % env["doc"]["id"]).json()["summary"]["added"] == 1
    [anki_note] = env["anki"].notes.values()
    assert anki_note["modelName"] == "Cloze" and anki_note["fields"]["Text"] == MOTOR_HTML
    card(env)  # a qa card
    body = {"document_ids": [env["doc"]["id"]], "scope": "all", "preview": True}
    assert c.post("/api/export", json=body).json()["cards"] == 2
    assert c.post("/api/export", json={**body, "types": ["cloze"]}).json()["cards"] == 1
    assert c.post("/api/export", json={**body, "types": ["qa", "list"]}).json()["cards"] == 1


def test_images_go_on_a_clozes_text_or_extra(env):
    s, n = shot(env), card(env, type="cloze", text=MOTOR)
    assert drop(env, n, s, "text").json()["text"] == MOTOR + "\n" + tag(s)
    assert drop(env, n, s, "why").status_code == 200
    assert drop(env, n, s, "front").status_code == 422


def test_an_ai_edit_of_a_cloze_hides_its_images_and_keeps_them(env):
    s, n = shot(env), card(env, type="cloze", text=MOTOR)
    drop(env, n, s, "text")
    env["llm"] = ScriptedLLM(reply({"type": "cloze", "text": MOTOR.replace("Fatigue", "Fatiguability")}))
    job = env["client"].post("/api/notes/%s/ai-edit" % n["id"], json={"instruction": "rename"}).json()
    sent = env["llm"].calls[0]["messages"][1]["content"]
    assert "<img" not in sent and '"type": "cloze"' in sent
    assert job["proposal"][0]["text"].endswith("Fatiguability: {{c1::resistant vs prone}}\n" + tag(s))


def test_a_qa_card_can_become_a_cloze_and_back(env):
    n = card(env)
    env["llm"] = ScriptedLLM(reply({"type": "cloze", "kind": "fact", "text": "Rhodopsin peaks near {{c1::~498 nm}}"}))
    job = env["client"].post("/api/notes/%s/ai-edit" % n["id"], json={"instruction": "make it a cloze"}).json()
    env["client"].post("/api/jobs/%s/accept" % job["id"])
    [after] = env["client"].get("/api/documents/%s/notes" % env["doc"]["id"]).json()
    assert (after["id"], after["type"], after["text"], after["front"], after["back"]) == (
        n["id"], "cloze", "Rhodopsin peaks near {{c1::~498 nm}}", "", "")
    env["llm"] = ScriptedLLM(reply({"type": "qa", "front": "Rhodopsin peak (value)", "back": "~498 nm"}))
    job = env["client"].post("/api/notes/%s/ai-edit" % n["id"], json={"instruction": "make it a qa"}).json()
    env["client"].post("/api/jobs/%s/accept" % job["id"])
    [after] = env["client"].get("/api/documents/%s/notes" % env["doc"]["id"]).json()
    assert (after["type"], after["text"], after["back"]) == ("qa", "", "~498 nm")
