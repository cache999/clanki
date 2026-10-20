import json

from clanki.generation import EXAMPLE_OUTPUT, parse_output
from clanki.prompts import MAX_CONTEXT_CHARS, build_edit_messages, build_messages, load_profile

PAGES = ["Rods and cones.", "Rhodopsin absorbs maximally near 498 nm.", "Bipolar cells."]


def test_profile_loads_with_label_and_a_json_example():
    p = load_profile("medical_ukmla")
    assert p.label == "Medical (UKMLA)"
    assert "JSON" in p.system  # DeepSeek's JSON mode needs the word and an example
    example = json.dumps(EXAMPLE_OUTPUT, ensure_ascii=False, indent=1)
    assert example in p.system and len(parse_output(example).cards) == 4
    assert "{EXAMPLE}" not in p.system


def test_system_prompt_is_stable_between_loads():
    assert load_profile("medical_ukmla").system == load_profile("medical_ukmla").system


def _msgs(**kw):
    args = dict(title="Vision", pages=PAGES, target="Rhodopsin absorbs maximally near 498 nm.",
                target_pages=(2, 2), focus="", mode="highlight")
    return build_messages(load_profile("medical_ukmla"), **{**args, **kw})


def test_messages_are_system_then_user_with_document_then_target():
    system, user = _msgs()
    assert system == {"role": "system", "content": load_profile("medical_ukmla").system}
    text = user["content"]
    assert user["role"] == "user"
    assert text.index('<document title="Vision"') < text.index("[p.1]") < text.index("<target") < text.index("Focus")
    assert '<target pages="2">\nRhodopsin absorbs maximally near 498 nm.\n</target>' in text
    assert "Focus: none" in text


def test_jobs_on_one_document_share_the_document_prefix():
    a = _msgs()[1]["content"]
    b = _msgs(target="Bipolar cells.", target_pages=(3, 3), focus="MoA", mode="chunk")[1]["content"]
    doc_end = a.index("</document>") + len("</document>")
    assert a[:doc_end] == b[:doc_end]
    assert "Focus: MoA" in b and "whole section" in b


def test_a_prompt_job_sends_the_request_after_the_same_document_prefix():
    a = _msgs()[1]["content"]
    b = _msgs(target="why hypoglycaemia causes decerebrate posture", focus="", mode="prompt")[1]["content"]
    doc_end = a.index("</document>") + len("</document>")
    assert a[:doc_end] == b[:doc_end]
    assert "<request>\nwhy hypoglycaemia causes decerebrate posture\n</request>" in b
    assert "<target" not in b and "Focus:" not in b and "may not cover" in b


def test_an_edit_of_a_prompted_card_shows_the_request():
    msgs = build_edit_messages(load_profile("medical_ukmla"), title="Vision", pages=PAGES, card={"type": "qa"},
                               source_text="why rods saturate", source_pages=(2, 2), instruction="shorter",
                               source_kind="prompt")
    text = msgs[1]["content"]
    assert "<request>\nwhy rods saturate\n</request>" in text and "<source" not in text


def test_large_documents_send_only_pages_around_the_target():
    pages = ["page %d " % i + "x" * 20000 for i in range(1, 21)]
    text = _msgs(pages=pages, target="x", target_pages=(10, 10))[1]["content"]
    assert len(text) < MAX_CONTEXT_CHARS
    assert "[p.8]" in text and "[p.12]" in text and "[p.7]" not in text and "[p.13]" not in text
    assert 'pages="8-12"' in text


def _vocab_line(system: str) -> str:
    return system.split("# Facet vocabulary\n", 1)[1].splitlines()[1]


def test_without_anki_the_prompt_uses_the_profile_facets():
    system = load_profile("medical_ukmla").system
    assert "{FACETS}" not in system
    assert _vocab_line(system).startswith("definition, function, location, MoA, origin")


def test_the_students_frequent_facets_join_the_vocabulary():
    counts = {"morphology": [46, "morphology"], "gram": [20, "gram"], "overview": [47, "overview"],
              "definition": [891, "definition"], "once": [1, "once"]}
    line = _vocab_line(load_profile("medical_ukmla", facet_counts=counts).system)
    assert line.startswith("definition, function") and line.endswith("why, gram, morphology")
    assert "overview" not in line and "once" not in line  # excluded as vague; too rare
