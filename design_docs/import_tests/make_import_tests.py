#!/usr/bin/env python3
"""Generate the three Anki import test files for clanki (spec: web_gui_spec.md).

Field order is taken from the user's collection:
  Cloze (overlapping):            Title, Original, Mnemonic, Remarks, Sources, Settings, Text1-20, Full  (27)
  Basic (optional reversed card): Front, Back, Add Reverse                                              (3)
"""
import html, sys
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
OLC_MAX = 20
TAG = "clanki-test"


def overlap_fields(title, items, remarks="", mnemonic="", sources="", style="div", full=True):
    """Fill every Cloze (overlapping) field the way the add-on's generator does (settings 1,1,0)."""
    if style == "div":
        wrap = lambda xs: "".join("<div>%s</div>" % x for x in xs)
        original = "<br>".join(items)
    else:  # ul
        wrap = lambda xs: "<ul>%s</ul>" % "".join("<li>%s</li>" % x for x in xs)
        original = wrap(items)  # no raw newlines: they would split the TSV row
    texts = []
    for k in range(len(items)):
        snip = ["..."] * len(items)
        if k:
            snip[k - 1] = items[k - 1]
        snip[k] = "{{c%d::%s}}" % (k + 1, items[k])
        texts.append(wrap(snip))
    texts += [""] * (OLC_MAX - len(texts))
    full_f = wrap(["{{c21::%s}}" % x for x in items]) if full else ""
    settings = "1,1,0 | n,n,n," + ("n" if full else "y")
    return [title, original, mnemonic, remarks, sources, settings] + texts + [full_f]


def write(name, header, rows):
    p = OUT / name
    p.write_text("\n".join(header + ["\t".join(r) for r in rows]) + "\n", encoding="utf-8", newline="\n")
    print("wrote", p, len(rows), "rows")


# ---------- Test 1: the user's notes format (27 fields + tags column 28) ----------
t1 = [
    overlap_fields("CLANKI TEST 1 - inner planets (order from Sun)",
                   ["Mercury", "Venus", "Earth", "Mars"],
                   remarks="Test 1 (notes format, div style). Expect 5 cards: 4 overlapping + 1 whole-list."),
    overlap_fields("CLANKI TEST 1 - Beatles members (set; order: alphabetical)",
                   ["George", "John", "Paul", "Ringo"],
                   remarks="Test 1 (notes format, ul style). Set with an imposed order, stated in the title.",
                   style="ul"),
]
write("test1_notes_format.txt",
      ["#separator:tab", "#html:true", "#notetype:Cloze (overlapping)",
       "#deck:clanki-test::1-notes", "#tags column:28"],
      [r + [TAG] for r in t1])


# ---------- Test 2: the given cards format (rendered card HTML into Basic) ----------
def attr(s):  # mimics Anki's data-cloze escaping: every non-alphanumeric char as &#xNN;
    return "".join(c if c.isalnum() else "&#x%X;" % ord(c) for c in s)


def rendered_cards(title, items, remarks, hint_id):
    orig = "<br>".join(items)
    out = []
    ordinals = list(range(1, len(items) + 1)) + [21]
    for ordn in ordinals:
        f_items, b_items = [], []
        for i, it in enumerate(items):
            k = i + 1
            if ordn == 21 or k == ordn:
                f_items.append('<div><span class="cloze" data-cloze="%s" data-ordinal="%d">[...]</span></div>' % (attr(it), ordn))
                b_items.append('<div><span class="cloze" data-ordinal="%d">%s</span></div>' % (ordn, it))
            elif k == ordn - 1:
                f_items.append("<div>%s</div>" % it); b_items.append("<div>%s</div>" % it)
            else:
                f_items.append("<div>...</div>"); b_items.append("<div>...</div>")
        front = ('<div class="front">\n  <div class="title">%s\n</div>\n  <div class="text">\n    %s\n'
                 '    <div class="hidden">\n       <div>%s</div>\n    </div>\n  </div>\n</div>') % (title, "".join(f_items), orig)
        back = ('<div class="back">\n  <div class="title">%s</div>\n  <div class="text">\n    %s\n'
                '    <div class="hidden">%s</div>\n  </div>\n  <div class="extra"><hr></div>\n'
                '  <div class="text"><div class="fullhint">\n<a class=hint href="#"\n'
                "onclick=\"this.style.display='none';\ndocument.getElementById('%s').style.display='block';\n"
                'return false;" draggable=false>\nOriginal</a>\n<div id="%s" class=hint style="display: none">%s</div>\n'
                '</div></div>\n  <div class="extra">\n    <div class="extra-entry">\n'
                '      <div class="extra-descr">Remarks</div><div>%s</div>\n    </div>\n  </div>\n</div>') % (
                   title, "".join(b_items), orig, hint_id, hint_id, orig, remarks)
        out.append([front, back])
    return out


