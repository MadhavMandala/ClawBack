"""Bank statement CSV upload: the no-approval-needed way to get transactions.

Accepts a CSV with a header row containing a date column, a description column and an amount column
(or separate debit/credit columns). Charges are stored as positive amounts.
MISSING: OFX/QFX files, and per-bank format quirks beyond these common column names.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

from ..models import Transaction

DATE_COLS = ("date", "transaction date", "posted date", "posting date")
DESC_COLS = ("description", "name", "merchant", "payee", "details")
AMOUNT_COLS = ("amount",)
DEBIT_COLS = ("debit", "withdrawal", "withdrawals")
CREDIT_COLS = ("credit", "deposit", "deposits")
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y")


def _col(header: list[str], names: tuple[str, ...]) -> int | None:
    low = [h.strip().lower() for h in header]
    return next((low.index(n) for n in names if n in low), None)


def _date(text: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {text!r}")


def _money(text: str) -> float | None:
    t = text.strip().replace("$", "").replace(",", "")
    if not t:
        return None
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    return float(t)


def parse_csv(content: str, id_prefix: str = "s") -> list[Transaction]:
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    di, de = _col(header, DATE_COLS), _col(header, DESC_COLS)
    ai, dbi, cri = _col(header, AMOUNT_COLS), _col(header, DEBIT_COLS), _col(header, CREDIT_COLS)
    if di is None or de is None or (ai is None and dbi is None):
        raise ValueError("CSV needs date, description and amount (or debit) columns")

    single = [_money(r[ai]) for r in body if ai is not None and len(r) > ai and r[ai].strip()]
    # In a single amount column, banks differ on whether charges are negative or positive.
    # Assume whichever sign is more common is the charges.
    charges_negative = sum(1 for v in single if v is not None and v < 0) >= len(single) / 2 if single else True

    out: list[Transaction] = []
    for i, r in enumerate(body):
        if len(r) <= max(di, de):
            continue
        if ai is not None:
            v = _money(r[ai])
            if v is None:
                continue
            amount = -v if charges_negative else v
        else:
            debit = _money(r[dbi]) if len(r) > dbi else None
            credit = _money(r[cri]) if cri is not None and len(r) > cri else None
            amount = (debit or 0.0) - (credit or 0.0)
        out.append(Transaction(id=f"{id_prefix}{i:05d}", date=_date(r[di]), description=r[de].strip(), amount=round(amount, 2), source="statement"))
    return out
