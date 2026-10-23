"""Reference data for finding money people are owed: store price adjustments, flight refunds and
compensation, card/bank dispute rules, bank fees, bill providers and open class-action settlements.

Every fact in the JSON files beside this module was read on an official or primary page, recorded in
`source_url` / `source_urls`, and dated in `checked_on`. Rows marked `verified: false` could not be
confirmed and must not drive anything sent to a company. See README.md in this folder.

Matching: `match` entries are either UPPERCASE bank-descriptor fragments ("COMCAST") or lowercase
sender domains ("xfinity.com"). Both are matched case-insensitively and must start at a word
boundary; domains must also end at one. When several rows match, the longest matching entry wins.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_DIR = Path(__file__).parent
STALE_AFTER_DAYS = 92  # README rule: re-verify anything older than ~3 months


def _https(url: str) -> str:
    if not url.startswith("https://"):
        raise ValueError(f"URL must be https: {url!r}")
    return url


HttpsUrl = Annotated[str, AfterValidator(_https)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- matching


@lru_cache(maxsize=4096)
def _pattern(entry: str) -> re.Pattern[str]:
    body = r"(?<![A-Za-z0-9])" + re.escape(entry)
    if entry != entry.upper():  # a lowercase sender domain: also require a right boundary
        body += r"(?![A-Za-z0-9-])"
    return re.compile(body, re.IGNORECASE)


def match_strength(text: str, match: tuple[str, ...] | list[str], exclude: tuple[str, ...] | list[str] = ()) -> int:
    """Length of the longest `match` entry found in `text` (0 = no match, or an `exclude` entry matched)."""
    if not text or any(_pattern(x).search(text) for x in exclude):
        return 0
    return max((len(m) for m in match if _pattern(m).search(text)), default=0)


def _best(rows, text: str):
    best, best_len = None, 0
    for row in rows:
        n = match_strength(text, row.match, row.exclude)
        if n > best_len:
            best, best_len = row, n
    return best


def is_stale(checked_on: date, today: date | None = None, max_age_days: int = STALE_AFTER_DAYS) -> bool:
    """True when a fact was last checked more than ~3 months before `today`."""
    return ((today or date.today()) - checked_on).days > max_age_days


# ---------------------------------------------------------------- retailers.json


class Tier(_Model):
    name: str
    window_days: int


class Retailer(_Model):
    store: str
    match: tuple[str, ...] = Field(min_length=1)
    exclude: tuple[str, ...] = ()  # same format as match; any hit vetoes the row (e.g. APPLE.COM/BILL)
    adjusts: bool
    window_days: int | None
    window_from: Literal["purchase", "delivery"] | None
    tiers: tuple[Tier, ...] = ()
    conditions: str
    exclusions: tuple[str, ...] = ()
    how_to_claim: str
    claim_url: HttpsUrl | None
    source_url: HttpsUrl
    extra_source_urls: tuple[HttpsUrl, ...] = ()
    no_automated_requests: bool = False  # the store refuses requests filed by third-party services
    checked_on: date
    verified: bool

    def window_for(self, tier: str | None = None) -> int | None:
        """Window in days for a membership tier name (case-insensitive substring), else the default."""
        if tier:
            for t in self.tiers:
                if tier.lower() in t.name.lower():
                    return t.window_days
        return self.window_days


class RetailersFile(_Model):
    note: str
    checked_on: date
    retailers: tuple[Retailer, ...]


@lru_cache
def retailers() -> RetailersFile:
    return RetailersFile.model_validate(_load("retailers.json"))


def retailer_for(text: str) -> Retailer | None:
    """The store a bank description or sender address belongs to, e.g. "TARGET 00012345 MINNEAPOLIS"."""
    return _best(retailers().retailers, text)


# ---------------------------------------------------------------- flights.json


class UnverifiedUrl(_Model):
    url: HttpsUrl
    note: str


class SignificantChange(_Model):
    domestic_hours: int
    international_hours: int
    criteria: tuple[str, ...]


class RefundDeadline(_Model):
    credit_card_business_days: int
    other_payment_calendar_days: int
    clock_starts: str


class BagFeeRefund(_Model):
    domestic_hours: int
    international_hours: int
    international_long_haul_hours: int
    long_haul_rule: str
    measured_from: str
    requires: str
    also_refunded_if: str
    exemptions: tuple[str, ...]


class DelayCompensation(_Model):
    required: bool
    note: str
    withdrawn_on: date | None
    source_url: HttpsUrl


class UsDot(_Model):
    law: str
    applies_to: str
    refund_owed_when: tuple[str, ...]
    significant_change: SignificantChange
    refund_covers: str
    refund_deadline: RefundDeadline
    form_of_payment: str
    vouchers: str
    ancillary_fee_refund: str
    bag_fee_refund: BagFeeRefund
    delay_compensation: DelayCompensation
    summary: str
    source_urls: tuple[HttpsUrl, ...] = Field(min_length=1)
    unverified_urls: tuple[UnverifiedUrl, ...] = ()
    verified: bool


class Band(_Model):
    label: str
    min_km: int
    max_km: int | None
    intra_eu_only: bool
    amount: int
    reduced_amount: int
    reduced_if_rerouted_within_hours: int


class CompensationScheme(_Model):
    law: str
    currency: Literal["EUR", "GBP"]
    applies_to: tuple[str, ...]
    delay_threshold_hours: int
    cancellation_notice_days: int
    bands: tuple[Band, ...] = Field(min_length=3)
    long_haul_delay_3_to_4h_amount: int
    compensation_due_when: tuple[str, ...]
    exemption: str
    refund_option: str
    refund_within_days: int | None
    how_to_claim: str
    summary: str
    source_urls: tuple[HttpsUrl, ...] = Field(min_length=1)
    unverified_urls: tuple[UnverifiedUrl, ...] = ()
    pending_reform: str | None
    verified: bool


class Airline(_Model):
    name: str
    iata: str
    region: Literal["US", "EU", "UK"]
    match: tuple[str, ...] = Field(min_length=1)
    exclude: tuple[str, ...] = ()  # same format as match; any hit vetoes the row (e.g. APPLE.COM/BILL)
    refund_url: HttpsUrl | None
    compensation_url: HttpsUrl | None
    source_url: HttpsUrl
    extra_source_urls: tuple[HttpsUrl, ...] = ()
    notes: str
    checked_on: date
    verified: bool


class FlightsFile(_Model):
    note: str
    checked_on: date
    us_dot: UsDot
    eu261: CompensationScheme
    uk261: CompensationScheme
    airlines: tuple[Airline, ...]


@lru_cache
def flights() -> FlightsFile:
    return FlightsFile.model_validate(_load("flights.json"))


def airline_for(text: str) -> Airline | None:
    """The airline a bank description or sender address belongs to."""
    return _best(flights().airlines, text)


def delay_compensation(
    scheme: Literal["eu261", "uk261"], distance_km: float, arrival_delay_hours: float, intra_eu: bool = False
) -> int | None:
    """Fixed compensation for an arrival delay under EU261/UK261, in the scheme's currency.

    Covers delays only, and assumes the flight is in scope and no extraordinary circumstances
    applied (ClawBack can't know that, so present it as "may be owed"). Cancellations depend on
    notice and re-routing and are not computed here. `intra_eu` matters for EU261 only: an intra-EU
    flight over 3,500 km stays in the middle band.
    """
    s: CompensationScheme = getattr(flights(), scheme)
    if arrival_delay_hours < s.delay_threshold_hours:
        return None
    long_haul, middle = s.bands[2], s.bands[1]
    if distance_km <= s.bands[0].max_km:
        return s.bands[0].amount
    if distance_km <= middle.max_km or (intra_eu and scheme == "eu261"):
        return middle.amount
    if arrival_delay_hours < long_haul.reduced_if_rerouted_within_hours:
        return s.long_haul_delay_3_to_4h_amount
    return long_haul.amount


# ---------------------------------------------------------------- disputes.json


class DisputeRule(_Model):
    kind: str
    label: str
    law: str
    applies_to: Literal["credit_card", "debit_card", "remittance"]
    covers: tuple[str, ...]
    notice_deadline_days: int | None
    notice_clock_starts: str | None
    notice_method: str
    oral_notice_ok: bool | None
    acknowledge_within_days: int | None
    resolve_within_billing_cycles: int | None
    resolve_within_days_max: int | None
    investigate_business_days: int | None
    investigate_days_max: int | None
    investigate_days_max_extended: int | None = None
    provisional_credit: str | None
    extensions: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    liability_cap: str | None = None
    consumer_rights_pending: tuple[str, ...]
    notice_must_include: tuple[str, ...]
    summary: str
    source_urls: tuple[HttpsUrl, ...] = Field(min_length=1)
    verified: bool


class DisputesFile(_Model):
    note: str
    checked_on: date
    rules: tuple[DisputeRule, ...]


@lru_cache
def disputes() -> DisputesFile:
    return DisputesFile.model_validate(_load("disputes.json"))


def dispute_rule(kind: str) -> DisputeRule:
    """e.g. "credit_card_billing_error", "debit_card_error". Raises KeyError for an unknown kind."""
    for r in disputes().rules:
        if r.kind == kind:
            return r
    raise KeyError(kind)


def dispute_deadline(kind: str, statement_sent_on: date) -> date | None:
    """Last day the notice can reach the issuer/bank, counted from the date the statement showing the
    error was sent (for remittances: the disclosed date the funds were due). None if no fixed deadline."""
    days = dispute_rule(kind).notice_deadline_days
    return statement_sent_on + timedelta(days=days) if days is not None else None


# ---------------------------------------------------------------- bank_fees.json


class BankFee(_Model):
    kind: str
    label: str
    account: Literal["deposit", "credit_card", "any"]
    patterns: tuple[str, ...] = Field(min_length=1)
    rule: str
    reversal_tip: str
    source_url: HttpsUrl
    extra_source_urls: tuple[HttpsUrl, ...] = ()
    notes: str | None = None
    verified: bool


class BankFeesFile(_Model):
    note: str
    checked_on: date
    exclude_patterns: tuple[str, ...]
    fees: tuple[BankFee, ...]


@lru_cache
def bank_fees() -> BankFeesFile:
    return BankFeesFile.model_validate(_load("bank_fees.json"))


@lru_cache(maxsize=256)
def _regex(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


def bank_fee_for(description: str) -> BankFee | None:
    """The fee type a bank transaction description looks like (heuristic; first kind in file order wins).
    Refunds/reversals of a fee (see exclude_patterns) return None."""
    f = bank_fees()
    if not description or any(_regex(p).search(description) for p in f.exclude_patterns):
        return None
    for fee in f.fees:
        if any(_regex(p).search(description) for p in fee.patterns):
            return fee
    return None


def fee_kind_for(description: str) -> str | None:
    """e.g. "OVERDRAFT FEE" -> "overdraft"; None if it doesn't look like a bank fee."""
    fee = bank_fee_for(description)
    return fee.kind if fee else None


# ---------------------------------------------------------------- bills.json


class BillProvider(_Model):
    provider: str
    match: tuple[str, ...] = Field(min_length=1)
    exclude: tuple[str, ...] = ()  # same format as match; any hit vetoes the row (e.g. APPLE.COM/BILL)
    category: Literal["internet", "mobile", "insurance", "utility", "gym"]
    generic: bool = False  # a catch-all entry, only used when no named provider matches
    negotiable: bool
    variable_amount: bool
    account_url: HttpsUrl | None
    cancel_or_retention: HttpsUrl | None
    budget_billing_url: HttpsUrl | None = None
    assistance_url: HttpsUrl | None = None
    notes: str
    source_url: HttpsUrl
    extra_source_urls: tuple[HttpsUrl, ...] = ()
    checked_on: date
    verified: bool


class BillsFile(_Model):
    note: str
    checked_on: date
    providers: tuple[BillProvider, ...]


@lru_cache
def bills() -> BillsFile:
    return BillsFile.model_validate(_load("bills.json"))


def bill_provider_for(text: str) -> BillProvider | None:
    """The bill provider a bank description or sender address belongs to, e.g. "COMCAST CABLE COMM".
    Named providers win; the generic utility entry is a fallback."""
    rows = bills().providers
    return _best([p for p in rows if not p.generic], text) or _best([p for p in rows if p.generic], text)


# ---------------------------------------------------------------- settlements.json


class ClassPeriod(_Model):
    start: date | None
    end: date | None


class Settlement(_Model):
    id: str
    type: Literal["class_action", "ftc_refund"] = "class_action"
    name: str
    defendant: str
    match: tuple[str, ...] = Field(min_length=1)
    exclude: tuple[str, ...] = ()  # same format as match; any hit vetoes the row (e.g. APPLE.COM/BILL)
    # Words that must appear in the user's matched charges or emails before a match counts as likely,
    # e.g. PHARMACY for a prescriptions-only class. Empty means any match will do.
    evidence_words: tuple[str, ...] = ()
    who_qualifies: str
    class_period: ClassPeriod
    claim_deadline: date
    payout: str
    payout_estimate_usd: float | None
    proof_required: bool | None
    claim_url: HttpsUrl
    source_url: HttpsUrl
    extra_source_urls: tuple[HttpsUrl, ...] = ()
    notes: str = ""
    checked_on: date
    verified: bool

    def is_open(self, today: date | None = None) -> bool:
        return self.claim_deadline >= (today or date.today())


class SettlementsFile(_Model):
    note: str
    checked_on: date
    settlements: tuple[Settlement, ...]


@lru_cache
def settlements() -> SettlementsFile:
    return SettlementsFile.model_validate(_load("settlements.json"))


def open_settlements(today: date | None = None, include_unverified: bool = False) -> list[Settlement]:
    """Settlements still taking claims on `today` (default: the real date), soonest deadline first."""
    rows = [s for s in settlements().settlements if s.is_open(today) and (s.verified or include_unverified)]
    return sorted(rows, key=lambda s: (not s.verified, s.claim_deadline, s.name))


def settlements_matching(text: str, today: date | None = None, include_unverified: bool = False) -> list[Settlement]:
    """Open settlements whose defendant matches a bank description or sender address, best match first."""
    hits = [(match_strength(text, s.match, s.exclude), s) for s in open_settlements(today, include_unverified)]
    return [s for n, s in sorted(hits, key=lambda h: -h[0]) if n]


# ---------------------------------------------------------------- merchant_sites.json

# Hosts and paths where anyone can post, so a page there is never the merchant's own word.
_USER_CONTENT_HOSTS = ("community.", "communities.", "forum.", "forums.", "discussions.", "groups.", "sites.",
                       "docs.", "answers.", "discuss.")
_USER_CONTENT_PATHS = ("/thread/", "/threads/", "/community/", "/forum", "/discussion", "/questions/")


def on_domains(url: str, domains: tuple[str, ...] | list[str]) -> bool:
    """True when `url` is https, its host is one of `domains` or a subdomain of one, and it isn't a place for
    user-written posts (community., forum., /thread/ ...). Look-alikes such as netflix-cancel.com or
    netflix.com.example.io, and user@host tricks, are False."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit((url or "").strip())
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return False
    if parts.scheme != "https" or not host or parts.username or parts.password:
        return False
    if not any(host == d.lower() or host.endswith("." + d.lower()) for d in domains if d):
        return False
    if any(host.startswith(p) for p in _USER_CONTENT_HOSTS):
        return False
    path = parts.path.lower()
    return not any(p in path for p in _USER_CONTENT_PATHS)


class MerchantSite(_Model):
    merchant: str
    aliases: tuple[str, ...] = ()
    domains: tuple[str, ...] = Field(min_length=1)  # lowercase registrable domains, e.g. "netflix.com"
    help_url: HttpsUrl
    checked_on: date

    def owns(self, url: str) -> bool:
        return on_domains(url, self.domains)


class MerchantSitesFile(_Model):
    note: str
    checked_on: date
    merchants: tuple[MerchantSite, ...]


@lru_cache
def merchant_sites() -> MerchantSitesFile:
    return MerchantSitesFile.model_validate(_load("merchant_sites.json"))


def merchant_site(name: str) -> MerchantSite | None:
    """The merchant's own domains, by its name or an alias (case-insensitive), e.g. "Netflix"."""
    key = (name or "").strip().lower()
    for m in merchant_sites().merchants:
        if key == m.merchant.lower() or key in (a.lower() for a in m.aliases):
            return m
    return None


# ---------------------------------------------------------------- auto_renewal.json


class FederalLaw(_Model):
    law: str
    title: str
    rule: str
    user_right: str
    quote: str
    source_url: HttpsUrl
    extra_source_urls: tuple[HttpsUrl, ...] = ()
    checked_on: date
    verified: bool


class FtcRuleStatus(_Model):
    in_force: bool
    status: str
    source_urls: tuple[HttpsUrl, ...] = Field(min_length=1)
    checked_on: date
    notes: str = ""


class FederalRules(_Model):
    rosca: FederalLaw
    ftc_negative_option_rule: FtcRuleStatus


class StateAutoRenewal(_Model):
    state: str = Field(pattern=r"^[A-Z]{2}$")
    name: str
    law: str
    title: str
    effective: date | None
    rule: str
    user_right: str  # one plain sentence a user can rely on; hedged where the law has limits
    applies_when: Literal["any", "trial", "annual"] = "any"
    exclude_categories: tuple[str, ...] = ()  # Subscription.category values the law exempts
    applies_to: str
    price_increase_right: str | None = None
    quote: str
    source_url: HttpsUrl
    extra_source_urls: tuple[HttpsUrl, ...] = ()
    checked_on: date
    verified: bool
    confidence: Literal["high", "medium", "low"]
    notes: str = ""


class AutoRenewalFile(_Model):
    note: str
    checked_on: date
    federal: FederalRules
    states: tuple[StateAutoRenewal, ...]


@lru_cache
def auto_renewal() -> AutoRenewalFile:
    return AutoRenewalFile.model_validate(_load("auto_renewal.json"))


def auto_renewal_for(state: str | None) -> StateAutoRenewal | None:
    """The verified auto-renewal law row for a two-letter state code ("ca" works too), else None."""
    code = (state or "").strip().upper()
    return next((s for s in auto_renewal().states if s.state == code and s.verified), None)


# ---------------------------------------------------------------- loading


def _load(name: str) -> dict:
    with open(_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def clear_cache() -> None:
    """Drop cached files (e.g. after editing the JSON in a running process)."""
    for fn in (retailers, flights, disputes, bank_fees, bills, settlements, merchant_sites, auto_renewal):
        fn.cache_clear()


__all__ = [
    "MerchantSite", "merchant_site", "merchant_sites", "on_domains",
    "StateAutoRenewal", "auto_renewal", "auto_renewal_for",
    "Airline", "BankFee", "BillProvider", "DisputeRule", "Retailer", "Settlement",
    "airline_for", "bank_fee_for", "bank_fees", "bill_provider_for", "bills", "clear_cache",
    "delay_compensation", "dispute_deadline", "dispute_rule", "disputes", "fee_kind_for", "flights",
    "is_stale", "match_strength", "open_settlements", "retailer_for", "retailers", "settlements",
    "settlements_matching",
]
