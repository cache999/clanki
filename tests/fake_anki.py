"""In-memory stand-in for the AnkiConnect add-on, served through httpx.MockTransport."""
import base64
import json
import re

import httpx

from clanki.anki_format import BASIC, BASIC_FIELDS, OVERLAP, OVERLAP_FIELDS


class FakeAnki:
    def __init__(self, models=None):
        self.models = models if models is not None else {BASIC: list(BASIC_FIELDS), OVERLAP: list(OVERLAP_FIELDS)}
        self.decks = {"Default"}
        self.notes = {}  # id -> {"modelName", "deckName", "fields", "tags"}
        self.media = {}  # filename -> bytes
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

    def add(self, model: str, deck: str = "Default", **fields) -> int:
        """Put a note straight into the collection (as if made in Anki)."""
        self.decks.add(deck)
        names = self.models[model]
        return self.a_addNotes([{"modelName": model, "deckName": deck, "tags": [],
                                 "fields": {k: fields.get(k.replace(" ", "_"), "") for k in names}}])[0]

    # reads; a note's card ids are id*10 (+1 for a second card)
    def a_findNotes(self, query):
        m = re.fullmatch(r'"note:(.+)"', query)
        return [i for i, n in self.notes.items() if m is None or n["modelName"] == m.group(1)]

    def a_notesInfo(self, notes):
        return [{"noteId": i, "modelName": self.notes[i]["modelName"], "tags": self.notes[i]["tags"],
                 "fields": {k: {"value": v, "order": j} for j, (k, v) in enumerate(self.notes[i]["fields"].items())},
                 "cards": [i * 10]} for i in notes if i in self.notes]

    def a_getDecks(self, cards):
        out = {}
        for c in cards:
            out.setdefault(self.notes[c // 10]["deckName"], []).append(c)
        return out

    def a_storeMediaFile(self, filename, data):
        self.media[filename] = base64.b64decode(data)
        return filename

    def a_updateNoteFields(self, note):
        if note["id"] not in self.notes:
            raise Exception("Note was not found: %s" % note["id"])
        self.notes[note["id"]]["fields"].update(note["fields"])
        return None
