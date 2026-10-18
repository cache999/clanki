"""LLM providers. DeepSeek for now (OpenAI-compatible API); Claude is future work."""
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import openai

DEEPSEEK_URL = "https://api.deepseek.com"
# USD per million tokens at peak: (input cache hit, input cache miss, output); off-peak is half.
# From api-docs.deepseek.com/quick_start/pricing, 2026-10-17.
DEEPSEEK_PRICES = {
    "deepseek-flash": (0.006, 0.30, 1.20),
    "deepseek-v4-pro": (0.044, 1.32, 3.96),
}
PROVIDER_MODELS = {"deepseek": list(DEEPSEEK_PRICES)}
DEFAULT_MODEL = "deepseek-flash"
# Mon-Fri, UTC. DeepSeek also treats Chinese public holidays as off-peak; ignoring them only
# overstates the cost on those days.
PEAK_HOURS_UTC = ((1, 4), (6, 10))


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class Usage:
    cache_hit: int
    cache_miss: int
    output: int
    reasoning: int


@dataclass(frozen=True)
class LLMResult:
    text: str
    finish_reason: str
    model: str
    usage: Usage
    cost_usd: float


def is_peak(t: datetime) -> bool:
    t = t.astimezone(timezone.utc)
    return t.weekday() < 5 and any(a <= t.hour < b for a, b in PEAK_HOURS_UTC)


def cost(model: str, u: Usage, at: datetime) -> float:
    hit, miss, out = DEEPSEEK_PRICES[model]
    factor = 1 if is_peak(at) else 0.5
    return factor * (u.cache_hit * hit + u.cache_miss * miss + u.output * out) / 1e6


class DeepSeek:
    name = "deepseek"

    def __init__(self, api_key: str, base_url: str = DEEPSEEK_URL,
                 http_client: httpx.Client | None = None, max_retries: int = 2, timeout: float = 600):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url, http_client=http_client,
                                    max_retries=max_retries, timeout=timeout)

    def _call(self, fn):
        try:
            return fn()
        except openai.AuthenticationError as e:
            raise LLMError("DeepSeek rejected the API key") from e
        except openai.RateLimitError as e:
            raise LLMError("DeepSeek rate limit reached: wait a moment and retry") from e
        except openai.APIConnectionError as e:
            raise LLMError("could not reach DeepSeek: check the internet connection") from e
        except openai.APIStatusError as e:
            if e.status_code == 402:
                raise LLMError("DeepSeek account balance is insufficient: top up at platform.deepseek.com") from e
            raise LLMError("DeepSeek error %d: %s" % (e.status_code, e.message)) from e

    def complete(self, messages: list[dict], *, model: str, effort: str = "high", max_tokens: int = 32000,
                 now: datetime | None = None, json_mode: bool = True) -> LLMResult:
        """json_mode=False for a plain-text reply. Message content may include images
        ({"type": "image_url", ...}); deepseek-flash reads them (at most ~1300×1300 px each)."""
        if model not in DEEPSEEK_PRICES:
            raise LLMError("unknown model %r (choose from %s)" % (model, ", ".join(DEEPSEEK_PRICES)))
        fmt = {"response_format": {"type": "json_object"}} if json_mode else {}
        r = self._call(lambda: self.client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, **fmt,
            extra_body={"thinking": {"type": "enabled"}, "reasoning_effort": effort}))
        u = r.usage
        # DeepSeek's own fields, falling back to the OpenAI-style ones
        hit = getattr(u, "prompt_cache_hit_tokens", None)
        if hit is None:
            hit = getattr(u.prompt_tokens_details, "cached_tokens", 0) or 0
        miss = getattr(u, "prompt_cache_miss_tokens", None)
        if miss is None:
            miss = u.prompt_tokens - hit
        reasoning = getattr(u.completion_tokens_details, "reasoning_tokens", 0) or 0
        usage = Usage(cache_hit=hit, cache_miss=miss, output=u.completion_tokens, reasoning=reasoning)
        choice = r.choices[0]
        return LLMResult(text=choice.message.content or "", finish_reason=choice.finish_reason or "",
                         model=model, usage=usage, cost_usd=cost(model, usage, now or datetime.now(timezone.utc)))

    def check(self) -> None:
        """A free call that fails if the key is wrong."""
        self._call(lambda: self.client.models.list())
