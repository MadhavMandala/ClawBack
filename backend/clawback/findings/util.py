"""Small shared helpers for the detectors: stable ids, dates, money, merchant names."""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date, datetime


def finding_id(kind: str, *facts: object) -> str:
    """Stable across re-runs, so a dismissed or done finding stays that way."""
    digest = hashlib.sha1("|".join([kind, *(str(f) for f in facts)]).encode()).hexdigest()[:12]
    return f"{kind.replace('_', '-')}-{digest}"


def end_of_month(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def as_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def money(amount: float, currency: str = "USD") -> str:
    symbol = {"USD": "$", "EUR": "EUR ", "GBP": "GBP "}.get(currency, f"{currency} ")
    return f"{symbol}{amount:,.2f}"


def day(d: date | None) -> str:
    return f"{d:%b} {d.day}, {d.year}" if d else "unknown date"


def merchant_words(description: str, n: int = 2) -> list[str]:
    """'BEST BUY 00012345 ATLANTA' -> ['best', 'buy']."""
    return re.sub(r"[^a-z ]+", " ", description.lower()).split()[:n]


def merchant_name(description: str) -> str:
    return " ".join(merchant_words(description)).title() or description.strip()


def first_url(entry: dict) -> str | None:
    if entry.get("source_url"):
        return entry["source_url"]
    urls = entry.get("source_urls") or []
    return urls[0] if urls else None


def search_terms(text: str, terms: list[str]) -> bool:
    """Case-insensitive match of any term (a regex if it compiles, else plain text)."""
    low = (text or "").lower()
    for term in terms or []:
        if not term:
            continue
        try:
            if re.search(term, low, re.I):
                return True
        except re.error:
            if term.lower() in low:
                return True
    return False


def fee_name(label: str, lower: bool = False) -> str:
    """'ATM fee (out-of-network fee or operator surcharge)' -> 'ATM fee'; lower=True keeps acronyms."""
    short = label.split(" (")[0].strip() or label
    if lower and not short.split()[0].isupper():
        short = short[0].lower() + short[1:]
    return short


def times(n: int) -> str:
    return {1: "once", 2: "twice", 3: "three times"}.get(n, f"{n} times")


STALE_AFTER_DAYS = 92  # rules/README.md: re-check anything older than ~3 months


def stale_note(checked_on: date | None, today: date) -> list[str]:
    if checked_on and (today - checked_on).days > STALE_AFTER_DAYS:
        return [f"This rule was last checked on {day(checked_on)}: check the official page before relying on it."]
    return []
