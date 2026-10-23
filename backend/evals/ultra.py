"""Counterfactual: skip triage and send every email to Ultra, the largest tier, instead of rules + Lightning.

Only a small, fixed sample of emails is sent (every k-th email by id across the three people). The cost per
email from the sample is multiplied up to 1,000 emails, which is an extrapolation and is labelled as one.
The prompt and the JSON schema are the product's own extraction prompt (pipeline/extract.py); only the tier changes.
"""

from __future__ import annotations

import time

from clawback import llm
from clawback.store import store

from . import adapter, costs
from .score import collapse, names_match


def sample(people: list[dict], n: int) -> list[tuple[dict, dict]]:
    emails = sorted(((p, e) for p in people for e in p["emails"]), key=lambda pe: pe[1]["id"])
    step = max(1, len(emails) // n)
    return emails[::step][:n]


def run(people: list[dict], n: int, thinking: bool, user_id: str = "eval-all-ultra") -> dict:
    from clawback.pipeline.extract import FACT_SCHEMA, KINDS, SYSTEM_PROMPT

    store.reset(user_id)
    rows = []
    for person, raw in sample(people, n):
        email = adapter.to_email(raw)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"<email>\nFrom: {email.sender}\nSubject: {email.subject}\n\n"
                                        f"{email.body_text[:6000]}\n</email>"},
        ]
        before = len(store.user(user_id).trace)
        start = time.perf_counter()
        try:
            data, _ = llm.chat_json(user_id, "all-ultra extract", "reason", messages, FACT_SCHEMA, thinking=thinking)
        except Exception as exc:  # recorded in the trace by llm.chat
            data = None
            error = type(exc).__name__
        else:
            error = None if data is not None else "no JSON object"
        ms = (time.perf_counter() - start) * 1000
        new = store.user(user_id).trace[before:]
        kind = data.get("kind") if isinstance(data, dict) and data.get("kind") in KINDS else None
        lab = raw["label"]
        rows.append({
            "email": raw["id"], "label": lab["kind"], "predicted": kind or "error",
            "kind_ok": kind is not None and collapse(kind) == collapse(lab["kind"]),
            "merchant": data.get("merchant") if isinstance(data, dict) else None,
            "merchant_ok": (names_match(lab["names"], data.get("merchant")) if isinstance(data, dict)
                            and lab["merchant"] and collapse(lab["kind"]) != "none" else None),
            "ms": round(ms, 1), "error": error,
            "cost_usd": round(sum(r.cost_usd for r in new), 6),
            "input_tokens": sum(r.input_tokens for r in new), "output_tokens": sum(r.output_tokens for r in new),
            "reasoning_tokens": sum(r.reasoning_tokens for r in new),
        })
    trace = [s.model_dump(mode="json") for s in store.user(user_id).trace]
    summary = costs.summarize(trace, len(rows))
    ok = [r for r in rows if r["error"] is None]
    return {
        "sample_size": len(rows), "thinking": thinking, "model": llm.TIERS["reason"].model,
        "emails_total": sum(len(p["emails"]) for p in people),
        "cost_usd": summary["cost_usd"],
        "cost_per_email_usd": round(summary["cost_usd"] / len(rows), 6) if rows else None,
        "extrapolated_cost_per_1000_emails_usd": summary["cost_per_1000_emails_usd"],
        "errors": sum(1 for r in rows if r["error"]),
        "accuracy": round(sum(1 for r in rows if r["kind_ok"]) / len(rows), 4) if rows else None,
        "ms_p50": costs._pct([r["ms"] for r in ok], 0.5), "ms_p90": costs._pct([r["ms"] for r in ok], 0.9),
        "input_tokens": summary["input_tokens"], "output_tokens": summary["output_tokens"],
        "reasoning_tokens": summary["reasoning_tokens"],
        "rows": rows,
    }