def csvq(s):  # quote like Anki's card export (fields contain newlines)
    return '"' + s.replace('"', '""') + '"'


t2 = rendered_cards("CLANKI TEST 2 - inner planets (order from Sun)",
                    ["Mercury", "Venus", "Earth", "Mars"],
                    "Test 2 (cards format): each overlapping card imported as its own Basic note.",
                    "hintc1a2b3c4d5e6f701")
write("test2_cards_format.txt",
      ["#separator:tab", "#html:true", "#notetype:Basic", "#deck:clanki-test::2-cards", "#tags:" + TAG],
      [[csvq(f), csvq(b)] for f, b in t2])


# ---------- Test 3: proposed clanki export format ----------
# Mixed note types in one file, stable GUIDs (re-export updates instead of duplicating),
# per-row deck and tags, every row padded to the same width.
N = 27
COLS = ["GUID", "Note type", "Deck", "Tags"] + ["F%d" % i for i in range(1, N + 1)]
HDR = ["#separator:tab", "#html:true", "#guid column:1", "#notetype column:2",
       "#deck column:3", "#tags column:4", "#columns:" + "\t".join(COLS)]
OLC, BASIC = "Cloze (overlapping)", "Basic (optional reversed card)"


def row(guid, nt, deck, tags, fields):
    return [guid, nt, deck, " ".join(tags)] + fields + [""] * (N - len(fields))


def t3_rows(back_suffix=""):
    d = "clanki-test::3-clanki"
    return [
        row("clankiT3a01", OLC, d, [TAG, "clanki-test::lists"],
            overlap_fields("CLANKI TEST 3 - noble gases (increasing atomic number)",
                           ["He", "Ne", "Ar", "Kr", "Xe"],
                           remarks="Test 3: ordered, 5 items, whole-list card on.",
                           mnemonic="He Never Arrives Kraving Xenon",
                           sources="clanki import test")),
        row("clankiT3b02", OLC, d, [TAG, "clanki-test::lists"],
            overlap_fields("CLANKI TEST 3 - RGB+K print/screen colours (set; order: RGB then K)",
                           ["Red", "Green", "Blue", "Black"],
                           remarks="Test 3: set with imposed order, whole-list card off.",
                           full=False, style="ul")),
        # Basic fields: Front, Back, Add Reverse, Why (Why must be added to the note type first)
        row("clankiT3c03", BASIC, d, [TAG, "clanki-test::basic"],
            ["CLANKI TEST 3 - capital of France", "Paris" + back_suffix, "y",
             "Test 3: reverse card on; Why should show on BOTH answer sides."]),
        row("clankiT3d04", BASIC, d, [TAG, "clanki-test::basic"],
            ["CLANKI TEST 3 - water boiling point at 1 atm (value + unit)",
             "100 °C" + back_suffix, "",
             "Boiling occurs when vapour pressure equals ambient pressure (101.3 kPa)."]),
    ]


write("test3_clanki_format.txt", HDR, t3_rows())
# 3b: same GUIDs, edited Backs; importing it should UPDATE the 3a notes, not add new ones.
write("test3b_clanki_reimport.txt", HDR, t3_rows(back_suffix=" (EDITED by re-import)"))
