import json
from datetime import datetime, timezone

import httpx
import pytest

from clanki import llm


def deepseek_reply(content='{"cards": []}', finish="stop", hit=1000, miss=200, out=300, reasoning=120):
    return {
        "id": "x", "object": "chat.completion", "created": 1, "model": "deepseek-flash",
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": content, "reasoning_content": "thinking…"}}],
        "usage": {"prompt_tokens": hit + miss, "completion_tokens": out, "total_tokens": hit + miss + out,
                  "prompt_cache_hit_tokens": hit, "prompt_cache_miss_tokens": miss,
                  "prompt_tokens_details": {"cached_tokens": hit},
                  "completion_tokens_details": {"reasoning_tokens": reasoning}},
    }


def provider(handler):
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    p = llm.DeepSeek(api_key="sk-test", http_client=httpx.Client(transport=httpx.MockTransport(wrapped)),
                     max_retries=0)
    return p, seen


MSGS = [{"role": "system", "content": "Reply in JSON"}, {"role": "user", "content": "hi"}]


def test_request_uses_json_mode_thinking_and_effort():
    p, seen = provider(lambda r: httpx.Response(200, json=deepseek_reply()))
    p.complete(MSGS, model="deepseek-v4-pro", effort="max")
    [req] = seen
    assert req.url.path.endswith("/chat/completions")
    assert req.headers["authorization"] == "Bearer sk-test"
    body = json.loads(req.content)
    assert body["model"] == "deepseek-v4-pro" and body["messages"] == MSGS
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "enabled"} and body["reasoning_effort"] == "max"
    assert body["max_tokens"] >= 16000


def test_result_carries_text_usage_and_cost():
    p, _ = provider(lambda r: httpx.Response(200, json=deepseek_reply('{"cards": [1]}')))
    off_peak = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)  # a Saturday
    r = p.complete(MSGS, model="deepseek-flash", now=off_peak)
    assert r.text == '{"cards": [1]}' and r.finish_reason == "stop" and r.model == "deepseek-flash"
    assert r.usage == llm.Usage(cache_hit=1000, cache_miss=200, output=300, reasoning=120)
    # off-peak flash: 1000*0.003 + 200*0.15 + 300*0.6 per million
    assert r.cost_usd == pytest.approx((1000 * 0.003 + 200 * 0.15 + 300 * 0.6) / 1e6)


def test_peak_hours():
    assert llm.is_peak(datetime(2026, 10, 19, 7, 30, tzinfo=timezone.utc))  # Monday 07:30 UTC
    assert llm.is_peak(datetime(2026, 10, 19, 1, 0, tzinfo=timezone.utc))
    assert not llm.is_peak(datetime(2026, 10, 19, 4, 0, tzinfo=timezone.utc))
    assert not llm.is_peak(datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc))
    assert not llm.is_peak(datetime(2026, 10, 18, 7, 30, tzinfo=timezone.utc))  # Sunday


def test_peak_cost_is_double():
    u = llm.Usage(cache_hit=0, cache_miss=1_000_000, output=0, reasoning=0)
    peak = llm.cost("deepseek-v4-pro", u, datetime(2026, 10, 19, 7, 0, tzinfo=timezone.utc))
    off = llm.cost("deepseek-v4-pro", u, datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc))
    assert (peak, off) == (pytest.approx(1.32), pytest.approx(0.66))


@pytest.mark.parametrize("status,message", [
    (401, "rejected the API key"), (402, "balance"), (429, "rate limit"), (500, "DeepSeek error 500"),
])
def test_api_errors_become_readable(status, message):
    p, _ = provider(lambda r: httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(llm.LLMError, match=message):
        p.complete(MSGS, model="deepseek-flash")


def test_connection_failure_is_readable():
    def down(request):
        raise httpx.ConnectError("no route")
    p, _ = provider(down)
    with pytest.raises(llm.LLMError, match="could not reach DeepSeek"):
        p.complete(MSGS, model="deepseek-flash")


def test_unknown_model_is_rejected_before_calling():
    p, seen = provider(lambda r: httpx.Response(200, json=deepseek_reply()))
    with pytest.raises(llm.LLMError, match="unknown model"):
        p.complete(MSGS, model="gpt-4")
    assert seen == []


def test_check_lists_models():
    p, seen = provider(lambda r: httpx.Response(200, json={"object": "list", "data": [
        {"id": "deepseek-flash", "object": "model", "owned_by": "deepseek"}]}))
    p.check()
    assert seen[0].url.path.endswith("/models")
