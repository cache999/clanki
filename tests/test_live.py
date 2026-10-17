"""Real API calls (cost: a fraction of a cent). Run with: uv run pytest -m live"""
import os

import pytest

from clanki.generation import parse_output
from clanki.llm import DeepSeek
from clanki.prompts import build_messages, load_profile

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"), reason="DEEPSEEK_API_KEY not set")]

PAGES = ["Phototransduction\nRhodopsin, the rod visual pigment, absorbs maximally near 498 nm. Light isomerises "
         "11-cis retinal to all-trans retinal, activating transducin, which activates PDE6. PDE6 hydrolyses "
         "cGMP, closing cGMP-gated cation channels so the rod hyperpolarises."]


@pytest.fixture(scope="module")
def deepseek():
    return DeepSeek(os.environ["DEEPSEEK_API_KEY"])


def test_key_works(deepseek):
    deepseek.check()


def test_flash_returns_usable_cards(deepseek):
    msgs = build_messages(load_profile(), title="Vision", pages=PAGES, target=PAGES[0], target_pages=(1, 1),
                          focus="", mode="highlight")
    r = deepseek.complete(msgs, model="deepseek-flash")
    assert r.finish_reason == "stop", r.finish_reason
    out = parse_output(r.text)
    assert out.cards
    assert r.usage.cache_hit + r.usage.cache_miss > 1000 and r.usage.output > 0
    assert 0 < r.cost_usd < 0.05
    print("\n%d cards, usage %s, cost $%.5f" % (len(out.cards), r.usage, r.cost_usd))
    for c in out.cards:
        print(" -", c.type, "|", getattr(c, "front", None) or c.title, "|",
              getattr(c, "back", None) or "; ".join(c.items), "| rev:", getattr(c, "reverse_prompt", ""))
