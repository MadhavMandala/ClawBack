"""Bank charge problems: duplicate charges and bank fees.

Duplicate charges
  Data in: bank transactions, plus purchases read from receipt emails (purchases.py).
  Rule: rules/disputes.json, the Fair Credit Billing Act (credit cards) and Regulation E (debit cards): a written
  dispute within 60 days after the statement that first shows the charge.
  Detector: the same merchant (first two words of the description) and the same amount, charged again within
  3 days, $5 or more, and not part of a recurring series or a bank fee. High confidence when one email receipt
  shows a single order for that amount around that date; medium when there is no receipt. If the emails show as
  many orders as charges, it isn't flagged.
  Deadline: the rule's 60 days after the statement that first shows the charge. For a credit card whose last
  statement date came from Plaid (/liabilities/get), that statement is worked out from the card's statement day:
  the last statement itself, an earlier one (same day of the month), or the next one when the charge came after
  it. Otherwise (no Plaid date, a debit card, CSV or demo data) the statement is assumed to close at the end of
  the charge's month and the deadline says "estimated". A debit card account uses the Regulation E rule.
Bank fees
  Data in: bank transactions. Rule: rules/bank_fees.json (fee kinds, description patterns, a neutral reversal tip).
  Detector: descriptions matched with fee_kind_for(). No deadline; the action asks for a one-time courtesy reversal.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta
from typing import Callable

from ..models import BankAccount, Finding, RuleRef, Transaction
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


def add_months(d: date, n: int) -> date:
    """The same day of the month n months away, clamped to the month's last day (Jan 31 + 1 -> Feb 28)."""
    years, month0 = divmod(d.month - 1 + n, 12)
    year, month = d.year + years, month0 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def first_statement(charged_on: date, last_issued: date) -> tuple[date, str]:
    """The statement that first shows a charge, from the card's last statement date (monthly cycle):
    ("exact", the last statement itself), ("cycle", an earlier one on the same day of the month), or ("next", the
    coming one when the charge came after the last statement). The earliest possible statement is chosen, so the
    deadline is never later than the real one."""
    if charged_on > last_issued:
        return add_months(last_issued, 1), "next"
    back = 0
    while back < 24 and add_months(last_issued, -(back + 1)) >= charged_on:
        back += 1
    return add_months(last_issued, -back), "exact" if back == 0 else "cycle"


def statement_deadline(t: Transaction, accounts: dict[str, BankAccount], credit: dict | None,
                       debit: dict | None) -> tuple[date | None, dict | None, dict]:
    """(deadline, the rule used, how it was worked out) for a charge, using the card's real statement date when
    Plaid gave one, else the end-of-month estimate."""
    acct = accounts.get(t.account_id or "")
    if acct and acct.kind == "credit" and acct.last_statement_issue_date and credit:
        stmt, how = first_statement(t.date, acct.last_statement_issue_date)
        days = credit.get("days")
        deadline = stmt + timedelta(days=days) if isinstance(days, int) else None
        return deadline, credit, {"source": f"plaid_{how}", "statement": stmt, "last": acct.last_statement_issue_date,
                                  "card": "credit", "mask": acct.mask}
    rule = (debit or credit) if acct and acct.kind == "depository" else (credit or debit)
    return dispute_deadline(t.date, rule), rule, {"source": "estimate", "statement": end_of_month(t.date),
                                                  "card": "debit" if acct and acct.kind == "depository" else None}


def _statement_note(how: dict, deadline: date, days: int) -> str:
    stmt = how["statement"]
    card = f"card ending {how['mask']}" if how.get("mask") else "card"
    if how["source"] == "plaid_exact":
        return (f"Your {card}'s statement of {day(stmt)} first shows this charge (statement date from your bank, "
                f"through Plaid), so the {days}-day dispute window ends {day(deadline)}.")
    if how["source"] == "plaid_cycle":
        return (f"Your {card}'s statements are issued around day {stmt.day} of the month (from your bank, through "
                f"Plaid), so the statement of {day(stmt)} first showed this charge and the {days}-day dispute window "
                f"ends {day(deadline)}.")
    if how["source"] == "plaid_next":
        return (f"This charge came after your {card}'s last statement ({day(how['last'])}), so it will first show on "
                f"the next one, around {day(stmt)}. The {days}-day dispute window ends about {day(deadline)}.")
    return (f"Statement date unknown: assumed it closed {day(stmt)}, so the {days}-day dispute window is an "
            "estimate.")


def _matching_orders(purchases: list[Purchase], words: list[str], amount: float, around: date) -> list[Purchase]:
    name = " ".join(words)
    return [p for p in purchases
            if name and (name in p.store.lower() or " ".join(merchant_words(p.store)) in name)
            and p.total is not None and abs(p.total - amount) < 0.005
            and abs((p.order_date - around).days) <= WINDOW_DAYS]


def duplicate_charges(transactions: list[Transaction], skip_ids: set[str], purchases: list[Purchase],
                      disputes: dict[str, dict], today: date,
                      accounts: dict[str, BankAccount] | None = None) -> list[Finding]:
    """`skip_ids`: transactions that belong to a recurring series or are bank fees. `accounts`: the user's Plaid
    accounts by id, with credit cards' last statement dates (UserData.bank_accounts)."""
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
                f = _duplicate(cluster, name.split(), amount, purchases, credit, debit, today, accounts or {})
                if f:
                    out.append(f)
            cluster = [t] if t is not None else []
    return out


def _duplicate(cluster, words, amount, purchases, credit, debit, today, accounts) -> Finding | None:
    first = cluster[0]
    orders = _matching_orders(purchases, words, amount, first.date)
    if len(orders) >= len(cluster):
        return None  # the emails show as many orders as charges: probably real
    extra = len(cluster) - 1
    deadline, rule, how = statement_deadline(first, accounts, credit, debit)
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
        evidence.append(_statement_note(how, deadline, rule["days"]))
    if how["card"] == "debit":
        evidence.append("This is a debit card account, so the debit card error rule (Regulation E) applies.")
    label = {"plaid_exact": "Dispute window closes", "estimate": "Dispute window closes (estimated)"}.get(
        how["source"], "Dispute window closes (from your statement day)")
    return Finding(
        id=finding_id("duplicate_charge", " ".join(words), f"{amount:.2f}", first.date.isoformat(), len(cluster)),
        category="charges", kind="duplicate_charge", merchant=store,
        title=f"{store} charged you twice",
        message=(f"{store} charged {money(amount)} {times(len(cluster))} around {day(first.date)}. If you ordered once, "
                 f"you can get {money(amount * extra)} back."),
        amount=round(amount * extra, 2),
        deadline=deadline, deadline_label=label if deadline else None,
        confidence="high" if orders else "medium", evidence=evidence, rule=_rule(rule), found_on=today,
        details={"amount_each": amount, "charges": [t.date.isoformat() for t in cluster], "description": first.description,
                 "order_number": orders[0].order_number if orders else None,
                 "debit_rule": debit, "credit_rule": credit,
                 "statement_source": how["source"], "statement_date": how["statement"].isoformat(),
                 "card": how["card"]},
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
