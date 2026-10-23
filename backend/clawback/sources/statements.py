"""Bank statement upload: the no-approval-needed way to get transactions.

CSV: a header row with a date column, a description column and an amount column (or separate debit/credit columns).
OFX / QFX (Quicken): OFX 1.x (SGML, leaf tags left open) and 2.x (XML). Each <STMTTRN> gives DTPOSTED (the date),
TRNAMT (negative = money out) and NAME, or MEMO when NAME is empty. FITID gives a stable id, so uploading the same
file twice doesn't add the charges twice. parse_upload() picks the reader from the file name or the content.
Charges are stored as positive amounts.
TODO(clawback): per-bank CSV quirks beyond these common column names.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from html import unescape

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


# --- OFX / QFX ---------------------------------------------------------------------------------------

OFX_EXTENSIONS = (".ofx", ".qfx")
_OFX_SNIFF = re.compile(r"OFXHEADER|<OFX>", re.I)
_TRN_START = re.compile(r"<STMTTRN>", re.I)
_TRN_END = re.compile(r"</STMTTRN>|<STMTTRN>|</BANKTRANLIST>", re.I)
_LEAF = re.compile(r"<([A-Za-z0-9_.]+)>([^<]*)")  # a tag and its text up to the next tag (SGML or XML)
_ACCTID = re.compile(r"<ACCTID>([^<\r\n]*)", re.I)


def is_ofx(content: str, filename: str | None = None) -> bool:
    if filename and filename.lower().endswith(OFX_EXTENSIONS):
        return True
    return bool(_OFX_SNIFF.search(content[:4096]))


def _ofx_fields(block: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag, value in _LEAF.findall(block):
        value = unescape(value).strip()
        if value and tag.upper() not in out:
            out[tag.upper()] = value
    return out


def _ofx_date(text: str) -> date | None:
    """DTPOSTED is YYYYMMDD, often followed by HHMMSS[.XXX][[-5:EST]]."""
    digits = re.match(r"\s*(\d{8})", text or "")
    if not digits:
        return None
    try:
        return datetime.strptime(digits.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _ofx_amount(text: str) -> float | None:
    t = (text or "").strip().replace(" ", "")
    if "," in t and "." not in t:  # some exporters write a decimal comma
        t = t.replace(",", ".")
    t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def parse_ofx(content: str) -> list[Transaction]:
    """Transactions from an OFX 1.x (SGML) or 2.x (XML) file. Raises ValueError when it has none we can read."""
    if not _OFX_SNIFF.search(content[:4096]) and not _TRN_START.search(content):
        raise ValueError("This doesn't look like an OFX or QFX file.")
    accounts = [(m.start(), m.group(1).strip()) for m in _ACCTID.finditer(content)]
    out: list[Transaction] = []
    seen: set[str] = set()
    for start in _TRN_START.finditer(content):
        rest = content[start.end():]
        end = _TRN_END.search(rest)
        f = _ofx_fields(rest[:end.start()] if end else rest)
        when, amount = _ofx_date(f.get("DTPOSTED", "")), _ofx_amount(f.get("TRNAMT", ""))
        description = f.get("NAME") or f.get("MEMO") or f.get("PAYEE") or ""
        if when is None or amount is None or not description:
            continue
        account = next((a for pos, a in reversed(accounts) if pos < start.start()), "")
        key = f.get("FITID") or f"{when.isoformat()}|{amount}|{description}|{len(out)}"
        tx_id = "ofx-" + hashlib.sha1(f"{account}|{key}".encode()).hexdigest()[:12]
        if tx_id in seen:
            continue
        seen.add(tx_id)
        out.append(Transaction(id=tx_id, date=when, description=description, amount=round(-amount, 2),
                               source="statement"))
    if not out:
        raise ValueError("No transactions found in this OFX file. It needs STMTTRN entries with DTPOSTED, TRNAMT and NAME.")
    return out


def decode(raw: bytes) -> str:
    """UTF-8 (with or without a byte-order mark), else Windows-1252, which OFX 1.x files often use."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def parse_upload(raw: bytes, filename: str | None = None) -> tuple[str, list[Transaction]]:
    """("ofx" | "csv", transactions) for an uploaded statement file. Raises ValueError with a plain message."""
    content = decode(raw)
    if is_ofx(content, filename):
        return "ofx", parse_ofx(content)
    return "csv", parse_csv(content)
