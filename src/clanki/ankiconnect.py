"""Client for the AnkiConnect add-on (https://foosoft.net/projects/anki-connect/, API version 6)."""
from dataclasses import dataclass
from typing import Literal

import httpx

from .anki_format import BASIC, BASIC_FIELDS, CLOZE, CLOZE_FIELDS, OVERLAP, OVERLAP_FIELDS, clean_tags, note_fields
from .models import Note

DEFAULT_URL = "http://127.0.0.1:8765"
EXPECTED_FIELDS = {BASIC: BASIC_FIELDS, OVERLAP: OVERLAP_FIELDS, CLOZE: CLOZE_FIELDS}
RENAMED = {CLOZE: {"Extra": "Back Extra"}}  # the name newer Ankis give a field


class AnkiError(Exception):
    """AnkiConnect answered with an error."""


class AnkiUnavailable(AnkiError):
    """Anki is closed or AnkiConnect is not installed."""


@dataclass
class SendResult:
    note_id: str
    action: Literal["added", "updated", "skipped", "failed"]
    anki_note_id: int | None = None
    error: str | None = None


class AnkiConnect:
    def __init__(self, url: str = DEFAULT_URL, transport: httpx.BaseTransport | None = None, timeout: float = 10):
        self.url = url
        self._http = httpx.Client(transport=transport, timeout=timeout)
        self._names: dict[str, dict[str, str]] = {}

    def call(self, action: str, **params):
        try:
            r = self._http.post(self.url, json={"action": action, "version": 6, "params": params})
        except httpx.TransportError as e:
            raise AnkiUnavailable("AnkiConnect not reachable at %s: is Anki open with the "
                                  "AnkiConnect add-on?" % self.url) from e
        body = r.json()
        if body.get("error"):
            raise AnkiError(body["error"])
        return body.get("result")

    def status(self) -> dict:
        try:
            version = self.call("version")
        except AnkiUnavailable as e:
            return {"connected": False, "version": None, "problems": [str(e)]}
        problems = []
        for model, expected in EXPECTED_FIELDS.items():
            try:
                fields = self.call("modelFieldNames", modelName=model)
            except AnkiError:
                problems.append("Note type '%s' not found in Anki" % model)
                continue
            renamed = [RENAMED.get(model, {}).get(f, f) for f in expected]
            if fields[:len(expected)] not in (expected, renamed):
                problems.append("Note type '%s' fields should start with: %s%s" % (
                    model, ", ".join(expected),
                    "".join(" (or %s)" % new for new in RENAMED.get(model, {}).values())))
        return {"connected": True, "version": version, "problems": problems}

    def _note_fields(self, n: Note) -> tuple[str, dict[str, str]]:
        """note_fields, with the field names this collection uses."""
        model, fields = note_fields(n)
        if model not in RENAMED:
            return model, fields
        if model not in self._names:
            try:
                have = self.call("modelFieldNames", modelName=model)
            except AnkiUnavailable:
                raise
            except AnkiError:  # no such note type: adding the note fails and says so
                have = []
            self._names[model] = {old: new for old, new in RENAMED[model].items() if old not in have and new in have}
        return model, {self._names[model].get(k, k): v for k, v in fields.items()}

    def deck_names(self) -> list[str]:
        return self.call("deckNames")

    def send(self, notes: list[Note], default_deck: str) -> list[SendResult]:
        """Add new notes, update edited ones, skip notes already up to date in Anki.
        Results are in input order."""
        self._names = {}  # note type -> renamed fields, looked up again on each send
        results: dict[str, SendResult] = {}
        new = []
        for n in notes:
            if n.anki_note_id is None:
                new.append(n)
            elif n.status == "edited":
                results[n.id] = self._update(n)
            else:
                results[n.id] = SendResult(n.id, "skipped", n.anki_note_id)
        if new:
            results.update(self._add(new, default_deck))
        return [results[n.id] for n in notes]

    def _update(self, n: Note) -> SendResult:
        try:
            _, fields = self._note_fields(n)
            self.call("updateNoteFields", note={"id": n.anki_note_id, "fields": fields})
        except AnkiError as e:
            return SendResult(n.id, "failed", n.anki_note_id, str(e))
        return SendResult(n.id, "updated", n.anki_note_id)

    def _add(self, notes: list[Note], default_deck: str) -> dict[str, SendResult]:
        payloads = []
        for n in notes:
            model, fields = self._note_fields(n)
            payloads.append({"deckName": n.deck or default_deck, "modelName": model, "fields": fields,
                             "tags": clean_tags(n.tags), "options": {"allowDuplicate": False}})
        for deck in sorted({p["deckName"] for p in payloads}):
            self.call("createDeck", deck=deck)
        checks = self.call("canAddNotesWithErrorDetail", notes=payloads)
        out, ok = {}, []
        for n, p, c in zip(notes, payloads, checks):
            if c.get("canAdd"):
                ok.append((n, p))
            else:
                out[n.id] = SendResult(n.id, "failed", error=c.get("error") or "cannot add note")
        if ok:
            try:
                ids = self.call("addNotes", notes=[p for _, p in ok])
            except AnkiError as e:
                ids = [None] * len(ok)
                err = str(e)
            else:
                err = "Anki did not add the note"
            for (n, _), nid in zip(ok, ids):
                out[n.id] = SendResult(n.id, "added", nid) if nid else SendResult(n.id, "failed", error=err)
        return out
