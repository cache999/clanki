"""Turn notes into the user's Anki note types: field dicts for AnkiConnect and the
tab-separated import file (format verified by design_docs/import_tests/test3)."""
import html
import re

from .models import Note, new_guid  # noqa: F401  (new_guid re-exported)

BASIC = "Basic (optional reversed card)"
BASIC_FIELDS = ["Front", "Back", "Add Reverse", "Why"]
OVERLAP = "Cloze (overlapping)"
OLC_MAX = 20
OVERLAP_FIELDS = (["Title", "Original", "Mnemonic", "Remarks", "Sources", "Settings"]
                  + ["Text%d" % k for k in range(1, OLC_MAX + 1)] + ["Full"])
N_FIELDS = len(OVERLAP_FIELDS)  # widest note type; every export row is padded to it
REVERSE_FORMAT = "<br>(r: {prompt})"

_INLINE = re.compile(r"&lt;(/?(?:b|i|u|sub|sup)|br\s*/?)&gt;", re.I)
# a screenshot clanki copies into Anki's media (see media.py); no other image survives
_IMAGE = re.compile(r"&lt;img src=&quot;(clanki-[0-9a-f]{32}\.(?:png|jpg|gif|webp))&quot;&gt;")


def esc(s: str) -> str:
    """Plain text -> safe field HTML. Tabs would break the import file; newlines become <br>."""
    s = html.escape(str(s or ""), quote=False).replace('"', "&quot;")
    return s.replace("\r\n", "\n").replace("\t", " ").strip().replace("\n", "<br>")


def rich(s: str) -> str:
    """Like esc, but keeps the inline tags b, i, u, sub, sup and br, and clanki's screenshots."""
    s = _INLINE.sub(lambda m: "<" + m.group(1) + ">", esc(s))
    return _IMAGE.sub(lambda m: '<img src="%s">' % m.group(1), s)


def assemble_back(back: str, add_reverse: bool, reverse_prompt: str, fmt: str = REVERSE_FORMAT) -> str:
    """The reverse card shows Back as its prompt, so a reversed Back carries the question
    that recovers the Front."""
    b = rich(back)
    p = rich(reverse_prompt)
    return b + fmt.format(prompt=p) if add_reverse and p else b


def _wrap(style: str, xs: list[str]) -> str:
    if style == "ul":
        return "<ul>%s</ul>" % "".join("<li>%s</li>" % x for x in xs)
    return "".join("<div>%s</div>" % x for x in xs)


def cloze_safe(s: str) -> str:
    r"""Inside a cloze, "}}" would end it early and "{{" open one, as MathJax often writes them
    (\frac{1}{\sqrt{d}}): space them, as Anki's manual advises; MathJax reads them the same."""
    while "}}" in s or "{{" in s:
        s = s.replace("}}", "} }").replace("{{", "{ {")
    return s


def overlap_fields(title, items, remarks="", mnemonic="", sources="", style="div", full=True) -> list[str]:
    """Every Cloze (overlapping) field, filled as the add-on's generator does with
    settings 1,1,0: item k is clozed, item k-1 shown, the rest '...'."""
    items = [esc(cloze_safe(x)) for x in items]
    original = "<br>".join(items) if style == "div" else _wrap("ul", items)
    texts = []
    for k in range(len(items)):
        snip = ["..."] * len(items)
        if k:
            snip[k - 1] = items[k - 1]
        snip[k] = "{{c%d::%s}}" % (k + 1, items[k])
        texts.append(_wrap(style, snip))
    texts += [""] * (OLC_MAX - len(texts))
    whole = _wrap(style, ["{{c%d::%s}}" % (OLC_MAX + 1, x) for x in items]) if full else ""
    settings = "1,1,0 | n,n,n," + ("n" if full else "y")
    return [esc(title), original, rich(mnemonic), rich(remarks), rich(sources), settings] + texts + [whole]


def note_fields(n: Note) -> tuple[str, dict[str, str]]:
    """(note type name, {field name: value}) for one note."""
    if n.type == "qa":
        values = [rich(n.front), assemble_back(n.back, n.add_reverse, n.reverse_prompt),
                  "y" if n.add_reverse else "", rich(n.why)]
        return BASIC, dict(zip(BASIC_FIELDS, values))
    values = overlap_fields(n.title, n.items, remarks=n.why, mnemonic=n.mnemonic,
                            sources=n.sources, style=n.style, full=n.full)
    return OVERLAP, dict(zip(OVERLAP_FIELDS, values))


def clean_tags(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = re.sub(r"\s+", "_", str(t).strip())
        if t and t not in out:
            out.append(t)
    return out


def export_txt(notes: list[Note], default_deck: str = "Default") -> str:
    cols = ["GUID", "Note type", "Deck", "Tags"] + ["F%d" % i for i in range(1, N_FIELDS + 1)]
    head = ["#separator:tab", "#html:true", "#guid column:1", "#notetype column:2",
            "#deck column:3", "#tags column:4", "#columns:" + "\t".join(cols)]
    rows = []
    for n in notes:
        model, fields = note_fields(n)
        values = list(fields.values())
        rows.append([n.guid, model, n.deck or default_deck, " ".join(clean_tags(n.tags))]
                    + values + [""] * (N_FIELDS - len(values)))
    return "\n".join(head + ["\t".join(r) for r in rows]) + "\n"
