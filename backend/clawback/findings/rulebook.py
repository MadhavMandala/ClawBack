"""Rule data for the detectors, from backend/clawback/rules (written and fact-checked separately; not edited here).

Detectors are pure functions over the plain dicts a Rulebook holds, so tests can build one from small inline data
with Rulebook.from_data(). current() builds the real one: through the rules package's loaders and match helpers
when they exist, else straight from the JSON files in that folder. It returns None when there is no rule data.

Only entries marked verified are kept, so only verified rules can raise a finding or a bill flag. The package's
lookups can return unverified rows; those map to None here. Matching itself (word boundaries, longest match, the
bank-fee exclude patterns) is the package's; the plain matchers below are only for inline test data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from .util import as_date, first_url, search_terms

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


def plain(obj: object) -> object:
    """Pydantic models (from the loaders) -> dicts and lists; everything else unchanged."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, (list, tuple)):
        return [plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    return obj


LIST_KEYS = ("items", "rules", "retailers", "providers", "fees", "settlements", "airlines")


def _items(raw: object) -> list[dict]:
    """The rows of a rules file, whichever key holds them (retailers, providers, fees, settlements, rules...)."""
    raw = plain(raw)
    if isinstance(raw, dict):
        raw = next((raw[k] for k in LIST_KEYS if isinstance(raw.get(k), list)), [])
    return [x for x in raw or [] if isinstance(x, dict)]


def _verified(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e.get("verified", True) is True]


# --- Normalizers: the rules files' shapes -> what the detectors read -----------------------------------

def norm_retailer(e: dict) -> dict:
    return {
        "store": e.get("store") or "",
        "match": list(e.get("match") or []),
        "adjusts": bool(e.get("adjusts")),
        "window_days": e.get("window_days"),
        "window_from": e.get("window_from"),
        "conditions": e.get("conditions") or "",
        "exclusions": list(e.get("exclusions") or []),
        "how_to_claim": e.get("how_to_claim") or "",
        "claim_url": e.get("claim_url"),
        "source_url": first_url(e),
        "tiers": list(e.get("tiers") or []),
        "no_automated_requests": bool(e.get("no_automated_requests")),
        "checked_on": as_date(e.get("checked_on")),
        "verified": e.get("verified") is True,
    }


def norm_bill(e: dict) -> dict:
    return {
        "provider": e.get("provider") or "",
        "match": list(e.get("match") or []),
        "category": e.get("category") or "",
        "negotiable": bool(e.get("negotiable")),
        "variable_amount": bool(e.get("variable_amount")),
        "account_url": e.get("account_url"),
        "cancel_or_retention": e.get("cancel_or_retention"),
        "budget_billing_url": e.get("budget_billing_url"),
        "assistance_url": e.get("assistance_url"),
        "generic": bool(e.get("generic")),
        "notes": e.get("notes") or "",
        "source_url": first_url(e),
        "verified": e.get("verified") is True,
    }


def norm_fee(e: dict) -> dict:
    return {
        "kind": e.get("kind") or "",
        "label": e.get("label") or e.get("kind") or "Bank fee",
        "patterns": list(e.get("patterns") or e.get("match") or []),
        "rule": e.get("rule") or "",
        "reversal_tip": e.get("reversal_tip") or "",
        "source_url": first_url(e),
        "verified": e.get("verified", True) is True,
    }


def norm_settlement(e: dict) -> dict:
    period = e.get("class_period") or {}
    est = e.get("payout_estimate_usd")
    return {
        "id": str(e.get("id") or e.get("name")),
        "name": e.get("name") or "",
        "defendant": e.get("defendant") or "",
        "match": list(e.get("match") or []),
        "who_qualifies": e.get("who_qualifies") or "",
        "evidence_words": [str(w).upper() for w in e.get("evidence_words") or []],
        "states": [str(c).upper() for c in e.get("states") or []],
        "class_start": as_date(period.get("start")) if isinstance(period, dict) else None,
        "class_end": as_date(period.get("end")) if isinstance(period, dict) else None,
        "claim_deadline": as_date(e.get("claim_deadline")),
        "payout": e.get("payout") or "",
        "payout_estimate_usd": float(est) if isinstance(est, (int, float)) else None,
        "proof_required": e.get("proof_required"),
        "claim_url": e.get("claim_url"),
        "source_url": first_url(e),
        "notes": e.get("notes") or "",
        "checked_on": as_date(e.get("checked_on")),
        "verified": e.get("verified") is True,
    }


def norm_disputes(raw: object) -> dict[str, dict]:
    """{"credit": FCBA billing-error rule, "debit": Reg E error rule}, each {name, summary, source_url, days}."""
    out: dict[str, dict] = {}
    for e in _verified(_items(raw)):
        kind, applies = str(e.get("kind") or ""), str(e.get("applies_to") or "")
        slot = ("credit" if kind == "credit_card_billing_error"
                else "debit" if kind == "debit_card_error" or (applies == "debit_card" and "error" in kind) else None)
        if slot and slot not in out:
            out[slot] = {"name": e.get("label") or kind, "summary": e.get("summary") or "",
                         "source_url": first_url(e), "days": e.get("notice_deadline_days"), "law": e.get("law")}
    return out


def _norm_comp(e: dict) -> dict | None:
    if not isinstance(e, dict) or e.get("verified") is not True:
        return None
    return {
        "name": e.get("law") or "",
        "summary": e.get("summary") or "",
        "source_url": first_url(e),
        "currency": e.get("currency") or "EUR",
        "delay_hours": e.get("delay_threshold_hours"),
        "notice_days": e.get("cancellation_notice_days"),
        "bands": [{"min_km": b.get("min_km") or 0, "max_km": b.get("max_km"), "amount": b.get("amount"),
                   "label": b.get("label") or ""}
                  for b in e.get("bands") or [] if isinstance(b, dict) and b.get("amount") is not None],
    }


def norm_flights(raw: object) -> dict:
    raw = plain(raw) or {}
    us = raw.get("us_dot") or {}
    sig = us.get("significant_change") or {}
    us_dot = None
    if us.get("verified") is True:
        us_dot = {"name": us.get("law") or "", "summary": us.get("summary") or "", "source_url": first_url(us),
                  "domestic_hours": sig.get("domestic_hours"), "international_hours": sig.get("international_hours")}
    airlines = [{"name": a.get("name") or "", "match": list(a.get("match") or []), "refund_url": a.get("refund_url"),
                 "compensation_url": a.get("compensation_url"), "source_url": first_url(a)}
                for a in _verified(_items(raw.get("airlines") or []))]
    return {"us_dot": us_dot, "eu261": _norm_comp(raw.get("eu261")), "uk261": _norm_comp(raw.get("uk261")),
            "airlines": airlines}


# --- The rulebook -------------------------------------------------------------------------------------

def _first_match(entries: list[dict], key: str) -> Callable[[str], dict | None]:
    ordered = sorted(entries, key=lambda e: bool(e.get("generic")))  # catch-all entries last

    def find(text: str) -> dict | None:
        return next((e for e in ordered if search_terms(text, e.get(key) or [])), None)
    return find


@dataclass
class Rulebook:
    retailers: list[dict] = field(default_factory=list)
    bills: list[dict] = field(default_factory=list)
    bank_fees: list[dict] = field(default_factory=list)
    disputes: dict[str, dict] = field(default_factory=dict)
    flights: dict = field(default_factory=lambda: {"us_dot": None, "eu261": None, "uk261": None, "airlines": []})
    settlements: list[dict] = field(default_factory=list)
    retailer_for: Callable[[str], dict | None] | None = None
    bill_provider_for: Callable[[str], dict | None] | None = None
    fee_kind_for: Callable[[str], dict | None] | None = None
    airline_for: Callable[[str], dict | None] | None = None
    settlements_matching: Callable[[str, date], list[dict]] | None = None
    origin: str = "inline"  # inline | package | json

    def __post_init__(self) -> None:
        self.retailer_for = self.retailer_for or _first_match(self.retailers, "match")
        self.bill_provider_for = self.bill_provider_for or _first_match(self.bills, "match")
        self.fee_kind_for = self.fee_kind_for or _first_match(self.bank_fees, "patterns")
        self.airline_for = self.airline_for or _first_match(self.flights.get("airlines") or [], "match")
        if self.settlements_matching is None:
            def matching(text: str, today: date) -> list[dict]:
                return [s for s in self.settlements
                        if (s["claim_deadline"] is None or s["claim_deadline"] >= today)
                        and search_terms(text, s["match"])]
            self.settlements_matching = matching

    @classmethod
    def from_data(cls, *, retailers=(), bills=(), bank_fees=(), disputes=None, flights=None, settlements=(),
                  origin: str = "inline") -> "Rulebook":
        """Build from raw rules-file shapes (as in backend/clawback/rules/*.json). Drops unverified entries."""
        return cls(
            retailers=[r for r in map(norm_retailer, _items(retailers)) if r["verified"]],
            bills=[b for b in map(norm_bill, _items(bills)) if b["verified"]],
            bank_fees=[f for f in map(norm_fee, _items(bank_fees)) if f["verified"]],
            disputes=norm_disputes(disputes or []),
            flights=norm_flights(flights or {}),
            settlements=[s for s in map(norm_settlement, _items(settlements)) if s["verified"]],
            origin=origin,
        )


def _load_json(name: str) -> object:
    path = RULES_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def _from_package(pkg) -> Rulebook:
    """Use the rules package's loaders, and its match helpers mapped onto our verified entries."""
    book = Rulebook.from_data(
        retailers=plain(pkg.retailers()), bills=plain(pkg.bills()), bank_fees=plain(pkg.bank_fees()),
        disputes=plain(pkg.disputes()), flights=plain(pkg.flights()), settlements=plain(pkg.settlements()),
        origin="package",
    )

    def mapped(helper_name: str, entries: list[dict], key: str, raw_key: str | None = None):
        helper = getattr(pkg, helper_name, None)
        if helper is None:
            return None

        def find(text: str) -> dict | None:
            hit = plain(helper(text))
            if not hit:
                return None
            value = hit if isinstance(hit, str) else hit.get(raw_key or key)
            return next((e for e in entries if e.get(key) == value), None)  # None when the hit isn't verified
        return find

    book.retailer_for = mapped("retailer_for", book.retailers, "store") or book.retailer_for
    book.bill_provider_for = mapped("bill_provider_for", book.bills, "provider") or book.bill_provider_for
    book.fee_kind_for = mapped("fee_kind_for", book.bank_fees, "kind") or book.fee_kind_for
    book.airline_for = mapped("airline_for", book.flights["airlines"], "name") or book.airline_for
    if hasattr(pkg, "settlements_matching"):
        ids = {s["id"]: s for s in book.settlements}

        def matching(text: str, today: date) -> list[dict]:
            out = []
            for hit in plain(pkg.settlements_matching(text, today)) or []:
                s = ids.get(str(hit.get("id") or hit.get("name"))) if isinstance(hit, dict) else None
                if s:
                    out.append(s)
            return out
        book.settlements_matching = matching
    return book


def current() -> Rulebook | None:
    try:
        from .. import rules as pkg  # noqa: PLC0415 (written by another agent; may not exist yet)
    except ImportError:
        pkg = None
    if pkg is not None and all(hasattr(pkg, n) for n in ("retailers", "bills", "bank_fees", "disputes",
                                                          "flights", "settlements")):
        return _from_package(pkg)
    if not RULES_DIR.is_dir() or not any(RULES_DIR.glob("*.json")):
        return None
    return Rulebook.from_data(
        retailers=_load_json("retailers"), bills=_load_json("bills"), bank_fees=_load_json("bank_fees"),
        disputes=_load_json("disputes"), flights=_load_json("flights") or {}, settlements=_load_json("settlements"),
        origin="json",
    )
