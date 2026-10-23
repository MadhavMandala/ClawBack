"""Load the synthetic people in evals/data and check that their labels hang together."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

EMAIL_KINDS = ("delivery_order", "inactivity", "engagement", "price_change", "trial", "store_receipt", "other",
               "irrelevant")
SIGNAL_KINDS = EMAIL_KINDS[:6]  # the kinds that change what the product concludes
SCORED_FLAGS = ("unused", "price_increase", "overlap", "trial_ending", "membership_losing_money", "bill_increase",
                "promo_ending")
FINDING_KINDS = ("duplicate_charge", "bank_fee", "price_drop", "flight_refund", "flight_compensation", "settlement")
CADENCE_DAYS = {"weekly": (5, 9), "monthly": (25, 36), "quarterly": (85, 95), "annual": (355, 375)}
CHECK_TYPES = ("email_kind", "email_merchant", "sub_found", "sub_flag", "not_sub", "no_finding", "finding_found",
               "injection")


def files(data_dir: Path = DATA_DIR) -> list[Path]:
    return sorted(data_dir.glob("p*.json"))


def load(data_dir: Path = DATA_DIR) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in files(data_dir)]


def fingerprint(data_dir: Path = DATA_DIR) -> str:
    """sha256 over the data files, so a result can say exactly which data it was measured on. Line endings are
    normalised, so a Windows checkout (CRLF) gives the same fingerprint."""
    h = hashlib.sha256()
    for p in files(data_dir):
        h.update(p.name.encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def _bank_charges(person: dict, label: dict) -> list[dict]:
    keys = [k.upper() for k in label["bank"]]
    txs = [t for t in person["transactions"] if t["amount"] > 0 and any(k in t["description"].upper() for k in keys)]
    if not label["variable"]:
        # Several subscriptions can share one descriptor (APPLE.COM/BILL): the amount tells them apart. A price
        # change keeps the older charges under the same label.
        same = [t for t in txs if abs(t["amount"] - label["amount"]) < 0.005]
        if same:
            first = min(t["date"] for t in same)
            older = [t for t in txs if t["date"] < first and t not in same]
            rose = {"price_increase", "bill_increase"} & set(label.get("flags") or [])
            txs = older + same if rose else same
    return sorted(txs, key=lambda t: t["date"])


def problems(person: dict) -> list[str]:
    """Everything wrong with one person's data and labels (empty list = consistent)."""
    out: list[str] = []
    pid = person["person"]["id"]
    tx_ids = Counter(t["id"] for t in person["transactions"])
    mail_ids = Counter(e["id"] for e in person["emails"])
    out += [f"{pid}: duplicate transaction id {i}" for i, n in tx_ids.items() if n > 1]
    out += [f"{pid}: duplicate email id {i}" for i, n in mail_ids.items() if n > 1]
    if person.get("synthetic") is not True:
        out.append(f"{pid}: not marked synthetic")
    today = date.fromisoformat(person["today"])
    for t in person["transactions"]:
        if date.fromisoformat(t["date"]) > today:
            out.append(f"{pid}: transaction {t['id']} is after today")
    for e in person["emails"]:
        lab = e.get("label") or {}
        if lab.get("kind") not in EMAIL_KINDS:
            out.append(f"{pid}: email {e['id']} has kind {lab.get('kind')!r}")
        if lab.get("merchant") and not lab.get("names"):
            out.append(f"{pid}: email {e['id']} names a merchant but no match names")
        if e.get("format") not in ("text", "html"):
            out.append(f"{pid}: email {e['id']} format {e.get('format')!r}")

    labels = person["labels"]
    sub_ids = Counter(s["id"] for s in labels["subscriptions"])
    out += [f"{pid}: duplicate subscription label {i}" for i, n in sub_ids.items() if n > 1]
    for s in labels["subscriptions"]:
        where = f"{pid}/{s['id']}"
        if not s["names"]:
            out.append(f"{where}: no match names")
        for k in s["flags"]:
            if k not in SCORED_FLAGS:
                out.append(f"{where}: unknown flag {k!r}")
        for e in s["evidence_emails"]:
            if e not in mail_ids:
                out.append(f"{where}: evidence email {e} does not exist")
        if not s["bank"]:
            if not s["evidence_emails"]:
                out.append(f"{where}: no bank charges and no email behind it")
            continue
        charges = _bank_charges(person, s)
        if not charges:
            out.append(f"{where}: no transactions behind it")
            continue
        if not s["variable"] and abs(charges[-1]["amount"] - s["amount"]) > 0.005:
            out.append(f"{where}: latest charge {charges[-1]['amount']} != label amount {s['amount']}")
        lo, hi = CADENCE_DAYS[s["cadence"]]
        dates = [date.fromisoformat(t["date"]) for t in charges]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        if any(not lo <= g <= hi for g in gaps):
            out.append(f"{where}: charge gaps {gaps} don't fit {s['cadence']}")
        if s["cadence"] in ("weekly", "monthly") and len(charges) < 2:
            out.append(f"{where}: {s['cadence']} but only {len(charges)} charge")
        if s["variable"]:
            mean = sum(t["amount"] for t in charges) / len(charges)
            if abs(mean - s["amount"]) > 0.05 * s["amount"]:
                out.append(f"{where}: variable amount {s['amount']} is not the charges' average {mean:.2f}")

    finding_ids = Counter(f["id"] for f in labels["findings"])
    out += [f"{pid}: duplicate finding label {i}" for i, n in finding_ids.items() if n > 1]
    for f in labels["findings"]:
        where = f"{pid}/{f['id']}"
        if f["kind"] not in FINDING_KINDS:
            out.append(f"{where}: unknown finding kind {f['kind']!r}")
        ev = f["evidence"]
        if not ev["transactions"] and not ev["emails"]:
            out.append(f"{where}: no evidence")
        out += [f"{where}: evidence transaction {t} missing" for t in ev["transactions"] if t not in tx_ids]
        out += [f"{where}: evidence email {e} missing" for e in ev["emails"] if e not in mail_ids]
        if f["kind"] == "duplicate_charge":
            txs = [t for t in person["transactions"] if t["id"] in ev["transactions"]]
            if len(txs) < 2 or len({(t["description"], t["amount"]) for t in txs}) != 1:
                out.append(f"{where}: a duplicate needs two identical charges")
            elif abs(txs[0]["amount"] * (len(txs) - 1) - (f["amount"] or 0)) > 0.005:
                out.append(f"{where}: amount should be the extra charges")
        if f["kind"] == "bank_fee":
            txs = [t for t in person["transactions"] if t["id"] in ev["transactions"]]
            if len(txs) != 1 or abs(txs[0]["amount"] - f["amount"]) > 0.005:
                out.append(f"{where}: a fee label needs its one fee charge, same amount")

    not_subs = {n["id"] for n in labels["not_subscriptions"]}
    for trap in labels["traps"]:
        for c in trap["checks"]:
            where = f"{pid}/{trap['id']}"
            if c["type"] not in CHECK_TYPES:
                out.append(f"{where}: unknown check {c['type']!r}")
            if "email" in c and c["email"] not in mail_ids:
                out.append(f"{where}: check names missing email {c['email']}")
            if "sub" in c and c["sub"] not in sub_ids:
                out.append(f"{where}: check names missing subscription {c['sub']}")
            if "finding" in c and c["finding"] not in finding_ids:
                out.append(f"{where}: check names missing finding {c['finding']}")
            if c["type"] == "not_sub" and c["ref"] not in not_subs:
                out.append(f"{where}: check names missing non-subscription {c['ref']}")
        if not trap["checks"]:
            out.append(f"{pid}/{trap['id']}: trap has no checks")
    return out


def stats(people: list[dict]) -> dict:
    emails = [e for p in people for e in p["emails"]]
    return {
        "people": len(people),
        "transactions": sum(len(p["transactions"]) for p in people),
        "emails": len(emails),
        "email_kinds": dict(Counter(e["label"]["kind"] for e in emails)),
        "subscriptions_labelled": sum(1 for p in people for s in p["labels"]["subscriptions"]
                                      if s["kind"] == "subscription"),
        "bills_labelled": sum(1 for p in people for s in p["labels"]["subscriptions"] if s["kind"] == "bill"),
        "flags_labelled": sum(len(s["flags"]) for p in people for s in p["labels"]["subscriptions"]),
        "findings_labelled": sum(len(p["labels"]["findings"]) for p in people),
        "traps": sum(len(p["labels"]["traps"]) for p in people),
        "today": people[0]["today"] if people else None,
    }
