"""Run every findings detector for one user, record a trace row for each, and keep the user's dismiss / done choices."""

from __future__ import annotations

import time
from datetime import date

from .. import connections, llm
from ..models import Finding, Subscription, Transaction
from ..store import UserData
from ..tools import prices
from ..trace import record
from .charges import bank_fees, duplicate_charges
from .purchases import Item, Purchase, extract_purchases
from .refunds import PriceCheck, flight_emails, flight_findings, price_drops
from .rulebook import Rulebook
from .settlements import settlement_findings


def _step(user_id: str, stage: str, fn, note_fn, engine: str = "code", status: str = "ok"):
    start = time.perf_counter()
    result = fn()
    record(user_id, stage, engine, status=status, ms=(time.perf_counter() - start) * 1000, note=note_fn(result)[:400])
    return result


def _bank_name(user_id: str, u: UserData) -> str:
    if u.mode == "real":
        plaid = connections.get(user_id).plaid
        if plaid and plaid.institution:
            return plaid.institution
    return "Your bank"


def run_findings(user_id: str, u: UserData, rules: Rulebook | None, subs: list[Subscription],
                 series: dict[str, list[Transaction]], today: date) -> list[Finding]:
    if rules is None:
        record(user_id, "findings", "code", status="missing",
               note="MISSING: no rule data in backend/clawback/rules, so no charges, refunds or settlements were checked")
        return []

    recurring_ids = {t.id for s in subs for t in series.get(s.id, [])}
    fees, fee_ids = _step(
        user_id, "bank fees", lambda: bank_fees(u.transactions, rules.fee_kind_for, _bank_name(user_id, u), today),
        lambda r: f"{len(r[0])} bank fees found ({', '.join(sorted({f.title.split(':')[0] for f in r[0]})) or 'none'})")

    purchases = _step(
        user_id, "extract purchases", lambda: extract_purchases(user_id, u.emails, rules.retailer_for),
        lambda r: f"{len(r)} purchases read from receipt emails"
                  + ("" if llm.available() else " (regex rules. MISSING [purchase-extraction]: NEBIUS_API_KEY for Nemotron)"),
        engine="code" if llm.available() else "rules", status="ok" if llm.available() else "missing")

    dups = _step(
        user_id, "duplicate charges",
        lambda: duplicate_charges(u.transactions, recurring_ids | fee_ids, purchases, rules.disputes, today),
        lambda r: f"{len(r)} duplicate charges"
                  + (f" ({', '.join(f.merchant for f in r)}; dispute deadlines estimated)" if r else ""))

    drops = _price_step(user_id, u, rules, purchases, today)

    flights = _step(
        user_id, "flights",
        lambda: flight_findings(flight_emails(user_id, u.emails, rules.airline_for), rules.flights, today),
        lambda r: f"{len(r)} flight refunds or compensation claims"
                  + (f" ({', '.join(f.merchant + ' ' + f.kind.replace('_', ' ') for f in r)})" if r else ""))

    settled = _step(
        user_id, "settlements",
        lambda: settlement_findings(u.transactions, u.emails, rules.settlements_matching, today),
        lambda r: f"{len(r)} open settlements match your charges or emails ({len(rules.settlements)} verified in the list)")

    found = fees + dups + drops + flights + settled
    for f in found:
        f.status = u.finding_status.get(f.id, "open")
    return found


def _price_step(user_id: str, u: UserData, rules: Rulebook, purchases: list[Purchase], today: date) -> list[Finding]:
    demo = u.mode == "demo"
    live = prices.live_available()

    def check(p: Purchase, item: Item, adjusts: bool) -> PriceCheck | None:
        if demo:
            price = prices.demo_price(p.store, item.name)
            return PriceCheck(price=price, how="simulated") if price is not None else None
        if not adjusts or not live:
            return None  # don't spend search credits on stores that won't adjust
        return prices.live_price(user_id, p.store, item.name, prices.store_domain(p.retailer))

    notes: list[str] = []
    start = time.perf_counter()
    drops = price_drops(purchases, check, today, notes)
    if demo:
        how = "simulated price check (demo data)"
        status = "ok"
    elif live:
        how = "live price check (Tavily + Nemotron)"
        status = "ok"
    else:
        how = "MISSING [live-price-check]: no TAVILY_API_KEY / NEBIUS_API_KEY, so prices weren't checked"
        status = "missing"
    record(user_id, "price drops", "code", status=status, ms=(time.perf_counter() - start) * 1000,
           note=(f"{len(drops)} price drops; {how}" + (f"; {'; '.join(notes)}" if notes else ""))[:400])
    return drops


def sort_key(f: Finding):
    return (f.status != "open", f.deadline is None, f.deadline or date.max, -f.amount)
