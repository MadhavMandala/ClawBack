"""Nebius Token Factory client (OpenAI-compatible).

Model IDs and prices come from the public Token Factory catalog, checked 2026-10-22:
https://tokenfactory.nebius.com/api/public/models_info

Verified live on 2026-10-22: all five models honour `response_format` (strict JSON schema) and
`chat_template_kwargs.enable_thinking`. Lightning must never think: it writes its reasoning into `content`.
Super, Ultra and Super-VL return reasoning separately in `reasoning_content`, which we never show.

Smoke test (one tiny call per tier):  python -m clawback.llm --check
"""

from __future__ import annotations

import functools
import json
import re
import time
from dataclasses import dataclass

from .config import settings
from .trace import record

# One row per tier: which model, its backup tier, whether thinking may be on, and limits.
@dataclass(frozen=True)
class Tier:
    model: str
    fallback: str | None
    thinking_allowed: bool
    max_tokens: int
    timeout_s: float


TIERS: dict[str, Tier] = {
    # Lightning writes its reasoning into the answer text when thinking is on, so it never thinks.
    "fast": Tier("nvidia/Nemotron-3_5-Lightning", "fast_fallback", False, 300, 20),  # email extraction
    "fast_fallback": Tier("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", None, False, 300, 20),
    "mid": Tier("nvidia/nemotron-3-super-120b-a12b", None, True, 2000, 60),  # read plan / pricing pages
    "reason": Tier("nvidia/Nemotron-3-Ultra-550b-a55b", None, True, 2000, 90),  # fit to usage, email wording
    "vision": Tier("nvidia/Nemotron-3.5-Super-VL", None, True, 1024, 60),  # receipts as images (MISSING [pdf-receipts])
}

MODELS = {role: tier.model for role, tier in TIERS.items()}

# USD per 1M tokens (input, output)
PRICES = {
    "nvidia/Nemotron-3_5-Lightning": (0.06, 0.24),
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
    "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
    "nvidia/Nemotron-3.5-Super-VL": (0.30, 0.90),
}


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    ms: float
    reasoning_tokens: int = 0


def available() -> bool:
    return bool(settings.nebius_api_key)


class ThinkingNotAllowed(ValueError):
    """Asked for thinking on a tier that must not think (Lightning)."""


@functools.cache
def _make_client(base_url: str, api_key: str):
    from openai import OpenAI

    # The SDK retries twice by default; our own single retry is the only one, so a click can't hang for minutes.
    return OpenAI(base_url=base_url, api_key=api_key, max_retries=0)


def _client():
    if not settings.nebius_api_key:
        raise RuntimeError("NEBIUS_API_KEY is not set in backend/.env")
    return _make_client(settings.nebius_base_url, settings.nebius_api_key)


def _retryable(exc: Exception) -> bool:
    """Retry once on rate limits, dropped connections and server errors. Not on timeouts: one is long enough."""
    import openai

    if isinstance(exc, (openai.RateLimitError, openai.APIConnectionError)) and not isinstance(exc, openai.APITimeoutError):
        return True
    return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500


def chat(
    user_id: str,
    stage: str,
    role: str,
    messages: list[dict],
    *,
    thinking: bool = False,
    max_tokens: int | None = None,
    schema: dict | None = None,
) -> LLMResult:
    """One model call (with one retry on rate limits / server errors), recorded in the trace."""
    tier = TIERS[role]
    if thinking and not tier.thinking_allowed:
        raise ThinkingNotAllowed(f"thinking is not allowed on the {role!r} tier ({tier.model})")
    kwargs: dict = {
        "model": tier.model,
        "messages": messages,
        "max_tokens": max_tokens or tier.max_tokens,
        "temperature": 0.2,
        "timeout": tier.timeout_s,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": thinking}},
    }
    if schema is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": stage, "strict": True, "schema": schema},
        }
    client = _client()
    start = time.perf_counter()
    for attempt in (1, 2):
        try:
            resp = client.chat.completions.create(**kwargs)
            break
        except Exception as exc:  # shown in the trace, not hidden
            if attempt == 1 and _retryable(exc):
                continue
            record(user_id, stage, tier.model, status="error", tier=role,
                   ms=(time.perf_counter() - start) * 1000, note=str(exc)[:300])
            raise
    ms = (time.perf_counter() - start) * 1000
    usage = resp.usage
    tin = getattr(usage, "prompt_tokens", 0) or 0
    tout = getattr(usage, "completion_tokens", 0) or 0
    details = getattr(usage, "completion_tokens_details", None)
    treason = (getattr(details, "reasoning_tokens", 0) or 0) if details else 0
    pin, pout = PRICES.get(tier.model, (0.0, 0.0))
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    record(user_id, stage, tier.model, tier=role, ms=ms, input_tokens=tin, output_tokens=tout,
           reasoning_tokens=treason, cost_usd=cost)
    # Only `content` is the answer. `reasoning_content` (thinking) is never returned to callers.
    return LLMResult(resp.choices[0].message.content or "", tier.model, tin, tout, cost, ms, treason)


