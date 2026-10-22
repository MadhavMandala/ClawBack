import httpx
import openai
import pytest

from clawback import llm
from clawback.store import store

LIGHTNING = "nvidia/Nemotron-3_5-Lightning"
NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
MSGS = [{"role": "user", "content": "hi"}]
SCHEMA = {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"],
          "additionalProperties": False}


@pytest.fixture(autouse=True)
def fresh_user():
    store.reset("t")


def make_rate_limit_error():
    return openai.RateLimitError(
        "rate", response=httpx.Response(429, request=httpx.Request("POST", "http://x")), body=None
    )


def test_chat_sends_schema_thinking_flag_and_timeout(fake_llm):
    llm.chat("t", "extract", "fast", MSGS, schema=SCHEMA)
    kw = fake_llm.calls[0]
    assert kw["model"] == LIGHTNING
    assert kw["response_format"]["type"] == "json_schema" and kw["response_format"]["json_schema"]["strict"] is True
    assert kw["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert kw["timeout"] == 20


def test_fast_tier_refuses_thinking(fake_llm):
    with pytest.raises(ValueError):
        llm.chat("t", "extract", "fast", MSGS, thinking=True)
    assert fake_llm.calls == []


def test_chat_json_falls_back_to_nano_on_bad_json(fake_llm):
    fake_llm.script = {LIGHTNING: ["not json"], NANO: ['{"kind": "trial"}']}
    data, res = llm.chat_json("t", "extract", "fast", MSGS, SCHEMA)
    assert data == {"kind": "trial"} and res.model == NANO
    assert [s.status for s in store.user("t").trace] == ["ok", "fallback", "ok"]


def test_chat_json_all_fail_returns_none(fake_llm):
    fake_llm.script = {LIGHTNING: [RuntimeError("down")] * 2, NANO: [RuntimeError("down")] * 2}
    assert llm.chat_json("t", "extract", "fast", MSGS, SCHEMA) == (None, None)
    assert "error" in {s.status for s in store.user("t").trace}


def test_retry_once_on_rate_limit(fake_llm):
    fake_llm.script = {ULTRA: [make_rate_limit_error(), '{"ok": true}']}
    data, _ = llm.chat_json("t", "alternatives", "reason", MSGS, SCHEMA, thinking=True)
    assert data == {"ok": True} and len(fake_llm.calls) == 2


def test_trace_row_has_tier_and_cost(fake_llm):
    llm.chat("t", "extract", "fast", MSGS)
    row = store.user("t").trace[-1]
    assert row.tier == "fast" and row.cost_usd == pytest.approx(100 / 1e6 * 0.06 + 20 / 1e6 * 0.24)
