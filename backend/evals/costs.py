"""Cost and latency from the pipeline trace (clawback/trace.py rows), per stage and per model."""

from __future__ import annotations

import statistics
from collections import defaultdict


def _model_ids() -> set[str]:
    from clawback import llm

    return set(llm.PRICES) | set(llm.MODELS.values())


def model_rows(trace: list[dict]) -> list[dict]:
    """Rows written by llm.chat: the engine is a model id."""
    ids = _model_ids()
    return [r for r in trace if r["engine"] in ids]


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(q * (len(values) - 1))))
    return round(values[k], 1)


def summarize(trace: list[dict], n_emails: int) -> dict:
    rows = model_rows(trace)
    calls = [r for r in rows if r["status"] == "ok"]
    by_stage: dict[tuple[str, str], dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "fallbacks": 0,
                                                                  "input_tokens": 0, "output_tokens": 0,
                                                                  "reasoning_tokens": 0, "cost_usd": 0.0,
                                                                  "ms": []})
    for r in rows:
        s = by_stage[(r["stage"], r["engine"])]
        if r["status"] == "ok":
            s["calls"] += 1
            s["ms"].append(r["ms"])
        elif r["status"] == "error":
            s["errors"] += 1
        elif r["status"] == "fallback":
            s["fallbacks"] += 1
        s["input_tokens"] += r["input_tokens"]
        s["output_tokens"] += r["output_tokens"]
        s["reasoning_tokens"] += r["reasoning_tokens"]
        s["cost_usd"] += r["cost_usd"]
    stages = []
    for (stage, engine), s in sorted(by_stage.items()):
        ms = s.pop("ms")
        stages.append({"stage": stage, "model": engine, **s, "cost_usd": round(s["cost_usd"], 6),
                       "ms_p50": _pct(ms, 0.5), "ms_p90": _pct(ms, 0.9)})
    cost = sum(r["cost_usd"] for r in rows)
    ms = [r["ms"] for r in calls]
    pipeline_rows = [r for r in trace if r["engine"] not in _model_ids()]
    return {
        "model_calls": len(calls),
        "errors": sum(1 for r in rows if r["status"] == "error"),
        "fallbacks": sum(1 for r in rows if r["status"] == "fallback"),
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
        "reasoning_tokens": sum(r["reasoning_tokens"] for r in rows),
        "cost_usd": round(cost, 6),
        "cost_per_1000_emails_usd": round(cost / n_emails * 1000, 4) if n_emails else None,
        "call_ms_p50": _pct(ms, 0.5), "call_ms_p90": _pct(ms, 0.9), "call_ms_max": round(max(ms), 1) if ms else None,
        "by_stage": stages,
        "pipeline_steps": [{"stage": r["stage"], "engine": r["engine"], "status": r["status"],
                            "ms": round(r["ms"], 1), "note": r["note"][:160]} for r in pipeline_rows],
    }


def mean_ms(values: list[float]) -> float | None:
    return round(statistics.mean(values), 1) if values else None
