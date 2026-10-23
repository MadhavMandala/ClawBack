"""Known subscription merchants: how they appear on bank statements and who they email from.

The list lives in rules/merchants.json (common US subscriptions and bills, with bank-descriptor fragments, sender
domains, category and whether it's a bill; the file's note says how it was made). Matching follows the rules
package: fragments are UPPERCASE descriptor pieces, matched case-insensitively from a word start, `exclude`
fragments veto a row, and the longest match wins. Descriptors are hints, not published formats.

Recurring charges the list doesn't know are named by pipeline/naming.py (Nemotron 3.5 Lightning, cached).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .rules import match_strength

RULES_FILE = Path(__file__).resolve().parent / "rules" / "merchants.json"

APPLE_SUBSCRIPTIONS_URL = "https://apps.apple.com/account/subscriptions"  # verified 2026-10-22
GOOGLE_PLAY_SUBSCRIPTIONS_URL = "https://play.google.com/store/account/subscriptions"  # verified 2026-10-22

CATEGORIES = (
    "video_streaming", "music", "audiobooks_books", "news", "software", "software_creative", "cloud_storage",
    "ai_assistant", "security_vpn", "fitness", "wellness", "dating", "gaming", "education", "delivery_membership",
    "shopping_membership", "meal_kit", "home_security", "mobile", "internet", "insurance", "other",
)


@dataclass(frozen=True)
class Merchant:
    name: str
    category: str
    bank_patterns: tuple[str, ...] = ()  # rules-style descriptor fragments ("NETFLIX", "GOOGLE *GOOGLE ONE")
    sender_domains: tuple[str, ...] = ()
    billed_by: str | None = None  # "apple" / "google_play" when the store, not the merchant, bills it
    known_cancel_url: str | None = None  # only URLs checked against official docs go here
    aliases: tuple[str, ...] = field(default=())
    bill: bool = False  # phone, internet, insurance: a bill rather than a subscription
    membership: str | None = None  # key into rules/memberships.json (dashpass, uber_one, amazon_prime ...)
    exclude: tuple[str, ...] = ()


class MerchantRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    category: Literal[CATEGORIES]  # type: ignore[valid-type]
    bill: bool = False
    match: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    billed_by: Literal["apple", "google_play"] | None = None
    membership: str | None = None
    evidence: Literal["official", "common", "guess"] = "common"
    source_url: str | None = None


class MerchantsFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    note: str
    checked_on: date
    merchants: tuple[MerchantRow, ...] = Field(min_length=1)


@lru_cache
def merchants_file() -> MerchantsFile:
    return MerchantsFile.model_validate(json.loads(RULES_FILE.read_text(encoding="utf-8")))


def _merchant(row: MerchantRow) -> Merchant:
    cancel = {"apple": APPLE_SUBSCRIPTIONS_URL, "google_play": GOOGLE_PLAY_SUBSCRIPTIONS_URL}.get(row.billed_by or "")
    return Merchant(row.name, row.category, row.match, row.domains, row.billed_by, cancel, row.aliases, row.bill,
                    row.membership, row.exclude)


MERCHANTS: list[Merchant] = [_merchant(r) for r in merchants_file().merchants]

# Categories where paying for two at once is usually waste (flag), vs. where it is often a choice (info only).
OVERLAP_CATEGORIES = {"cloud_storage", "music", "ai_assistant"}

APPLE_BILL_PATTERN = re.compile(r"apple\.com/bill|itunes\.com/bill", re.I)
GOOGLE_PLAY_PATTERN = re.compile(r"google ?\*(?!google one)", re.I)

# Card processors and bank wording put in front of the merchant's name ("SQ *SOME GYM", "TST* CAFE").
_BANK_PREFIX = re.compile(
    r"^(?:POS (?:DEBIT|PURCHASE)|DEBIT CARD PURCHASE|RECURRING (?:DEBIT |CARD )?(?:PAYMENT|PURCHASE)|CHECKCARD(?: \d+)?|"
    r"PURCHASE(?: AUTHORIZED ON \d\d/\d\d)?|ACH (?:DEBIT|WITHDRAWAL)|PREAUTHORIZED DEBIT|ONLINE PAYMENT)\s+", re.I)
_PROCESSOR_PREFIX = re.compile(
    r"^(?:SQ ?\*|SQU ?\*|TST ?\*|PAYPAL ?\*|PP ?\*|SP ?\*|PY ?\*|IN ?\*|FS ?\*|DD ?\*|WPY ?\*|CKO ?\*|2CO ?\*|"
    r"PADDLE\.NET ?\*|STRIPE ?\*|BT ?\*|ZSL ?\*|AMZ ?\*|GOOGLE ?\*|APPLE\.COM/BILL)\s*", re.I)


def clean_descriptor(description: str) -> str:
    """'SQ *SOME GYM 1234 ATLANTA GA' -> 'SOME GYM ATLANTA'. Code only: cuts card-processor prefixes, links,
    phone numbers, store numbers and a trailing state code. Never adds anything."""
    s = re.sub(r"\s+", " ", description or "").strip()
    for _ in range(2):
        s = _BANK_PREFIX.sub("", s)
        s = _PROCESSOR_PREFIX.sub("", s)
    s = re.sub(r"https?://\S+|www\.\S+|\S+/\S*", " ", s, flags=re.I)  # links and help paths ("g.co/payhelp#")
    s = re.sub(r"\b([A-Za-z][A-Za-z0-9-]*)\.(?:com|net|org|co|io|app|tv)\b(?:/\S*)?", r"\1", s, flags=re.I)
    s = re.sub(r"\+?\b1?[-. ]?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b", " ", s)
    s = re.sub(r"[#*]?\b[\w-]*\d[\w-]*\b", " ", s)
    s = re.sub(r"[^A-Za-z&'+. ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    s = re.sub(r"(?:^|\s+)[A-Z]{2}$", "", s)  # a trailing state code
    return s.strip()


def display_descriptor(description: str) -> str:
    """A readable form of a bank descriptor for an unknown charge: cleaned, title case, at most 40 characters."""
    cleaned = clean_descriptor(description) or re.sub(r"\s+", " ", description).strip()
    return " ".join(w.capitalize() for w in cleaned.split())[:40].strip() or description.strip()[:40]


@lru_cache(maxsize=8192)
def match_bank(description: str) -> Merchant | None:
    best, best_len = None, 0
    for m in MERCHANTS:
        n = match_strength(description, m.bank_patterns, m.exclude) if m.bank_patterns else 0
        if n > best_len:
            best, best_len = m, n
    return best


def match_sender(sender: str) -> Merchant | None:
    """The merchant a sender address belongs to: the longest matching domain, or None when several merchants share
    it (apple.com sends for iCloud+, Apple Music and Apple TV+ alike)."""
    domain = sender.split("@")[-1].lower().strip(" >")
    hits: list[tuple[int, Merchant]] = []
    for m in MERCHANTS:
        n = max((len(d) for d in m.sender_domains if domain == d or domain.endswith("." + d)), default=0)
        if n:
            hits.append((n, m))
    if not hits:
        return None
    longest = max(n for n, _ in hits)
    best = [m for n, m in hits if n == longest]
    return best[0] if len(best) == 1 else None


def by_name(name: str) -> Merchant | None:
    return next((m for m in MERCHANTS if m.name == name), None)


# One-word names that are also ordinary words: in free text they count only when capitalised as a name.
PLAIN_WORDS = {"Box", "Calm", "Cursor", "Factor", "Frontier", "Hinge", "Match", "Medium", "Notion", "Optimum",
               "Peacock", "Progressive", "Ring", "Slack", "Spectrum", "Tidal", "Visible", "Zoom", "Brilliant", "Cox",
               "Philo", "Starz", "Lemonade", "Verizon"}


@lru_cache(maxsize=1024)
def _word(term: str) -> re.Pattern[str]:
    flags = 0 if term in PLAIN_WORDS else re.I
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", flags)


def find_in_text(text: str) -> Merchant | None:
    """A merchant named in free text (a receipt line, a model's answer): whole words only, longest name wins."""
    best, best_len = None, 0
    for m in MERCHANTS:
        for term in (m.name, *m.aliases):
            if len(term) > best_len and _word(term).search(text or ""):
                best, best_len = m, len(term)
    return best
