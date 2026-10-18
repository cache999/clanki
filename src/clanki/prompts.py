"""Prompt profiles (src/clanki/prompts/<name>/) and the messages sent for one generation job."""
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .doctext import context_window, document_text
from .facets import vocabulary
from .generation import EXAMPLE_OUTPUT

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_PROFILE = "medical_ukmla"
MAX_CONTEXT_CHARS = 150_000  # ~40k tokens: above this, send only pages around the target


@dataclass(frozen=True)
class Profile:
    name: str
    label: str
    system: str
    transcribe: str = ""  # system prompt for reading an image into text


def _meta(name: str) -> dict:
    return tomllib.loads((PROMPTS / name / "profile.toml").read_text(encoding="utf-8"))


def facet_vocabulary(name: str = DEFAULT_PROFILE, facet_counts: dict | None = None) -> list[str]:
    """The profile's facets, extended by the ones the student uses most in Anki (facets.count_facets)."""
    f = _meta(name).get("facets", {})
    return vocabulary(facet_counts or {}, base=f.get("base", []), exclude=f.get("exclude", []),
                      size=f.get("size", 50), min_count=f.get("min_count", 5))


def load_profile(name: str = DEFAULT_PROFILE, facet_counts: dict | None = None) -> Profile:
    example = json.dumps(EXAMPLE_OUTPUT, ensure_ascii=False, indent=1)
    facets = ", ".join(facet_vocabulary(name, facet_counts))
    system = (PROMPTS / name / "system.md").read_text(encoding="utf-8")
    system = system.replace("{EXAMPLE}", example).replace("{FACETS}", facets).strip()
    transcribe = PROMPTS / name / "transcribe.md"
    return Profile(name=name, label=_meta(name)["label"], system=system,
                   transcribe=transcribe.read_text(encoding="utf-8").strip() if transcribe.exists() else "")


def list_profiles() -> list[Profile]:
    return [load_profile(p.name) for p in sorted(PROMPTS.iterdir()) if (p / "system.md").exists()]


def _pages_attr(first: int, last: int) -> str:
    return str(first) if first == last else "%d-%d" % (first, last)


def _document(title: str, pages: list[str], target_pages: tuple[int, int]) -> list[str]:
    """The document block that starts every user message, identical for every job on a document
    so the provider's prefix cache hits; only pages around the target for very long documents."""
    first, last = 1, len(pages)
    if sum(len(p) for p in pages) > MAX_CONTEXT_CHARS:
        first = context_window(len(pages), target_pages[0])[0]
        last = context_window(len(pages), target_pages[1])[1]
    return ['<document title="%s" pages="%s">' % (title.replace('"', "'"), _pages_attr(first, last)),
            document_text(pages, first, last), "</document>", ""]


def build_messages(profile: Profile, *, title: str, pages: list[str], target: str,
                   target_pages: tuple[int, int], focus: str, mode: str) -> list[dict]:
    """System prompt, then one user message: the document first, then the target and focus."""
    what = {"chunk": "The target is a whole section of the document: card all of it.",
            "figure": "The target was transcribed from a figure, diagram or image the student selected "
                      "(labels as \"label: what it points to\", links as \"A → B\"): card what it shows."
            }.get(mode, "The target is a passage the student highlighted.")
    focus_line = ("Focus: " + focus.strip()) if focus.strip() else \
        "Focus: none (card the testable, UKMLA-relevant content of the target)"
    user = "\n".join(_document(title, pages, target_pages) + [
        what,
        '<target pages="%s">' % _pages_attr(*target_pages),
        target.strip(),
        "</target>",
        "",
        focus_line,
        "",
        "Reply with the JSON object described in the system prompt.",
    ])
    return [{"role": "system", "content": profile.system}, {"role": "user", "content": user}]


def build_edit_messages(profile: Profile, *, title: str, pages: list[str], card: dict, source_text: str,
                        source_pages: tuple[int, int], instruction: str) -> list[dict]:
    """Revise one card following the student's instruction, with the same cached prefix."""
    parts = _document(title, pages, source_pages) + [
        "The student wants to change an existing card. Revise it following their instruction and the "
        "rules in the system prompt. Change only what the instruction asks for, plus anything that breaks "
        "a rule; keep everything else exactly as it is. Usually reply with one card; reply with several "
        "only if the instruction asks for a split or a rule requires one.",
        "<card>",
        json.dumps(card, ensure_ascii=False, indent=1),
        "</card>",
    ]
    if source_text.strip():
        parts += ['<source pages="%s">' % _pages_attr(*source_pages), source_text.strip(), "</source>"]
    parts += ["", "Instruction: " + instruction.strip(), "",
              'Reply with the JSON object described in the system prompt; leave "left_out" and '
              '"image_occlusion_candidates" empty.']
    return [{"role": "system", "content": profile.system}, {"role": "user", "content": "\n".join(parts)}]


def build_transcribe_messages(profile: Profile, *, image: str, page_text: str) -> list[dict]:
    """Read an image (a data URL) into text; the page's own text helps spell the labels."""
    context = ("Text on the same page (for spelling only):\n<page>\n%s\n</page>\n\n" % page_text.strip()
               if page_text.strip() else "")
    return [{"role": "system", "content": profile.transcribe},
            {"role": "user", "content": [{"type": "text", "text": context + "Transcribe the image."},
                                         {"type": "image_url", "image_url": {"url": image}}]}]
