"""Data shapes shared by the store, the exporters and the API."""
import secrets
import string
from typing import Literal

from pydantic import BaseModel, Field

_GUID_ALPHABET = string.ascii_letters + string.digits


def new_guid() -> str:
    """Anki note GUID: stable across exports, so a re-import updates instead of duplicating."""
    return "".join(secrets.choice(_GUID_ALPHABET) for _ in range(10))


class Note(BaseModel):
    """One Anki note. `type` qa -> Basic (optional reversed card); list -> Cloze (overlapping).

    For lists, `why` fills the Remarks field."""
    id: str | None = None
    guid: str = Field(default_factory=new_guid)
    document_id: str | None = None
    source_id: str | None = None
    type: Literal["qa", "list"]
    # qa
    front: str = ""
    back: str = ""
    add_reverse: bool = False
    reverse_prompt: str = ""
    # list
    title: str = ""
    items: list[str] = Field(default_factory=list)
    full: bool = True
    style: Literal["div", "ul"] = "div"
    mnemonic: str = ""
    sources: str = ""
    # both
    why: str = ""
    deck: str = ""
    tags: list[str] = Field(default_factory=list)
    # from generation: card kind (fact, linkage, concept, process, set), subquestion facets,
    # and the model's doubts (shown as warnings)
    kind: str = ""
    facets: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    # bookkeeping
    status: Literal["new", "sent", "edited"] = "new"
    deleted: bool = False
    anki_note_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    sent_at: str | None = None


class Document(BaseModel):
    id: str
    title: str
    filename: str
    kind: Literal["pdf", "pptx", "docx"]  # original format; every document is read as PDF
    deck: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str | None = None


class Source(BaseModel):
    """What cards were made from: a highlighted passage, or a page range for whole-document
    generation. `rects` are [x, y, w, h] as fractions of the page box, so they survive zoom
    changes."""
    id: str | None = None
    document_id: str
    kind: Literal["highlight", "chunk"] = "highlight"
    page: int
    page_end: int | None = None
    text: str
    rects: list[list[float]] = Field(default_factory=list)
    created_at: str | None = None


class Job(BaseModel):
    """One request to the LLM and what came of it: new cards from a highlight or a chunk, or a
    suggested revision of one card (mode "edit": focus holds the instruction, target the card
    as JSON, and the suggestion waits in proposal until accepted or discarded)."""
    id: str | None = None
    document_id: str
    source_id: str | None = None
    note_id: str | None = None
    mode: Literal["highlight", "chunk", "edit"]
    pages: tuple[int, int]
    target: str
    focus: str = ""
    profile: str = "medical_ukmla"
    model: str = "deepseek-flash"
    status: Literal["queued", "running", "done", "failed", "cancelled", "applied", "discarded"] = "queued"
    error: str | None = None
    attempts: int = 0
    usage: dict[str, int] = Field(default_factory=lambda: {"cache_hit": 0, "cache_miss": 0, "output": 0, "reasoning": 0})
    cost_usd: float = 0.0
    note_ids: list[str] = Field(default_factory=list)
    left_out: list[dict] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    image_occlusion: list[str] = Field(default_factory=list)
    proposal: list[dict] = Field(default_factory=list)
    before: dict | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
