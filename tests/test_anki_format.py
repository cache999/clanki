from pathlib import Path

from clanki import anki_format as af
from clanki.models import Note

IMPORT_TESTS = Path(__file__).resolve().parents[1] / "design_docs" / "import_tests"


def test_overlap_fields_follow_the_add_on_layout():
    f = af.overlap_fields("T", ["A", "B", "C", "D"], remarks="r", mnemonic="m", sources="s")
    assert len(f) == 27
    assert f[:6] == ["T", "A<br>B<br>C<br>D", "m", "r", "s", "1,1,0 | n,n,n,n"]
    assert f[6] == "<div>{{c1::A}}</div><div>...</div><div>...</div><div>...</div>"
    assert f[7] == "<div>A</div><div>{{c2::B}}</div><div>...</div><div>...</div>"
    assert f[8] == "<div>...</div><div>B</div><div>{{c3::C}}</div><div>...</div>"
    assert f[9] == "<div>...</div><div>...</div><div>C</div><div>{{c4::D}}</div>"
    assert f[10:26] == [""] * 16
    assert f[26] == "<div>{{c21::A}}</div><div>{{c21::B}}</div><div>{{c21::C}}</div><div>{{c21::D}}</div>"


def test_overlap_without_whole_list_card():
    f = af.overlap_fields("T", ["A", "B"], full=False)
    assert f[5] == "1,1,0 | n,n,n,y"
    assert f[26] == ""


def test_overlap_ul_style():
    f = af.overlap_fields("T", ["A", "B"], style="ul")
    assert f[1] == "<ul><li>A</li><li>B</li></ul>"
    assert f[6] == "<ul><li>{{c1::A}}</li><li>...</li></ul>"
    assert f[26] == "<ul><li>{{c21::A}}</li><li>{{c21::B}}</li></ul>"


def test_list_items_are_plain_text_and_escaped():
    f = af.overlap_fields("a < b", ["x & y", "<b>z</b>"])
    assert f[0] == "a &lt; b"
    assert f[1] == "x &amp; y<br>&lt;b&gt;z&lt;/b&gt;"


def test_rich_text_keeps_only_whitelisted_inline_tags():
    assert af.rich("<b>Prodrug</b> <script>x</script> H<sub>2</sub>O") == \
        "<b>Prodrug</b> &lt;script&gt;x&lt;/script&gt; H<sub>2</sub>O"


def test_rich_text_converts_newlines_and_tabs():
    assert af.rich("line 1\nline\t2") == "line 1<br>line 2"


def test_assemble_back_appends_reverse_prompt():
    assert af.assemble_back("Paris", True, "what country has this capital?") == \
        "Paris<br>(r: what country has this capital?)"


def test_assemble_back_ignores_prompt_when_reverse_off_or_prompt_empty():
    assert af.assemble_back("Paris", False, "what country?") == "Paris"
    assert af.assemble_back("Paris", True, "  ") == "Paris"


def test_basic_note_fields():
    n = Note(type="qa", front="Capital of France", back="Paris", why="Seine",
             add_reverse=True, reverse_prompt="what country has this capital?")
    model, fields = af.note_fields(n)
    assert model == "Basic (optional reversed card)"
    assert fields == {"Front": "Capital of France",
                      "Back": "Paris<br>(r: what country has this capital?)",
                      "Add Reverse": "y", "Why": "Seine"}


def test_list_note_fields_are_named():
    n = Note(type="list", title="T", items=["A", "B"], why="because", mnemonic="m")
    model, fields = af.note_fields(n)
    assert model == "Cloze (overlapping)"
    assert list(fields) == af.OVERLAP_FIELDS
    assert fields["Remarks"] == "because"
    assert fields["Text2"] == "<div>A</div><div>{{c2::B}}</div>"


def test_guid_is_ten_safe_characters_and_unique():
    gs = {af.new_guid() for _ in range(500)}
    assert len(gs) == 500
    assert all(len(g) == 10 and g.isalnum() for g in gs)


def _test3_notes(back_suffix=""):
    d, tag = "clanki-test::3-clanki", "clanki-test"
    return [
        Note(guid="clankiT3a01", type="list", deck=d, tags=[tag, "clanki-test::lists"],
             title="CLANKI TEST 3 - noble gases (increasing atomic number)",
             items=["He", "Ne", "Ar", "Kr", "Xe"],
             why="Test 3: ordered, 5 items, whole-list card on.",
             mnemonic="He Never Arrives Kraving Xenon", sources="clanki import test"),
        Note(guid="clankiT3b02", type="list", deck=d, tags=[tag, "clanki-test::lists"],
             title="CLANKI TEST 3 - RGB+K print/screen colours (set; order: RGB then K)",
             items=["Red", "Green", "Blue", "Black"],
             why="Test 3: set with imposed order, whole-list card off.", full=False, style="ul"),
        Note(guid="clankiT3c03", type="qa", deck=d, tags=[tag, "clanki-test::basic"],
             front="CLANKI TEST 3 - capital of France", back="Paris" + back_suffix, add_reverse=True,
             why="Test 3: reverse card on; Why should show on BOTH answer sides."),
        Note(guid="clankiT3d04", type="qa", deck=d, tags=[tag, "clanki-test::basic"],
             front="CLANKI TEST 3 - water boiling point at 1 atm (value + unit)",
             back="100 °C" + back_suffix,
             why="Boiling occurs when vapour pressure equals ambient pressure (101.3 kPa)."),
    ]


def test_export_reproduces_the_test3_file_verified_in_anki():
    expected = (IMPORT_TESTS / "test3_clanki_format.txt").read_text(encoding="utf-8")
    assert af.export_txt(_test3_notes()) == expected


def test_export_reproduces_the_test3b_reimport_file():
    expected = (IMPORT_TESTS / "test3b_clanki_reimport.txt").read_text(encoding="utf-8")
    assert af.export_txt(_test3_notes(" (EDITED by re-import)")) == expected


def test_export_uses_default_deck_when_note_has_none():
    text = af.export_txt([Note(guid="g1", type="qa", front="F", back="B")], default_deck="MVST1B::vision")
    row = text.splitlines()[-1].split("\t")
    assert row[:4] == ["g1", "Basic (optional reversed card)", "MVST1B::vision", ""]
    assert len(row) == 31


def test_tags_with_spaces_are_joined_by_underscores():
    text = af.export_txt([Note(guid="g1", type="qa", front="F", back="B", tags=["CPC::head ache", "x"])])
    assert text.splitlines()[-1].split("\t")[3] == "CPC::head_ache x"