def chat_json(
    user_id: str,
    stage: str,
    role: str,
    messages: list[dict],
    schema: dict,
    *,
    thinking: bool = False,
    max_tokens: int | None = None,
) -> tuple[dict | None, LLMResult | None]:
    """Strict-JSON call that walks the tier's fallback chain. Returns (None, None) if every tier fails."""
    current: str | None = role
    while current is not None:
        tier = TIERS[current]
        try:
            res = chat(user_id, stage, current, messages, thinking=thinking, max_tokens=max_tokens, schema=schema)
            data = parse_json(res.text)
            if isinstance(data, dict):
                return data, res
            reason = "reply was not a JSON object"
        except ThinkingNotAllowed:
            raise
        except Exception as exc:
            reason = str(exc)[:200]
        if tier.fallback is None:
            return None, None
        record(user_id, stage, tier.model, status="fallback", tier=current,
               note=f"{current} -> {tier.fallback}: {reason}")
        current, thinking = tier.fallback, False
    return None, None


def parse_json(text: str) -> dict | list | None:
    """Pull the first JSON object or array out of a model reply."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


CHECK_EMAIL = "From: no-reply@spotify.com\nSubject: Your price is changing\n\nPremium goes from $11.99 to $12.99 next month."
CHECK_SCHEMA = {
    "type": "object",
    "properties": {"kind": {"type": "string"}, "merchant": {"type": "string"}},
    "required": ["kind", "merchant"],
    "additionalProperties": False,
}


def check(user_id: str = "check") -> list[dict]:
    """One tiny strict-JSON call per tier, thinking off. Each tier is called directly (no fallback),
    so a broken tier shows up as broken instead of being covered by its backup."""
    rows = []
    messages = [
        {"role": "system", "content": "Report the subscription in this email as JSON with kind and merchant."},
        {"role": "user", "content": CHECK_EMAIL},
    ]
    for role, tier in TIERS.items():
        try:
            res = chat(user_id, "check", role, messages, schema=CHECK_SCHEMA, max_tokens=100)
            data = parse_json(res.text)
            ok = isinstance(data, dict) and bool(data.get("merchant"))
            rows.append({"tier": role, "model": tier.model, "ok": ok, "ms": round(res.ms),
                         "cost_usd": res.cost_usd, "note": res.text[:80].replace("\n", " ")})
        except Exception as exc:
            rows.append({"tier": role, "model": tier.model, "ok": False, "ms": 0, "cost_usd": 0.0,
                         "note": str(exc)[:80]})
    return rows


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="ClawBack model tiers")
    parser.add_argument("--check", action="store_true", help="make one live call per tier")
    args = parser.parse_args()
    if not args.check:
        parser.print_help()
        sys.exit(0)
    if not available():
        print("NEBIUS_API_KEY is not set (backend/.env).")
        sys.exit(1)
    results = check()
    for r in results:
        mark = "ok  " if r["ok"] else "FAIL"
        print(f"{mark} {r['tier']:<14} {r['model']:<40} {r['ms']:>6} ms  ${r['cost_usd']:.6f}  {r['note']}")
    print(f"total ${sum(r['cost_usd'] for r in results):.6f}")
    sys.exit(0 if all(r["ok"] for r in results) else 1)
