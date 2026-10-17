"""Prompt profiles (src/clanki/prompts/<name>/) and the messages sent for one generation job."""
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .doctext import context_window, document_text
from .generation import EXAMPLE_OUTPUT

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_PROFILE = "medical_ukmla"
MAX_CONTEXT_CHARS = 150_000  # ~40k tokens: above this, send only pages around the target


@dataclass(frozen=True)
class Profile:
    name: str
    label: str
    system: str


def load_profile(name: str = DEFAULT_PROFILE) -> Profile:
    d = PROMPTS / name
    meta = tomllib.loads((d / "profile.toml").read_text(encoding="utf-8"))
    example = json.dumps(EXAMPLE_OUTPUT, ensure_ascii=False, indent=1)
    system = (d / "system.md").read_text(encoding="utf-8").replace("{EXAMPLE}", example).strip()
    return Profile(name=name, label=meta["label"], system=system)


def list_profiles() -> list[Profile]:
    return [load_profile(p.name) for p in sorted(PROMPTS.iterdir()) if (p / "system.md").exists()]


def _pages_attr(first: int, last: int) -> str:
    return str(first) if first == last else "%d-%d" % (first, last)


def build_messages(profile: Profile, *, title: str, pages: list[str], target: str,
                   target_pages: tuple[int, int], focus: str, mode: str) -> list[dict]:
    """System prompt, then one user message: the document first (identical for every job on a
    document, so the provider's prefix cache hits), then the target and focus."""
    first, last = 1, len(pages)
    if sum(len(p) for p in pages) > MAX_CONTEXT_CHARS:
        first = context_window(len(pages), target_pages[0])[0]
        last = context_window(len(pages), target_pages[1])[1]
    what = ("The target is a whole section of the document: card all of it." if mode == "chunk"
            else "The target is a passage the student highlighted.")
    focus_line = ("Focus: " + focus.strip()) if focus.strip() else \
        "Focus: none (card the testable, UKMLA-relevant content of the target)"
    user = "\n".join([
        '<document title="%s" pages="%s">' % (title.replace('"', "'"), _pages_attr(first, last)),
        document_text(pages, first, last),
        "</document>",
        "",
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
