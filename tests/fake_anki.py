"""In-memory stand-in for the AnkiConnect add-on, served through httpx.MockTransport."""
import json

import httpx

from clanki.anki_format import BASIC, BASIC_FIELDS, OVERLAP, OVERLAP_FIELDS


class FakeAnki:
    def __init__(self, models=None):
        self.models = models if models is not None else {BASIC: list(BASIC_FIELDS), OVERLAP: list(OVERLAP_FIELDS)}
        self.decks = {"Default"}
        self.notes = {}  # id -> {"modelName", "deckName", "fields", "tags"}
        self.next_id = 1000
        self.calls = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["version"] == 6
        self.calls.append(body["action"])
        try:
            result = getattr(self, "a_" + body["action"])(**body.get("params", {}))
            return httpx.Response(200, json={"result": result, "error": None})
        except Exception as e:  # AnkiConnect reports errors in-band
            return httpx.Response(200, json={"result": None, "error": str(e)})

    def _duplicate(self, note):
        first = next(iter(note["fields"].values()))
        return any(n["modelName"] == note["modelName"] and next(iter(n["fields"].values())) == first
                   for n in self.notes.values())

    def a_version(self):
        return 6

    def a_deckNames(self):
        return sorted(self.decks)

    def a_createDeck(self, deck):
        self.decks.add(deck)
        return 1

    def a_modelFieldNames(self, modelName):
        if modelName not in self.models:
            raise Exception("model was not found: " + modelName)
        return self.models[modelName]

    def a_canAddNotesWithErrorDetail(self, notes):
        out = []
        for n in notes:
            if n["deckName"] not in self.decks:
                out.append({"canAdd": False, "error": "deck was not found: " + n["deckName"]})
            elif self._duplicate(n):
                out.append({"canAdd": False, "error": "cannot create note because it is a duplicate"})
            else:
                out.append({"canAdd": True})
        return out

    def a_addNotes(self, notes):
        ids = []
        for n in notes:
            self.next_id += 1
            self.notes[self.next_id] = {k: n[k] for k in ("modelName", "deckName", "fields", "tags")}
            ids.append(self.next_id)
        return ids

    def a_updateNoteFields(self, note):
        if note["id"] not in self.notes:
            raise Exception("Note was not found: %s" % note["id"])
        self.notes[note["id"]]["fields"].update(note["fields"])
        return None
