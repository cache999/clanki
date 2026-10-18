"""Facets: the generic subquestions in a front's trailing bracket, as in "Sacubitril (MoA, use) [2]".
Mined from the student's Anki cards, they become the vocabulary the prompt asks the model to use,
and they help match a new card against existing ones."""
import html
import re
from collections import Counter

# Abbreviations only: plurals ("causes", "functions") ask for several answers, so they stay distinct.
SYNONYMS = {"def": "definition", "defn": "definition", "pathophys": "pathophysiology", "desc": "describe"}
_STOP = {"a", "an", "the", "of", "in", "on", "for", "to", "and", "with", "by", "at", "from", "is", "are", "its"}
_COUNT = re.compile(r"\s*\[\d+\]\s*$")
_TAIL = re.compile(r"\(([^()]*)\)\s*$")
_SEP = re.compile(r"\s*(?:,|\+|/|;|&|\band\b)\s*")


def plain(s: str) -> str:
    """Card HTML as plain text on one line."""
    s = html.unescape(re.sub(r"<[^>]*>", " ", s)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _parts(inner: str) -> list[tuple[str, str]]:
    """(key, display form) for each facet in a bracket's contents."""
    out = []
    for p in _SEP.split(inner):
        p = p.strip().rstrip("?.").strip()
        if p:
            key = SYNONYMS.get(p.lower(), p.lower())
            out.append((key, key if key != p.lower() else p))
    return out


def _split(front: str) -> tuple[str, list[tuple[str, str]]]:
    s = _COUNT.sub("", plain(front))
    m = _TAIL.search(s)
    return (s[:m.start()].strip(), _parts(m.group(1))) if m else (s, [])


def split_front(front: str) -> tuple[str, list[str]]:
    """The entity asked about, and its facets (normalised, lower case)."""
    entity, parts = _split(front)
    return entity, [k for k, _ in parts]


def entity_key(entity: str) -> str:
    """Compares entities regardless of word order, case and small words."""
    return " ".join(sorted({w for w in re.findall(r"\w+", plain(entity).lower()) if w not in _STOP}))


def _display(forms: Counter) -> str:
    s = forms.most_common(1)[0][0]
    return s.lower() if s[1:] == s[1:].lower() else s  # "Definition" -> "definition"; "MoA", "DNA" stay


def count_facets(fronts: list[str]) -> dict[str, list]:
    """facet key -> [number of fronts using it, how the student writes it]."""
    forms: dict[str, Counter] = {}
    for f in fronts:
        for key, shown in dict(_split(f)[1]).items():
            forms.setdefault(key, Counter())[shown] += 1
    return {k: [sum(c.values()), _display(c)] for k, c in forms.items()}


def vocabulary(counts: dict[str, list], *, base: list[str], exclude: list[str], size: int,
               min_count: int = 5) -> list[str]:
    """The base list (curated, in order), then the student's most used other facets up to size,
    alphabetically so the prompt (and its cache) stays the same while counts creep up."""
    out, seen = [], {SYNONYMS.get(x.lower(), x.lower()) for x in exclude}
    for b in base:
        if b.lower() not in seen:
            out.append(b)
            seen.add(b.lower())
    extras = sorted(((c, k, shown) for k, (c, shown) in counts.items() if k not in seen and c >= min_count),
                    key=lambda x: (-x[0], x[1]))[:max(0, size - len(out))]
    return out + sorted((shown for _, _, shown in extras), key=str.lower)
