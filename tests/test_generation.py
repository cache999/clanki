import json

import pytest

from clanki.generation import EXAMPLE_OUTPUT, GenerationError, parse_output, to_notes
from clanki.models import Note
from clanki.validators import validate


def test_the_prompt_example_parses():
    out = parse_output(json.dumps(EXAMPLE_OUTPUT))
    assert [c.type for c in out.cards] == ["qa", "qa", "list"]


def test_missing_optional_fields_default_and_extras_are_ignored():
    out = parse_output('{"cards": [{"type": "qa", "front": "F", "back": "B", "confidence": 0.9}]}')
    [c] = out.cards
    assert (c.why, c.add_reverse, c.reverse_prompt, c.facets, c.flags) == ("", False, "", [], [])
    assert out.left_out == [] and out.flags == []


def test_card_type_is_inferred_when_missing():
    out = parse_output('{"cards": [{"front": "F", "back": "B"}, {"title": "T", "items": ["a", "b"]}]}')
    assert [c.type for c in out.cards] == ["qa", "list"]


def test_code_fences_are_tolerated():
    assert parse_output('```json\n{"cards": []}\n```').cards == []


@pytest.mark.parametrize("bad", ["", "not json", '{"cards": [{"type": "qa"}]}', '{"cards": "x"}', "[]"])
def test_invalid_output_raises_with_a_reason(bad):
    with pytest.raises(GenerationError) as e:
        parse_output(bad)
    assert str(e.value)


def test_to_notes_maps_qa_and_list_cards():
    out = parse_output(json.dumps({
        "cards": [
            {"type": "qa", "kind": "fact", "front": "Capital of France", "back": "Paris", "why": "Seine",
             "add_reverse": True, "reverse_prompt": "what country has this capital?", "facets": ["location"],
             "flags": ["check"]},
            {"type": "list", "kind": "process", "title": "Steps (in order)", "items": ["a", "b"],
             "remarks": "because", "mnemonic": "AB", "full": False},
        ],
    }))
    qa, lst = to_notes(out, document_id="d", source_id="s")
    assert isinstance(qa, Note) and (qa.document_id, qa.source_id) == ("d", "s")
    assert (qa.type, qa.front, qa.back, qa.why, qa.add_reverse, qa.reverse_prompt) == (
        "qa", "Capital of France", "Paris", "Seine", True, "what country has this capital?")
    assert (qa.kind, qa.facets, qa.flags) == ("fact", ["location"], ["check"])
    assert (lst.type, lst.title, lst.items, lst.why, lst.mnemonic, lst.full, lst.kind) == (
        "list", "Steps (in order)", ["a", "b"], "because", "AB", False, "process")
    assert qa.tags == lst.tags == ["ai-generated"]


def test_reverse_prompt_written_into_back_is_moved_to_its_field():
    out = parse_output('{"cards": [{"type": "qa", "front": "F", "back": "Paris<br>(r: what country?)", '
                       '"add_reverse": true}]}')
    [n] = to_notes(out, document_id="d", source_id=None)
    assert (n.back, n.reverse_prompt) == ("Paris", "what country?")


def test_model_flags_show_as_warnings():
    [issues] = validate([Note(type="qa", front="F", back="B", flags=["Source says X; NICE says Y"])])
    assert [(i.level, i.code, i.message) for i in issues] == [("warning", "model_flag", "Source says X; NICE says Y")]
