from clanki.models import Note
from clanki.validators import validate


def codes(issues):
    return sorted(i.code for i in issues)


def qa(**kw):
    return Note(type="qa", **{"front": "F", "back": "B", **kw})


def lst(**kw):
    return Note(type="list", **{"title": "T", "items": ["a", "b"], **kw})


def test_clean_cards_have_no_issues():
    assert validate([qa(), lst()]) == [[], []]


def test_empty_front_or_back_is_an_error():
    [issues] = validate([qa(front=" ", back="")])
    assert codes(issues) == ["empty_back", "empty_front"]
    assert all(i.level == "error" for i in issues)


def test_reversed_card_needs_a_reverse_prompt():
    [issues] = validate([qa(add_reverse=True)])
    assert codes(issues) == ["reverse_prompt_missing"]
    assert validate([qa(add_reverse=True, reverse_prompt="what country has this capital?")]) == [[]]


def test_shared_back_warns_only_when_a_reverse_card_is_involved():
    a, b = qa(front="F1", back="Paris"), qa(front="F2", back=" paris ")
    assert validate([a, b]) == [[], []]
    a.add_reverse, a.reverse_prompt = True, "city?"
    ia, ib = validate([a, b])
    assert codes(ia) == codes(ib) == ["shared_back"]


def test_semicolon_list_in_back_suggests_a_list_card():
    [issues] = validate([qa(back="a; b; c; d")])
    assert codes(issues) == ["back_is_list"]
    assert validate([qa(back="a; b; c")]) == [[]]


def test_unsupported_html_is_flagged():
    [issues] = validate([qa(front="<span>F</span>", back="<b>ok</b>")])
    assert codes(issues) == ["unsupported_html"]


def test_list_item_count_limits():
    assert codes(validate([lst(items=["a"])])[0]) == ["list_size"]
    assert codes(validate([lst(items=[str(i) for i in range(21)])])[0]) == ["list_size"]
    assert codes(validate([lst(items=[str(i) for i in range(9)])])[0]) == ["long_list"]


def test_list_items_cannot_contain_cloze_syntax():
    [issues] = validate([lst(items=["a::b", "c"])])
    assert codes(issues) == ["bad_item_chars"]
    assert issues[0].level == "error"


def test_blank_items_are_ignored_and_title_is_required():
    [issues] = validate([lst(title="", items=["a", " ", "b"])])
    assert codes(issues) == ["no_title"]


def test_duplicate_first_field_within_a_note_type_is_an_error():
    a, b, c = qa(front="Same"), qa(front="same", back="other"), lst(title="Same")
    ia, ib, ic = validate([a, b, c])
    assert codes(ia) == codes(ib) == ["duplicate_first_field"]
    assert ic == []


def test_deleted_notes_are_not_compared():
    a, b = qa(front="Same"), qa(front="Same", deleted=True)
    assert validate([a, b]) == [[], []]
