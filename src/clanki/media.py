"""Screenshots on cards: a field holds <img src="clanki-<source id>.<ext>">, the name Anki stores the
image under when the card is sent. These are the only images clanki allows in a field."""
import re

from .models import Note

TAG = re.compile(r'<img src="(clanki-([0-9a-f]{32})\.(?:png|jpg|gif|webp))">')
NAME = re.compile(r"clanki-([0-9a-f]{32})\.(png|jpg|gif|webp)")
# fields an image can be dropped on (a list's "why" is its Remarks, a cloze's its Extra)
IMAGE_FIELDS = {"qa": ("front", "back", "why"), "list": ("why", "sources"), "cloze": ("text", "why")}
_SENT_TO_MODEL = ("front", "back", "why", "text")  # the fields of an AI edit's card that can hold images


def tag(source_id: str, ext: str) -> str:
    return '<img src="clanki-%s.%s">' % (source_id, ext)


def append(value: str, tag_: str) -> str:
    return value + "\n" + tag_ if value.strip() else tag_


def names(n: Note) -> list[str]:
    """The images a note shows, in order, without repeats."""
    found = [m.group(1) for f in (n.front, n.back, n.text, n.why, n.sources) for m in TAG.finditer(f)]
    return list(dict.fromkeys(found))


def strip(n: Note) -> Note:
    """The note without its images, for the model (which must not see or drop them)."""
    return n.model_copy(update={f: _without(getattr(n, f)) for f in _SENT_TO_MODEL})


def reattach(card: dict, before: Note) -> dict:
    """Put the images the model never saw back into its revised card (reply format), in the same
    field, or in the Why (a list's remarks) if the card changed type."""
    card = dict(card)
    kind = card.get("type", "qa")
    why = "remarks" if kind == "list" else "why"
    own = {"qa": ("front", "back", "why"), "cloze": ("text", "why")}.get(kind, ())
    for f in _SENT_TO_MODEL:
        target = f if f in own else why
        for t in TAG.findall(getattr(before, f)):
            card[target] = append(card.get(target) or "", '<img src="%s">' % t[0])
    return card


def _without(s: str) -> str:
    return re.sub(r"\n?" + TAG.pattern, "", s).strip()
