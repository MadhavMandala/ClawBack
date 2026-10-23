"""Domain models shared by the pipeline and the API."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    id: str
    date: date
    description: str  # raw bank description, e.g. "NETFLIX.COM 866-579-7172 CA"
    amount: float  # positive = money out
    source: str = "demo"  # demo | plaid | statement
    category: str | None = None  # Plaid's personal finance category (detailed, e.g. LOAN_PAYMENTS_CAR_PAYMENT)


class Attachment(BaseModel):
    """An email attachment's metadata. The file itself is downloaded only when needed and kept in memory only."""

    id: str
    filename: str = ""
    content_type: str = ""
    size: int = 0  # bytes, as the provider reports it
    inline: bool = False  # inline images are usually logos, not receipts


class Email(BaseModel):
    id: str
    received_at: datetime
    sender: str  # address, e.g. "no-reply@doordash.com"
    subject: str
    body_text: str
    source: str = "demo"  # demo, or the Nylas provider it came from: google | microsoft | yahoo | icloud | imap | ews
    attachments: list[Attachment] = Field(default_factory=list)
    # Prompt-injection signals noticed while the body was turned into text, such as instructions in hidden HTML.
    # Short labels only, never body text (pipeline/guard.py reads them).
    screen: list[str] = Field(default_factory=list)


class Cadence(str, Enum):
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


class PriceChange(BaseModel):
    old_amount: float
    new_amount: float
    changed_on: date


class UsageSignal(BaseModel):
    kind: str  # receipt | inactivity_email | engagement_email | checkin
    on: date
    detail: str
    weight: float  # +1 = clearly used, -1 = clearly unused


class UsageSummary(BaseModel):
    level: str = "unknown"  # none | low | normal | unknown
    evidence: list[str] = Field(default_factory=list)
    needs_checkin: bool = False
    strength: str = ""  # "strong" when the check-in history alone settles it (two "no" answers in a row)
    next_checkin: date | None = None  # when ClawBack asks "used it?" again (later after three "yes" in a row)


class MembershipValue(BaseModel):
    period_fee: float
    uses: int
    savings: float  # what the receipts say it saved, or the generous end of an estimate
    net: float  # savings - fee; negative means the membership is losing money
    # losing_money | paying_off | too_close | not_enough_receipts. Only losing_money raises a flag.
    verdict: str = "losing_money"
    basis: str = "stated"  # stated (the receipt says what it saved) | estimated (from published fees) | none
    savings_low: float | None = None  # cautious end of an estimate
    note: str = ""
    source_url: str | None = None  # where the non-member fees used in an estimate come from


class Flag(BaseModel):
    # unused | price_increase | overlap | membership_losing_money | trial_ending | unknown_usage
    # bills: bill_increase | promo_ending | negotiable
    kind: str
    severity: str  # high | medium | info
    message: str
    monthly_savings: float = 0.0


class Subscription(BaseModel):
    id: str
    merchant: str
    category: str
    kind: str = "subscription"  # subscription | bill
    bill_category: str | None = None  # internet | mobile | insurance | utility | gym (bills only)
    cadence: Cadence | None = None
    amount: float | None = None  # latest charge
    monthly_cost: float = 0.0
    first_seen: date | None = None
    last_charged: date | None = None
    next_expected: date | None = None
    charge_count: int = 0
    price_change: PriceChange | None = None
    usage: UsageSummary = Field(default_factory=UsageSummary)
    value: MembershipValue | None = None
    flags: list[Flag] = Field(default_factory=list)
    status: str = "active"  # active | trial | kept | cancel_pending | cancelled
    detected_from: list[str] = Field(default_factory=list)  # bank | email
    billed_by: str | None = None  # apple | google_play when the store bills it (cancel there)
    matched_from: str | None = None  # how it was named: the store receipt it matched, or the naming step
    cancellation: Cancellation | None = None  # set once the user starts cancelling
    series_key: str | None = Field(None, exclude=True)  # how its bank charges are grouped (pipeline/recurring.py)


class Cancellation(BaseModel):
    """A subscription the user started cancelling, and what the bank shows since (pipeline/confirm.py)."""

    subscription_id: str
    merchant: str
    started_on: date
    series_key: str  # how its charges are grouped (recurring.series_key), to spot a charge after cancelling
    amount: float | None = None
    monthly_cost: float = 0.0
    cadence: Cadence | None = None
    category: str = "unknown"
    kind: str = "subscription"
    billed_by: str | None = None
    last_charge: date | None = None  # last charge on or before the day cancelling started
    first_due: date | None = None  # no charge yet (a free trial): when the first one was due
    expected_by: date | None = None  # next expected charge plus a grace period
    status: str = "pending"  # pending | charged_again | confirmed
    charged_again_on: date | None = None
    charged_again_amount: float | None = None
    confirmed_on: date | None = None
    skipped_charges: int = 0  # expected charges that didn't come
    note: str = ""


