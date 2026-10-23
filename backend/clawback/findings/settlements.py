"""Class-action settlements the user may qualify for.

Data in: bank transaction descriptions, and email senders and subjects.
Rule: rules/settlements.json, a curated list of open settlements (who qualifies, class period, claim deadline,
payout, the official claim site). MISSING [settlements-refresh]: no live feed, so the list goes stale.
Detector: settlements_matching() over each charge and email. A finding needs at least one matching charge or email.
Confidence is medium when a matching charge or receipt falls inside the class period and the class isn't limited to
one state or venue; otherwise low ("might apply"). Amount = payout_estimate_usd (or 0), with the payout text as the note. Deadline = the claim deadline.
Action: steps plus the official claim_url only. ClawBack never files a claim; claims are made under penalty of
perjury, so only the user can say they qualify.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable

from ..models import Email, Finding, RuleRef, Transaction
from .util import day, finding_id, stale_note

RECEIPT_WORDS = ("receipt", "order", "purchase", "invoice", "payment", "subscription", "renewal")
# How the rules data marks a class limited to one state or venue ("STATE-LIMITED", "NEVADA EVENTS ONLY", ...).
_LIMITED = re.compile(r"STATE-LIMITED|\b[A-Z]{3,}(?: [A-Z]{3,})* ONLY\b|single venue", re.M)
_CLAIM_CODE = re.compile(r"\b(Claim ID|Claim Number|PIN|Access Code|LoginID)\b|received a notice")


def limited(s: dict) -> bool:
    """True when only people in one state, or at one venue, qualify."""
    return bool(_LIMITED.search(f"{s.get('who_qualifies') or ''}\n{s.get('notes') or ''}"))


def needs_notice_code(s: dict) -> bool:
    """True when the online claim needs a Claim ID / PIN from a mailed or emailed notice."""
    return bool(_CLAIM_CODE.search(s.get("notes") or ""))


def settlement_findings(transactions: list[Transaction], emails: list[Email],
                        settlements_matching: Callable[[str, date], list[dict]], today: date) -> list[Finding]:
    hits: dict[str, dict] = {}
    for t in transactions:
        if t.amount <= 0:
            continue
        for s in settlements_matching(t.description, today):
            h = hits.setdefault(s["id"], {"rule": s, "charges": [], "emails": []})
            h["charges"].append(t)
    for e in emails:
        for s in settlements_matching(f"{e.sender} {e.subject}", today):
            h = hits.setdefault(s["id"], {"rule": s, "charges": [], "emails": []})
            h["emails"].append(e)

    out: list[Finding] = []
    for h in hits.values():
        s = h["rule"]
        if s["claim_deadline"] is not None and s["claim_deadline"] < today:
            continue
        dated = [t.date for t in h["charges"]] + [
            e.received_at.date() for e in h["emails"] if any(w in e.subject.lower() for w in RECEIPT_WORDS)]
        start, end = s["class_start"], s["class_end"]
        inside = [d for d in dated if (start is None or d >= start) and (end is None or d <= end)]
        evidence = [f"{day(t.date)}: charge {t.description.strip()} (${t.amount:,.2f})." for t in h["charges"][:3]]
        evidence += [f"{day(e.received_at.date())}: email from {e.sender}: {e.subject}" for e in h["emails"][:3]]
        if start or end:
            evidence.append(f"Class period: {day(start) if start else 'start not stated'} to "
                            f"{day(end) if end else 'not stated'}; "
                            + (f"{len(inside)} of your dated purchases {'falls' if len(inside) == 1 else 'fall'} inside it."
                               if inside
                               else "none of your dated purchases fall inside it, so it might not apply."))
        if s.get("proof_required") not in (None, False, ""):
            proof = s["proof_required"]
            evidence.append("Proof of purchase is required." if proof is True else f"Proof: {proof}")
        words = s.get("evidence_words") or []
        seen = " ".join([t.description for t in h["charges"]]
                        + [f"{e.subject} {e.body_text}" for e in h["emails"]]).upper()
        specific = not words or any(re.search(r"\b" + re.escape(w) + r"\b", seen) for w in words)
        if not specific:
            evidence.append(f"This settlement only covers part of what {(s['defendant'] or s['name']).rstrip('.')} sells, "
                            "and nothing in your data shows that part yet, so it might not apply.")
        if limited(s):
            evidence.append("Limited to one state or venue (see who qualifies), so it may not apply to you.")
        evidence += stale_note(s.get("checked_on"), today)
        found = len(h["charges"]) + len(h["emails"])
        who = (s["defendant"] or s["name"]).rstrip(".")
        out.append(Finding(
            id=finding_id("settlement", s["id"]),
            category="settlements", kind="settlement", merchant=s["defendant"] or s["name"],
            title=f"You may qualify for the {s['name']}",
            message=(f"{found} of your charges or emails involve {who}. "
                     f"{s['who_qualifies']}".strip()),
            amount=float(s["payout_estimate_usd"] or 0.0), amount_note=s["payout"] or None,
            deadline=s["claim_deadline"], deadline_label="Claim deadline" if s["claim_deadline"] else None,
            confidence="medium" if inside and specific and not limited(s) else "low", evidence=evidence,
            rule=RuleRef(name=s["name"], summary=s["who_qualifies"], source_url=s["source_url"]) if s.get("source_url") else None,
            found_on=today,
            details={"claim_url": s.get("claim_url"), "proof_required": s.get("proof_required"),
                     "needs_notice_code": needs_notice_code(s),
                     "class_start": start.isoformat() if start else None, "class_end": end.isoformat() if end else None},
        ))
    return out
