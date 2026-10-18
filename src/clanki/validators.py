"""Deterministic checks on cards; shown as warnings in the cards pane."""
import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from .anki_format import OLC_MAX
from .models import Note

LONG_LIST = 8
_ALLOWED_TAGS = {"b", "i", "u", "sub", "sup", "br"}
_TAG = re.compile(r"</?\s*([a-zA-Z][a-zA-Z0-9]*)")
_MATH = re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]", re.S)  # MathJax: \( ... \) and \[ ... \], where "<" is maths


class Issue(BaseModel):
    level: Literal["error", "warning"]
    code: str
    message: str


def _err(code, msg):
    return Issue(level="error", code=code, message=msg)


def _warn(code, msg):
    return Issue(level="warning", code=code, message=msg)


def _key(s: str) -> str:
    return re.sub(r"\W+", " ", re.sub(r"<[^>]*>", " ", s).lower()).strip()


def _items(n: Note) -> list[str]:
    return [x for x in n.items if x.strip()]


def _check_one(n: Note) -> list[Issue]:
    out = [_warn("model_flag", f) for f in n.flags if f.strip()]
    if n.type == "qa":
        if not n.front.strip():
            out.append(_err("empty_front", "Front is empty"))
        if not n.back.strip():
            out.append(_err("empty_back", "Back is empty"))
        if n.add_reverse and not n.reverse_prompt.strip():
            out.append(_warn("reverse_prompt_missing",
                             "Reverse card on but no reverse prompt to recover the Front"))
        if len([s for s in n.back.split(";") if s.strip()]) >= 4:
            out.append(_warn("back_is_list", "4 or more items in Back: consider a list card"))
        bad = {t.lower() for f in (n.front, n.back, n.why, n.reverse_prompt)
               for t in _TAG.findall(_MATH.sub(" ", f))} - _ALLOWED_TAGS
        if bad:
            out.append(_warn("unsupported_html",
                             "Tags shown as text in Anki: " + ", ".join(sorted(bad))))
        return out
    items = _items(n)
    if not 2 <= len(items) <= OLC_MAX:
        out.append(_err("list_size", "A list needs 2-%d items (has %d)" % (OLC_MAX, len(items))))
    elif len(items) > LONG_LIST:
        out.append(_warn("long_list", "%d items: split by principle?" % len(items)))
    if any("::" in x for x in items):  # braces are spaced apart on export (anki_format.cloze_safe)
        out.append(_err("bad_item_chars", "List items cannot contain '::'"))
    if not n.title.strip():
        out.append(_warn("no_title", "List has no title (the title is the prompt)"))
    return out


def validate(notes: list[Note]) -> list[list[Issue]]:
    """Issues per note, in input order. Deleted notes are skipped and not compared."""
    issues = [[] if n.deleted else _check_one(n) for n in notes]
    live = [i for i, n in enumerate(notes) if not n.deleted]

    first = defaultdict(list)
    for i in live:
        n = notes[i]
        k = _key(n.front if n.type == "qa" else n.title)
        if k:
            first[(n.type, k)].append(i)
    for group in first.values():
        if len(group) > 1:
            for i in group:
                issues[i].append(_err("duplicate_first_field",
                                      "Same %s as another card" % ("Front" if notes[i].type == "qa" else "Title")))

    backs = defaultdict(list)
    for i in live:
        if notes[i].type == "qa" and _key(notes[i].back):
            backs[_key(notes[i].back)].append(i)
    for group in backs.values():
        if len(group) > 1 and any(notes[i].add_reverse for i in group):
            for i in group:
                issues[i].append(_warn("shared_back", "Same Back as another card: reverse card is ambiguous"))
    return issues
