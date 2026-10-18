"""Stand-in LLM providers for tests and for tests/e2e_server.py."""
import json
import re

from clanki.llm import LLMError, LLMResult, Usage


class ScriptedLLM:
    """Replies with the given texts in turn (an Exception instance is raised instead)."""

    def __init__(self, *replies, finish="stop", on_call=None):
        self.replies = list(replies)
        self.finish = finish
        self.on_call = on_call
        self.calls = []

    def complete(self, messages, *, model, **kw):
        self.calls.append({"messages": messages, "model": model, "kw": kw})
        if self.on_call:
            self.on_call()
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        finish = self.finish if isinstance(self.finish, str) else self.finish.pop(0)
        return LLMResult(text=r, finish_reason=finish, model=model,
                         usage=Usage(cache_hit=100, cache_miss=50, output=20, reasoning=5), cost_usd=0.001)

    def check(self):
        pass


class EchoLLM:
    """Deterministic cards from the target text, so the UI can be driven end to end."""

    def complete(self, messages, *, model, **kw):
        user = messages[-1]["content"]
        if isinstance(user, list):  # an image to transcribe
            text = "Figure: nerve supply\nMedian nerve: carpal tunnel\nUlnar nerve: Guyon's canal\nC5 → C6 → C7"
            return LLMResult(text=text, finish_reason="stop", model=model,
                             usage=Usage(cache_hit=0, cache_miss=900, output=60, reasoning=30), cost_usd=0.0003)
        card = re.search(r"<card>\n(.*?)\n</card>", user, re.S)
        if card:  # an AI edit: echo the instruction into the front; "split" makes two cards
            c = json.loads(card.group(1))
            instruction = re.search(r"^Instruction: (.*)$", user, re.M).group(1)
            if c["type"] == "qa":
                c["front"] = "Edited: " + instruction
            else:
                c["title"] = "Edited: " + instruction
            cards = [c] + ([{**c, "front": "Second card", "back": "split off"}] if "split" in instruction else [])
            out = {"cards": cards, "left_out": [], "image_occlusion_candidates": [], "flags": []}
            return LLMResult(text=json.dumps(out), finish_reason="stop", model=model,
                             usage=Usage(cache_hit=1000, cache_miss=100, output=100, reasoning=20), cost_usd=0.0001)
        target = re.search(r"<target[^>]*>\n(.*?)\n</target>", user, re.S).group(1)
        focus = re.search(r"^Focus: (.*)$", user, re.M).group(1)
        lines = [l.strip("• ").strip() for l in target.splitlines() if l.strip()]
        cards = [{"type": "qa", "kind": "fact", "front": "Generated: " + " ".join(lines[0].split()[:6]),
                  "back": lines[0][:80], "why": "focus was " + focus, "add_reverse": False,
                  "reverse_prompt": "", "facets": [], "flags": []}]
        if len(lines) >= 3:
            cards.append({"type": "list", "kind": "set", "title": "Generated list", "items": lines[1:],
                          "order_principle": "as in source", "remarks": "", "mnemonic": "", "full": True,
                          "flags": ["check the order"]})
        out = {"cards": cards, "left_out": [{"text": "a left-out sentence", "reason": "not testable"}],
               "image_occlusion_candidates": [], "flags": []}
        return LLMResult(text=json.dumps(out), finish_reason="stop", model=model,
                         usage=Usage(cache_hit=0, cache_miss=1000, output=200, reasoning=50), cost_usd=0.0004)

    def check(self):
        pass


def failing(message="DeepSeek rejected the API key"):
    return LLMError(message)
