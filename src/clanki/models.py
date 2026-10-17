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
    """A highlighted passage. `rects` are [x, y, w, h] as fractions of the page box, so they
    survive zoom changes."""
    id: str | None = None
    document_id: str
    page: int
    text: str
    rects: list[list[float]] = Field(default_factory=list)
    created_at: str | None = None
