"""Nebius Token Factory client (OpenAI-compatible).

Model IDs and prices come from the public Token Factory catalog, checked 2026-10-22:
https://tokenfactory.nebius.com/api/public/models_info

MISSING [json-schema-check]: not yet confirmed whether Token Factory honours `response_format` (JSON schema)
and `chat_template_kwargs` (thinking on/off) for the Nemotron models. The code asks for JSON in the prompt as
well, and parses defensively. Run one real call per model before relying on it.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from .config import settings
from .missing import missing
from .trace import record

# Role -> model. Each model gets the job it fits.
MODELS = {
    "fast": "nvidia/Nemotron-3_5-Lightning",  # extraction, triage fallback: cheap and fast
    "fast_fallback": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    "mid": "nvidia/nemotron-3-super-120b-a12b",  # policy / plan pages (262k context)
    "reason": "nvidia/Nemotron-3-Ultra-550b-a55b",  # usage-vs-plan reasoning, cancellation wording
    "vision": "nvidia/Nemotron-3.5-Super-VL",  # receipts as images / PDF pages (MISSING [pdf-receipts])
}

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


def available() -> bool:
    return bool(settings.nebius_api_key)


def _client():
    if not settings.nebius_api_key:
        missing("llm-extraction", "set NEBIUS_API_KEY in backend/.env")
    from openai import OpenAI

    return OpenAI(base_url=settings.nebius_base_url, api_key=settings.nebius_api_key)


def chat(
    user_id: str,
    stage: str,
    role: str,
    messages: list[dict],
    *,
    thinking: bool = False,
    max_tokens: int = 1024,
) -> LLMResult:
    """One chat call, recorded in the trace with tokens and cost."""
    model = MODELS[role]
    client = _client()
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
            # UNVERIFIED on Token Factory, see the module docstring.
            extra_body={"chat_template_kwargs": {"enable_thinking": thinking}},
        )
    except Exception as exc:  # network / auth / model errors are shown in the trace, not hidden
        record(user_id, stage, model, status="error", ms=(time.perf_counter() - start) * 1000, note=str(exc)[:300])
        raise
    ms = (time.perf_counter() - start) * 1000
    usage = resp.usage
    tin = getattr(usage, "prompt_tokens", 0) or 0
    tout = getattr(usage, "completion_tokens", 0) or 0
    pin, pout = PRICES.get(model, (0.0, 0.0))
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    record(user_id, stage, model, ms=ms, input_tokens=tin, output_tokens=tout, cost_usd=cost)
    return LLMResult(resp.choices[0].message.content or "", model, tin, tout, cost, ms)


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
