"""The JSON the model returns, how it is parsed leniently, and how it becomes notes."""
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from .models import Note

GENERATED_TAG = "ai-generated"


class GenQA(BaseModel):
    type: Literal["qa"]
    kind: str = ""
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    why: str = ""
    add_reverse: bool = False
    reverse_prompt: str = ""
    facets: list[str] = []
    flags: list[str] = []


class GenList(BaseModel):
    type: Literal["list"]
    kind: str = ""
    title: str = ""
    items: list[str]
    order_principle: str = ""
    remarks: str = ""
    mnemonic: str = ""
    full: bool = True
    flags: list[str] = []


class LeftOut(BaseModel):
    text: str
    reason: str = ""


class GenOutput(BaseModel):
    cards: list[Annotated[GenQA | GenList, Field(discriminator="type")]]
    left_out: list[LeftOut] = []
    image_occlusion_candidates: list[str] = []
    flags: list[str] = []


_OUTPUT = TypeAdapter(GenOutput)

# Shown to the model as the shape to follow; parsed by the tests so it can't drift.
EXAMPLE_OUTPUT = {
    "cards": [
        {"type": "qa", "kind": "fact", "front": "Sacubitril (MoA, use) [2]",
         "back": "Neprilysin inhibitor; chronic heart failure with reduced ejection fraction (with valsartan)",
         "why": "Neprilysin breaks down natriuretic peptides; blocking it raises ANP/BNP, promoting "
                "natriuresis and vasodilation that oppose RAAS activation.",
         "add_reverse": False, "reverse_prompt": "", "facets": ["MoA", "use"], "flags": []},
        {"type": "qa", "kind": "fact", "front": "Rhodopsin peak absorption (value + unit)", "back": "~498 nm",
         "why": "Rods dominate scotopic vision, so dark-adapted sensitivity peaks near 500 nm, shorter than "
                "the photopic peak (the Purkinje shift).",
         "add_reverse": True, "reverse_prompt": "visual pigment with this absorption peak?",
         "facets": ["value"], "flags": []},
        {"type": "list", "kind": "set",
         "title": "Cranial nerves carrying parasympathetic fibres (in numerical order)",
         "items": ["Oculomotor (III)", "Facial (VII)", "Glossopharyngeal (IX)", "Vagus (X)"],
         "order_principle": "numerical", "remarks": "", "mnemonic": "1973 (III, VII, IX, X)", "full": True,
         "flags": []},
    ],
    "left_out": [{"text": "Course timetable and reading list", "reason": "not testable"}],
    "image_occlusion_candidates": ["p.4 diagram: layers of the retina"],
    "flags": [],
}


class GenerationError(Exception):
    """The model's reply could not be used."""


def parse_output(text: str) -> GenOutput:
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    try:
        data = json.loads(s)
    except json.JSONDecodeError as e:
        raise GenerationError("reply is not valid JSON (%s)" % e.msg) from e
    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise GenerationError('reply has no "cards" list')
    for c in data["cards"]:
        if isinstance(c, dict) and "type" not in c:
            c["type"] = "list" if "items" in c else "qa"
    try:
        return _OUTPUT.validate_python(data)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first["loc"])
        raise GenerationError("reply does not match the card format: %s: %s" % (where, first["msg"])) from e


def note_to_card(n: Note) -> dict:
    """A note in the reply format, so the model can revise it."""
    if n.type == "qa":
        return {"type": "qa", "kind": n.kind, "front": n.front, "back": n.back, "why": n.why,
                "add_reverse": n.add_reverse, "reverse_prompt": n.reverse_prompt, "facets": n.facets, "flags": []}
    return {"type": "list", "kind": n.kind, "title": n.title, "items": n.items, "order_principle": "",
            "remarks": n.why, "mnemonic": n.mnemonic, "full": n.full, "flags": []}


def parse_cards(cards: list[dict]) -> GenOutput:
    return _OUTPUT.validate_python({"cards": cards})


_REVERSE_IN_BACK = re.compile(r"\s*(?:<br\s*/?>|\n)?\s*\(r:\s*(.+?)\)\s*$", re.I)


def to_notes(out: GenOutput, document_id: str, source_id: str | None) -> list[Note]:
    notes = []
    for c in out.cards:
        common = dict(document_id=document_id, source_id=source_id, kind=c.kind, flags=c.flags,
                      tags=[GENERATED_TAG])
        if c.type == "qa":
            back, prompt = c.back, c.reverse_prompt
            m = _REVERSE_IN_BACK.search(back)
            if m:
                back, prompt = back[:m.start()], prompt or m.group(1)
            notes.append(Note(type="qa", front=c.front, back=back, why=c.why, add_reverse=c.add_reverse,
                              reverse_prompt=prompt, facets=c.facets, **common))
        else:
            notes.append(Note(type="list", title=c.title, items=c.items, why=c.remarks,
                              mnemonic=c.mnemonic, full=c.full, **common))
    return notes
