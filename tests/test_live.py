"""Real API calls (cost: a fraction of a cent). Run with: uv run pytest -m live"""
import base64
import os
from pathlib import Path

import pytest

from clanki.generation import parse_output
from clanki.llm import DeepSeek
from clanki.prompts import build_edit_messages, build_messages, build_transcribe_messages, load_profile

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


def test_flash_edit_follows_the_instruction(deepseek):
    card = {"type": "qa", "kind": "fact", "front": "Peak absorption wavelength of rhodopsin (value + unit)",
            "back": "~498 nm", "why": "", "add_reverse": False, "reverse_prompt": "", "facets": ["value"], "flags": []}
    msgs = build_edit_messages(load_profile(), title="Vision", pages=PAGES, card=card,
                               source_text="Rhodopsin, the rod visual pigment, absorbs maximally near 498 nm.",
                               source_pages=(1, 1), instruction="add a reverse card")
    r = deepseek.complete(msgs, model="deepseek-flash")
    assert r.finish_reason == "stop", r.finish_reason
    [c] = parse_output(r.text).cards
    print("\nusage %s, cost $%.5f\n - %s | %s | rev: %s | why: %s" % (
        r.usage, r.cost_usd, c.front, c.back, c.reverse_prompt, c.why))
    assert c.type == "qa" and c.add_reverse and c.reverse_prompt.strip()
    assert "498" in c.back


def test_flash_transcribes_a_diagram(deepseek):
    png = (Path(__file__).parent / "fixtures" / "raas.png").read_bytes()
    msgs = build_transcribe_messages(load_profile(), image="data:image/png;base64," + base64.b64encode(png).decode(),
                                     page_text="The renin-angiotensin-aldosterone system regulates blood pressure.")
    r = deepseek.complete(msgs, model="deepseek-flash", json_mode=False)
    print("\nusage %s, cost $%.5f\n%s" % (r.usage, r.cost_usd, r.text))
    assert r.finish_reason == "stop" and r.usage.cache_miss < 3000
    for s in ("Angiotensinogen", "Angiotensin II", "Aldosterone", "ACE inhibitor", "Renin", "→"):
        assert s in r.text


def _show(r, out):
    print("\nusage %s, cost $%.5f" % (r.usage, r.cost_usd))
    for c in out.cards:
        print(" -", c.type, "|", getattr(c, "front", None) or c.title, "|",
              getattr(c, "back", None) or "; ".join(c.items), "| why:", c.why if c.type == "qa" else c.remarks)
    print(" left out:", [x.text for x in out.left_out])


def test_flash_ml_profile_on_a_real_paper(deepseek):
    import httpx
    import io
    from pypdf import PdfReader
    from clanki.web import page_to_pdf
    _, pdf = page_to_pdf("https://arxiv.org/abs/1706.03762", httpx.Client())
    pages = [p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages]
    target_page = next(i for i, p in enumerate(pages) if "Scaled Dot-Product Attention" in p and "softmax" in p)
    start = pages[target_page].index("3.2.1")
    target = pages[target_page][start:start + 1400]
    msgs = build_messages(load_profile("ml_papers"), title="Attention Is All You Need", pages=pages, target=target,
                          target_pages=(target_page + 1, target_page + 1), focus="", mode="highlight")
    r = deepseek.complete(msgs, model="deepseek-flash")
    out = parse_output(r.text)
    _show(r, out)
    text = r.text.lower()
    assert out.cards and "\\\\(" in r.text and "this paper" not in text and "the proposed" not in text


def test_flash_general_profile(deepseek):
    pages = ["Ohm's law states that the current through a conductor between two points is directly proportional to "
             "the voltage across the two points. Introducing the constant of proportionality, the resistance, one "
             "arrives at I = V/R. The law was named after the German physicist Georg Ohm, who in 1827 described "
             "measurements of applied voltage and current through simple electrical circuits containing various "
             "lengths of wire."]
    msgs = build_messages(load_profile("general"), title="Ohm's law", pages=pages, target=pages[0],
                          target_pages=(1, 1), focus="", mode="highlight")
    r = deepseek.complete(msgs, model="deepseek-flash")
    out = parse_output(r.text)
    _show(r, out)
    assert out.cards and "ukmla" not in r.text.lower()
