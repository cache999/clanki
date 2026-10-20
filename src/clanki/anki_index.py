"""A snapshot of the student's Anki notes, read through AnkiConnect (under a second for ~17k notes).
It warns when a new card repeats one already in Anki, and supplies the facet counts for the prompt.
Kept in clanki's database, so the warnings work while Anki is closed."""
import re
from collections import defaultdict
from datetime import datetime, timezone

from .anki_format import BASIC, CLOZE, OVERLAP, reveal
from .ankiconnect import AnkiConnect
from .facets import count_facets, entity_key, plain, split_front
from .generation import REVERSE_IN_BACK
from .models import Note
from .validators import Issue

_BATCH = 1000


def _key(s: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in plain(s).lower()).split())


def _short(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def cloze_lines(text: str) -> tuple[str, str]:
    """A cloze's first line (its title, or the whole sentence) and the rest, answers shown, as plain text."""
    first, *rest = re.split(r"<br\s*/?>|</?div>|\n", reveal(text), maxsplit=1)
    return plain(first), plain(" ".join(rest))


class AnkiIndex:
    def __init__(self, notes: list[dict], facet_counts: dict, refreshed_at: str | None):
        """notes: {"id", "type", "first" (Front or Title), "back" (Back without the reverse prompt,
        or a list's items), "reverse", "deck"}, all plain text."""
        self.notes, self.facet_counts, self.refreshed_at = notes, facet_counts, refreshed_at
        self._by_entity = defaultdict(list)
        self._reversed_by_back = defaultdict(list)
        for a in notes:
            entity, facets = split_front(a["first"])
            if entity_key(entity):
                self._by_entity[entity_key(entity)].append((a, set(facets)))
            if a["reverse"] and _key(a["back"]):
                self._reversed_by_back[_key(a["back"])].append(a)

    @classmethod
    def empty(cls) -> "AnkiIndex":
        return cls([], {}, None)

    @classmethod
    def fetch(cls, anki: AnkiConnect) -> "AnkiIndex":
        notes, cards, fronts = [], {}, []
        for model in (BASIC, OVERLAP, CLOZE):
            ids = anki.call("findNotes", query='"note:%s"' % model)
            for i in range(0, len(ids), _BATCH):
                for info in anki.call("notesInfo", notes=ids[i:i + _BATCH]):
                    f = {k: v["value"] for k, v in info["fields"].items()}
                    if model == BASIC:
                        fronts.append(f.get("Front", ""))
                        a = {"type": "qa", "first": plain(f.get("Front", "")), "reverse": bool(f.get("Add Reverse", "").strip()),
                             "back": plain(REVERSE_IN_BACK.sub("", f.get("Back", "")))}
                    elif model == CLOZE:
                        first, rest = cloze_lines(f.get("Text", ""))
                        a = {"type": "cloze", "first": first, "reverse": False, "back": rest}
                    else:
                        a = {"type": "list", "first": plain(f.get("Title", "")), "reverse": False,
                             "back": plain(f.get("Original", ""))}
                    notes.append({"id": info["noteId"], "deck": "", **a})
                    cards.update({c: len(notes) - 1 for c in info["cards"][:1]})
        if cards:
            for deck, cids in anki.call("getDecks", cards=list(cards)).items():
                for c in cids:
                    notes[cards[c]]["deck"] = deck
        return cls(notes, count_facets(fronts), datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_dict(cls, d: dict) -> "AnkiIndex":
        return cls(d["notes"], d["facet_counts"], d["refreshed_at"])

    def to_dict(self) -> dict:
        return {"notes": self.notes, "facet_counts": self.facet_counts, "refreshed_at": self.refreshed_at}

    def summary(self) -> dict:
        return {"notes": len(self.notes), "refreshed_at": self.refreshed_at}

    def check(self, notes: list[Note]) -> list[list[Issue]]:
        """Warnings per note, for cards not yet in Anki: the same entity asked about on a shared
        facet (or either card asks without facets), and reverse cards whose Back a reversed Anki
        card already has."""
        return [[] if n.deleted or n.anki_note_id is not None else self._check_one(n) for n in notes]

    def _check_one(self, n: Note) -> list[Issue]:
        out = []
        first = {"qa": n.front, "list": n.title, "cloze": cloze_lines(n.text)[0]}[n.type]
        entity, facets = split_front(first)
        matches = [a for a, fs in self._by_entity.get(entity_key(entity), []) if not fs or not facets or fs & set(facets)]
        if matches:
            a = matches[0]
            what = "Already in Anki" if a["first"].lower() == plain(first).lower() else "Similar card in Anki"
            more = " (+%d more)" % (len(matches) - 1) if len(matches) > 1 else ""
            out.append(Issue(level="warning", code="in_anki", message='%s: "%s" → %s (%s)%s' % (
                what, a["first"], _short(a["back"]), a["deck"], more)))
        if n.type == "qa" and n.add_reverse:
            for a in self._reversed_by_back.get(_key(n.back), [])[:1]:
                out.append(Issue(level="warning", code="anki_shared_back", message=(
                    'Same Back as "%s" in Anki, which also has a reverse card: the reverse would be '
                    'ambiguous' % a["first"])))
        return out
