"""Checks that a model's answer is grounded in the text it read.

Models only copy facts out of untrusted text (emails, receipts, web pages). Before code uses a value, it checks that
the value is written in that text: an amount must appear as a number, a name's words must appear, a code (order or
flight number) must appear, a date must appear in some written form. A value that fails is dropped, so a model can't
invent or change an amount, whatever the text tells it to do. Dates and dollars are then worked out by code.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta

_NUMBER = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\d.,])\d+(?:\.\d+)?")
_MONEY = re.compile(r"(?:[$\u20ac\u00a3]|\b(?:usd|eur|gbp)\b)\s?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
                    r"|(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})(?!\d)", re.I)
_WORD = re.compile(r"[a-z0-9]+")
URL = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|net|org|io|co|tv|app|us|biz|info|ly|me|xyz|link|site)\b", re.I)
MONTHS = ("january february march april may june july august september october november december").split()


def number(value) -> float | None:
    """A finite, non-negative number from a model answer (not a bool, not a string)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def numbers_in(text: str) -> set[float]:
    """Every number written in the text ("$1,299.00" -> 1299.0, "Nov 4" -> 4.0)."""
    return {round(float(n.replace(",", "")), 2) for n in _NUMBER.findall(text or "")}


def money_in(text: str) -> set[float]:
    """Amounts written as money: with a currency sign or code, or with two decimals ("$55", "129.99", "USD 12")."""
    out: set[float] = set()
    for a, b in _MONEY.findall(text or ""):
        out.add(round(float((a or b).replace(",", "")), 2))
    return out


def amount_ok(value, text: str, strict: bool = False) -> float | None:
    """The amount if it is written in the text, else None. strict=True needs it written as money."""
    v = number(value)
    if v is None or v == 0:
        return None
    v = round(v, 2)
    return v if v in (money_in(text) if strict else numbers_in(text)) else None


def integer_ok(value, text: str) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if re.search(rf"(?<![\d.]){value}(?![\d])", text or "") else None


def words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def phrase_ok(value, text: str, limit: int = 120) -> str | None:
    """A name (item, plan, provider) if every word of it appears in the text and it carries no link."""
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" ,.-:;")[:limit].strip()
    if not cleaned or URL.search(cleaned) or "<" in cleaned or ">" in cleaned:
        return None
    have = set(words(text))
    need = words(cleaned)
    return cleaned if need and all(w in have for w in need) else None


def _alnum(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def code_ok(value, text: str, limit: int = 40) -> str | None:
    """An order, confirmation or flight number if it appears in the text (spaces and dashes ignored)."""
    if not isinstance(value, str):
        return None
    code = value.strip().lstrip("#").strip()
    if not code or len(code) > limit or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]*", code):
        return None
    key = _alnum(code)
    return code if len(key) >= 3 and key in _alnum(text) else None


def _date_forms(d: date) -> list[str]:
    mon, full = MONTHS[d.month - 1][:3], MONTHS[d.month - 1]
    out = [d.isoformat(), f"{d.month}/{d.day}", f"{d.month:02d}/{d.day:02d}"]  # US order only: 4/11 is April 11
    for name in {mon, full, "sept" if d.month == 9 else mon}:
        out += [f"{name} {d.day}", f"{name}. {d.day}", f"{d.day} {name}", f"{name} {d.day:02d}"]
    return out


def date_ok(value, text: str, ref: date) -> date | None:
    """A "YYYY-MM-DD" answer, kept only if the text writes that month and day. When the text gives no year, code
    picks it the way bills.find_date does (the next such day on or after a month before `ref`)."""
    if not isinstance(value, str):
        return None
    try:
        d = date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
    low = re.sub(r"\s+", " ", (text or "").lower())
    if not any(re.search(rf"(?<![\w/]){re.escape(form)}(?![\d])", low) for form in _date_forms(d)):
        return None
    if str(d.year) in low:
        return d
    try:
        guess = date(ref.year, d.month, d.day)
        return guess if guess >= ref - timedelta(days=31) else date(ref.year + 1, d.month, d.day)
    except ValueError:
        return None


def time_ok(value, text: str) -> str | None:
    """An "HH:MM" answer (24-hour), kept only if the text writes that time ("8:05 AM", "08:05", "20:05")."""
    if not isinstance(value, str):
        return None
    try:
        t = datetime.strptime(value.strip(), "%H:%M")
    except ValueError:
        return None
    h12 = t.hour % 12 or 12
    ampm = "am" if t.hour < 12 else "pm"
    low = (text or "").lower()
    forms = [rf"(?<!\d){h12}:{t.minute:02d}\s?{ampm}", rf"(?<!\d)0?{h12}:{t.minute:02d}\s?{ampm[0]}\.?m",
             rf"(?<!\d){t.hour:02d}:{t.minute:02d}(?!\s?[ap])", rf"(?<!\d){t.hour}:{t.minute:02d}(?!\s?[ap])"]
    return t.strftime("%H:%M") if any(re.search(f, low) for f in forms) else None
