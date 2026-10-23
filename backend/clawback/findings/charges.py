"""Bank charge problems: duplicate charges and bank fees.

Duplicate charges
  Data in: bank transactions, plus purchases read from receipt emails (purchases.py).
  Rule: rules/disputes.json, the Fair Credit Billing Act (credit cards) and Regulation E (debit cards): a written
  dispute within 60 days after the statement that first shows the charge.
  Detector: the same merchant (first two words of the description) and the same amount, charged again within
  3 days, $5 or more, and not part of a recurring series or a bank fee. High confidence when one email receipt
  shows a single order for that amount around that date; medium when there is no receipt. If the emails show as
  many orders as charges, it isn't flagged.
  Deadline: the statement date isn't known, so the statement is assumed to close at the end of the charge's month,
  plus the rule's 60 days. MISSING [statement-dates]: Plaid Statements would give the real date.
Bank fees
  Data in: bank transactions. Rule: rules/bank_fees.json (fee kinds, description patterns, a neutral reversal tip).
  Detector: descriptions matched with fee_kind_for(). No deadline; the action asks for a one-time courtesy reversal.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Callable

from ..models import Finding, RuleRef, Transaction
from .purchases import Purchase
from .util import day, end_of_month, fee_name, finding_id, merchant_name, merchant_words, money, times

WINDOW_DAYS = 3
MIN_AMOUNT = 5.0


def _rule(entry: dict | None) -> RuleRef | None:
    if not entry or not entry.get("source_url"):
        return None
    return RuleRef(name=entry["name"], summary=entry["summary"], source_url=entry["source_url"])


def dispute_deadline(charged_on: date, rule: dict | None) -> date | None:
    """Estimated: the statement is assumed to close at the end of the charge's month."""
    days = (rule or {}).get("days")
    return end_of_month(charged_on) + timedelta(days=days) if isinstance(days, int) else None


def _matching_orders(purchases: list[Purchase], words: list[str], amount: float, around: date) -> list[Purchase]:
    name = " ".join(words)
    return [p for p in purchases
            if name and (name in p.store.lower() or " ".join(merchant_words(p.store)) in name)
            and p.total is not None and abs(p.total - amount) < 0.005
            and abs((p.order_date - around).days) <= WINDOW_DAYS]


def duplicate_charges(transactions: list[Transaction], skip_ids: set[str], purchases: list[Purchase],
                      disputes: dict[str, dict], today: date) -> list[Finding]:
    """`skip_ids`: transactions that belong to a recurring series or are bank fees."""
    groups: dict[tuple[str, float], list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.amount >= MIN_AMOUNT and t.id not in skip_ids:
            words = merchant_words(t.description)
            if words:
                groups[(" ".join(words), round(t.amount, 2))].append(t)

    credit, debit = disputes.get("credit"), disputes.get("debit")
    out: list[Finding] = []
    for (name, amount), txs in groups.items():
        txs.sort(key=lambda t: (t.date, t.id))
        cluster: list[Transaction] = []
        for t in txs + [None]:  # None flushes the last cluster
            if t is not None and cluster and (t.date - cluster[0].date).days <= WINDOW_DAYS:
                cluster.append(t)
                continue
            if len(cluster) >= 2:
                f = _duplicate(cluster, name.split(), amount, purchases, credit, debit, today)
                if f:
                    out.append(f)
            cluster = [t] if t is not None else []
    return out


def _duplicate(cluster, words, amount, purchases, credit, debit, today) -> Finding | None:
    first = cluster[0]
    orders = _matching_orders(purchases, words, amount, first.date)
    if len(orders) >= len(cluster):
        return None  # the emails show as many orders as charges: probably real
    extra = len(cluster) - 1
    rule = credit or debit
    deadline = dispute_deadline(first.date, rule)
    if deadline is not None and deadline < today:
        return None  # the dispute window has closed
    store = orders[0].store if orders else merchant_name(first.description)
    when = ", ".join(day(t.date) for t in cluster)
    evidence = [f"{money(amount)} charged {times(len(cluster))} by {first.description.strip()}: {when}."]
    if orders:
        o = orders[0]
        number = f" (order {o.order_number})" if o.order_number else ""
        evidence.append(f"Your email has one {store} order for {money(amount)} on {day(o.order_date)}{number}.")
    else:
        evidence.append("No email receipt found for this order, so check that you didn't buy it twice.")
    if deadline:
        evidence.append(f"Statement date unknown: assumed it closed {day(end_of_month(first.date))}, so the "
                        f"{rule['days']}-day dispute window is an estimate.")
    return Finding(
        id=finding_id("duplicate_charge", " ".join(words), f"{amount:.2f}", first.date.isoformat(), len(cluster)),
        category="charges", kind="duplicate_charge", merchant=store,
        title=f"{store} charged you twice",
        message=(f"{store} charged {money(amount)} {times(len(cluster))} around {day(first.date)}. If you ordered once, "
                 f"you can get {money(amount * extra)} back."),
        amount=round(amount * extra, 2),
        deadline=deadline, deadline_label="Dispute window closes (estimated)" if deadline else None,
        confidence="high" if orders else "medium", evidence=evidence, rule=_rule(rule), found_on=today,
        details={"amount_each": amount, "charges": [t.date.isoformat() for t in cluster], "description": first.description,
                 "order_number": orders[0].order_number if orders else None,
                 "debit_rule": debit, "credit_rule": credit},
    )


def bank_fees(transactions: list[Transaction], fee_kind_for: Callable[[str], dict | None], bank: str,
              today: date) -> tuple[list[Finding], set[str]]:
    """Findings, plus the ids of the fee transactions (so they aren't counted as duplicates)."""
    out: list[Finding] = []
    ids: set[str] = set()
    for t in transactions:
        if t.amount <= 0:
            continue
        fee = fee_kind_for(t.description)
        if not fee:
            continue
        ids.add(t.id)
        label = fee["label"]
        out.append(Finding(
            id=finding_id("bank_fee", t.id, t.date.isoformat(), f"{t.amount:.2f}"),
            category="charges", kind="bank_fee", merchant=bank,
            title=f"{fee_name(label)}: {money(t.amount)}",
            message=(f"{bank} charged you {money(t.amount)} on {day(t.date)}: {label}. Banks sometimes reverse a fee "
                     "as a one-time courtesy when you ask."),
            amount=round(t.amount, 2), confidence="high",
            evidence=[f"{day(t.date)}: {t.description.strip()} ({money(t.amount)})."],
            rule=(RuleRef(name=label, summary=fee.get("rule") or fee["reversal_tip"], source_url=fee["source_url"])
                  if fee.get("source_url") else None),
            found_on=today,
            details={"fee_kind": fee["kind"], "reversal_tip": fee["reversal_tip"], "date": t.date.isoformat(),
                     "description": t.description},
        ))
    return out, ids
