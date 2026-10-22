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


class Email(BaseModel):
    id: str
    received_at: datetime
    sender: str  # address, e.g. "no-reply@doordash.com"
    subject: str
    body_text: str
    source: str = "demo"  # demo | gmail | outlook | forward


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
    kind: str  # unused | price_increase | overlap | membership_losing_money | trial_ending | unknown_usage
    severity: str  # high | medium | info
    message: str
    monthly_savings: float = 0.0


class Subscription(BaseModel):
    id: str
    merchant: str
    category: str
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


class TraceStep(BaseModel):
    at: datetime
    stage: str
    engine: str  # model ID, "code", "tavily", or "rules"
    status: str  # ok | missing | error
    ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    note: str = ""
