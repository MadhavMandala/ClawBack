"""Seeded demo user: six months of bank charges plus the emails that go with them.

All data is made up. Prices are illustrative, not quotes of any company's current price.
Each subscription is there to exercise one flag:

- Netflix: price went up (price_increase)
- Hulu: a "we miss you" email (unused)
- DoorDash DashPass: one order a month, saving less than the fee (membership_losing_money)
- iCloud+ and Google One: two cloud storage plans (overlap); iCloud+ appears only as APPLE.COM/BILL
- Spotify: weekly listening emails (in use, no flag)
- Adobe, ChatGPT Plus: no usage evidence at all (needs a check-in)
- Super Duolingo: free trial about to convert, email only (trial_ending)
- Grocery, gas and one-off shopping: noise that must NOT be detected as subscriptions
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from .models import Email, Transaction


def _monthly_dates(today: date, day: int, months: int = 6) -> list[date]:
    out = []
    y, m = today.year, today.month
    for _ in range(months + 1):
        try:
            d = date(y, m, day)
        except ValueError:
            d = date(y, m, 28)
        if d <= today:
            out.append(d)
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(out)[-months:]


def _dt(d: date, hour: int = 9) -> datetime:
    return datetime.combine(d, time(hour, 0), tzinfo=timezone.utc)


def transactions(today: date) -> list[Transaction]:
    tx: list[Transaction] = []

    def add(d: date, desc: str, amount: float) -> None:
        tx.append(Transaction(id=f"t{len(tx):04d}", date=d, description=desc, amount=amount))

    for i, d in enumerate(_monthly_dates(today, 5)):
        add(d, "NETFLIX.COM 866-579-7172 CA", 15.49 if i < 4 else 17.99)
    for d in _monthly_dates(today, 12):
        add(d, "SPOTIFY USA 877-778-1161", 11.99)
    for d in _monthly_dates(today, 20):
        add(d, "HULU 877-8244858 CA", 9.99)
    for d in _monthly_dates(today, 2):
        add(d, "DOORDASH DASHPASS SAN FRANCISCO", 9.99)
    for d in _monthly_dates(today, 15):
        add(d, "APPLE.COM/BILL 866-712-7753 CA", 2.99)
    for d in _monthly_dates(today, 8):
        add(d, "GOOGLE *Google One g.co/helppay#", 9.99)
    for d in _monthly_dates(today, 22):
        add(d, "ADOBE *CREATIVE CLD 408-536-6000", 59.99)
    for d in _monthly_dates(today, 3):
        add(d, "OPENAI *CHATGPT SUBSCR SAN FRANCISCO", 20.00)

    # Noise: varying amounts, not subscriptions.
    for k in range(26):
        add(today - timedelta(days=7 * k + 1), "KROGER #0412 ATLANTA GA", round(48 + (k * 13.7) % 61, 2))
    for k in range(12):
        add(today - timedelta(days=15 * k + 4), "SHELL OIL 57444 ATLANTA", round(31 + (k * 7.3) % 22, 2))
    for k, d in enumerate(_monthly_dates(today, 17)):
        add(d, "DOORDASH*CHIPOTLE SAN FRANCISCO", round(22.4 + k * 2.15, 2))
    add(today - timedelta(days=40), "BEST BUY 00012345 ATLANTA", 179.99)
    add(today - timedelta(days=95), "AMAZON MKTPL*2K4LP0", 34.18)
    add(today - timedelta(days=12), "AMAZON MKTPL*9Q1ZZ3", 12.49)

    return sorted(tx, key=lambda t: t.date)


def emails(today: date) -> list[Email]:
    out: list[Email] = []

    def add(d: date, sender: str, subject: str, body: str) -> None:
        out.append(Email(id=f"e{len(out):04d}", received_at=_dt(d), sender=sender, subject=subject, body_text=body))

    for k, d in enumerate(_monthly_dates(today, 17)):
        add(
            d,
            "no-reply@doordash.com",
            "Order confirmed: Chipotle",
            f"Thanks for your order! Subtotal ${20.10 + k * 2.15:.2f}. Delivery fee $0.00. "
            "DashPass saved you $2.99 on this order.",
        )
    add(today - timedelta(days=18), "hello@hulumail.com", "We miss you! See what's new on Hulu",
        "It's been a while since you watched. Come back and catch up on what's new.")
    for k in range(4):
        add(today - timedelta(days=4 + 7 * k), "no-reply@spotify.com", "Your top songs this week",
            "You listened to 9 hours of music this week. Here are your top songs.")
    netflix_change = _monthly_dates(today, 5)[4] - timedelta(days=30)
    add(netflix_change, "info@account.netflix.com", "We're updating your Netflix price",
        "Starting with your next billing date, your monthly price will change from $15.49 to $17.99.")
    add(today - timedelta(days=10), "no_reply@email.apple.com", "Your receipt from Apple",
        "Apple Account receipt. iCloud+ with 200 GB (Monthly) $2.99. Billed to Visa.")
    add(today - timedelta(days=2), "hello@duolingo.com", "Your Super Duolingo free trial ends in 3 days",
        "Your free trial ends in 3 days. After that you'll be charged $12.99/month unless you cancel.")

    # Noise the triage step should drop.
    add(today - timedelta(days=1), "noreply@medium.com", "Your daily digest", "Stories picked for you.")
    add(today - timedelta(days=3), "notifications@github.com", "[repo] New issue opened", "Someone opened an issue.")
    add(today - timedelta(days=6), "receipts@kroger.com", "Your Kroger receipt", "Total $61.20. Thanks for shopping.")
    add(today - timedelta(days=9), "team@linkedin.com", "You appeared in 12 searches", "See who's looking.")

    return sorted(out, key=lambda e: e.received_at)
