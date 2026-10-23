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


class MembershipValue(BaseModel):
    period_fee: float
    uses: int
    savings: float
    net: float  # savings - fee; negative means the membership is losing money


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
