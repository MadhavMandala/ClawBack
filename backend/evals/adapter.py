"""The thin layer between the eval set and the product. It changes no product code.

Each synthetic person is loaded into a fresh user the way main.seed() loads the demo user (store.reset, then
transactions and emails, then pipeline.run), with three eval-only adjustments:

1. Emails go through the same body conversion the Nylas source uses (sources/nylas.to_email: HTML to text, the
   5,000-character cap), so the HTML-heavy email is tested the way a real inbox delivers it.
2. Current prices for the price-drop check come from the person's `simulated_prices` table instead of
   demo_data.PRICE_CHECKS. The user stays in demo mode, so the product calls tools.prices.demo_price; we swap that
   one function for the length of the run. TODO(clawback): a price-checker argument on run() would remove this.
3. The per-email facts are captured by wrapping pipeline.run.extract_all for the length of the run, because run()
   doesn't keep them (u.facts holds only model results). TODO(clawback): run() could return or store every
   email's Fact, including rule-based ones.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import date, datetime

from clawback.models import Email, Transaction
from clawback.store import store


def to_email(e: dict) -> Email:
    """A dataset email as the Nylas source would hand it to the pipeline."""
    received = datetime.fromisoformat(e["received_at"])
    try:
        from clawback.sources import nylas

        msg = {"id": e["id"], "from": [{"name": e.get("from_name") or "", "email": e["from"]}],
               "date": int(received.timestamp()), "subject": e["subject"], "body": e["body"], "snippet": ""}
        email = nylas.to_email(msg, "google")
        if email is not None:
            return email.model_copy(update={"source": "demo", "received_at": received})
    except Exception:  # the Nylas helper changed shape: fall back to the shared text helper
        pass
    from clawback.sources import text

    return Email(id=e["id"], received_at=received, sender=e["from"].lower(), subject=e["subject"],
                 body_text=text.to_text(e["body"])[:5000], source="demo")


def to_transaction(t: dict) -> Transaction:
    return Transaction(id=t["id"], date=date.fromisoformat(t["date"]), description=t["description"],
                       amount=t["amount"], source="demo")


@contextmanager
def simulated_prices(table: list[dict]):
    """tools.prices.demo_price answers from the dataset's table for the length of the block."""
    from clawback.tools import prices

    def lookup(store_name: str, item: str) -> float | None:
        for row in table:
            if row["store"].lower() == (store_name or "").lower() and row["item_contains"] in (item or "").lower():
                return row["price_now"]
        return None

    original = prices.demo_price
    prices.demo_price = lookup
    try:
        yield
    finally:
        prices.demo_price = original


@contextmanager
def capture_facts():
    """Record what triage passed on and what extraction concluded for each email during pipeline.run()."""
    from clawback.pipeline import run as run_mod

    captured: dict = {"candidates": [], "facts": {}, "hooked": False}
    original = getattr(run_mod, "extract_all", None)
    if original is None:
        yield captured
        return

    def wrapper(user_id, emails):
        facts = original(user_id, emails)
        captured["candidates"] = [e.id for e in emails]
        captured["facts"] = {f.email_id: f for f in facts}
        return facts

    run_mod.extract_all = wrapper
    captured["hooked"] = True
    try:
        yield captured
    finally:
        run_mod.extract_all = original


def _facts_by_rerun(user_id: str, emails: list[Email]) -> dict:
    """Fallback when run() no longer calls extract_all by that name: triage + extract again (cached when live)."""
    from clawback.pipeline.extract import extract_all
    from clawback.pipeline.triage import triage

    cands = triage(user_id, emails)
    facts = extract_all(user_id, cands)
    return {"candidates": [e.id for e in cands], "facts": {f.email_id: f for f in facts}, "hooked": False}


def clear_module_caches() -> None:
    """Per-email model results the product keeps at module level (keyed by email id, not user)."""
    from clawback.findings import purchases, refunds
    from clawback.tools import prices

    for mod, name in ((purchases, "_read"), (refunds, "_read"), (prices, "_checked")):
        cache = getattr(mod, name, None)
        if isinstance(cache, dict):
            cache.clear()


def run_person(person: dict, user_id: str) -> dict:
    """Load one person into a fresh user, run the pipeline once, and return what it produced."""
    from clawback.pipeline.run import run

    today = date.fromisoformat(person["today"])
    u = store.reset(user_id)
    u.transactions = [to_transaction(t) for t in person["transactions"]]
    u.emails = [to_email(e) for e in person["emails"]]
    with simulated_prices(person.get("simulated_prices") or []), capture_facts() as cap:
        start = time.perf_counter()
        run(user_id, today)
        wall = time.perf_counter() - start
    trace = [s.model_dump(mode="json") for s in store.user(user_id).trace]
    if not cap["hooked"]:
        cap = _facts_by_rerun(user_id, u.emails)
    u = store.user(user_id)
    return {
        "user_id": user_id,
        "wall_s": round(wall, 3),
        "subscriptions": [_sub(s) for s in u.subscriptions.values()],
        "findings": [_finding(f) for f in u.findings.values()],
        "candidates": cap["candidates"],
        "facts": {k: _fact(f) for k, f in cap["facts"].items()},
        "facts_hooked": cap["hooked"],
        "trace": trace,
    }


def rerun_without(person: dict, user_id: str, drop: set[str]) -> list[dict]:
    """Run the same user again without some emails (model results are cached per user, so this is free when live).
    Returns the subscriptions. Used to check that the prompt-injection email changed nothing."""
    from clawback.pipeline.run import run

    u = store.user(user_id)
    keep = list(u.emails)
    u.emails = [e for e in keep if e.id not in drop]
    try:
        with simulated_prices(person.get("simulated_prices") or []):
            run(user_id, date.fromisoformat(person["today"]))
        return [_sub(s) for s in store.user(user_id).subscriptions.values()]
    finally:
        u.emails = keep


def _sub(s) -> dict:
    return {
        "id": s.id, "merchant": s.merchant, "kind": s.kind, "category": s.category,
        "cadence": s.cadence.value if s.cadence else None, "amount": s.amount, "monthly_cost": s.monthly_cost,
        "status": s.status, "detected_from": list(s.detected_from), "usage": s.usage.level,
        "flags": [{"kind": f.kind, "severity": f.severity, "message": f.message} for f in s.flags],
    }


def _finding(f) -> dict:
    return {"id": f.id, "kind": f.kind, "category": f.category, "merchant": f.merchant, "title": f.title,
            "amount": f.amount, "currency": f.currency, "confidence": f.confidence,
            "deadline": f.deadline.isoformat() if f.deadline else None}


def _fact(f) -> dict:
    return {"kind": f.kind, "merchant": f.merchant, "amount": f.amount, "saved_amount": f.saved_amount,
            "old_price": f.old_price, "new_price": f.new_price,
            "trial_end": f.trial_end.isoformat() if f.trial_end else None}