class RefundWatch(BaseModel):
    """A finding the user marked done: the credit ClawBack looks for in the bank (pipeline/confirm.py).

    Kept apart from the finding itself, because detectors rebuild findings each run and drop them once a deadline
    passes, while the refund can arrive later."""

    finding_id: str
    kind: str
    category: str
    merchant: str
    title: str
    amount: float
    currency: str = "USD"
    got_back: float = 0.0  # what the user said came back (self-reported)
    done_on: date
    charged_on: date | None = None  # the original charge or purchase; a credit must come after it
    match_words: list[str] = Field(default_factory=list)  # words the credit's bank description must contain
    status: str = "waiting"  # waiting | confirmed
    confirmed_on: date | None = None
    confirmed_amount: float | None = None
    confirmed_from: str | None = None  # the bank credit that matched
    confirmed_tx: str | None = None  # its transaction id (each credit confirms one finding)


class RecoveryEvent(BaseModel):
    """One dated line in the history of money recovered (GET /api/recovered)."""

    id: str
    kind: str  # cancelled_subscription | refund | self_reported
    status: str  # confirmed | self_reported
    on: date
    merchant: str
    amount: float = 0.0  # one-time money back; for a cancellation, the charges that didn't come so far
    monthly: float = 0.0  # cancellations: what it no longer costs each month
    note: str = ""
    subscription_id: str | None = None
    finding_id: str | None = None


class StoreItem(BaseModel):
    name: str  # the app or service, as the receipt names it
    plan: str | None = None  # "Calm Premium (Monthly)"
    price: float | None = None  # before tax
    merchant: str | None = None  # our merchant list's name, when it is one we know


class StoreReceipt(BaseModel):
    """What an Apple or Google Play receipt says, read by code (or Lightning when the format is new). No body text."""

    email_id: str
    store: str  # apple | google_play
    received: date
    kind: str = "receipt"  # receipt | notice (a subscription confirmation or renewal notice: a price, no charge)
    order_id: str | None = None
    items: list[StoreItem] = Field(default_factory=list)
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    read_by: str = "code"  # code | the model id


# --- One-time money: findings and the action prepared for each ---------------------------------------

class RuleRef(BaseModel):
    """The rule a finding relies on, quoted from backend/clawback/rules data (never from memory)."""

    name: str
    summary: str
    source_url: str


class Finding(BaseModel):
    id: str  # stable hash of the kind + key facts, so dismiss / done survive re-runs
    category: str  # charges | refunds | settlements
    kind: str  # duplicate_charge | bank_fee | price_drop | flight_refund | flight_compensation | settlement
    merchant: str
    title: str
    message: str
    amount: float = 0.0
    currency: str = "USD"  # USD | EUR | GBP
    amount_note: str | None = None
    deadline: date | None = None
    deadline_label: str | None = None
    confidence: str = "medium"  # high | medium | low
    evidence: list[str] = Field(default_factory=list)
    rule: RuleRef | None = None
    status: str = "open"  # open | dismissed | done
    found_on: date
    # Done findings: the bank credit that confirmed the money came back (pipeline/confirm.py).
    confirmed_amount: float | None = None
    confirmed_on: date | None = None
    confirmed_from: str | None = None
    # Facts the action builder needs (order number, flight, fare...). Not sent to the frontend.
    details: dict = Field(default_factory=dict, exclude=True)


class ActionLink(BaseModel):
    label: str
    url: str
    verified: bool = False


class ActionMessage(BaseModel):
    to: str | None = None
    subject: str | None = None
    body: str
    # Who wrote this message and the talking points next to it: the model id (Nemotron 3 Ultra), or "template".
    written_by: str = "template"


class ActionPrep(BaseModel):
    """What ClawBack prepares for the user to send or say. It never sends, files or calls anything itself."""

    title: str
    summary: str
    channel: str  # email | chat | phone | form | dispute | in_person
    steps: list[str] = Field(default_factory=list)
    links: list[ActionLink] = Field(default_factory=list)
    message: ActionMessage | None = None
    script: list[str] | None = None
    deadline: date | None = None
    missing: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    at: datetime
    stage: str
    engine: str  # model ID, "code", "tavily", or "rules"
    status: str  # ok | missing | error | fallback | skipped (daily model limit reached)
    tier: str = ""  # fast | fast_fallback | mid | reason | vision ("" for non-model steps)
    ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    note: str = ""


class Fact(BaseModel):
    """What one email says about a subscription. Dates here are computed by code, never by a model."""

    email_id: str
    received: date
    kind: str  # delivery_order | inactivity | engagement | price_change | trial | store_receipt | other
    merchant: str | None = None
    amount: float | None = None
    saved_amount: float | None = None
    old_price: float | None = None
    new_price: float | None = None
    trial_end: date | None = None


Subscription.model_rebuild()  # it refers to Cancellation, defined below it
