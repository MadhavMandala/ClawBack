"""Seeded demo user: six months of bank charges plus the emails that go with them.

All data is made up. Prices are illustrative, not quotes of any company's current price.
Each subscription is there to exercise one flag:

- Netflix: price went up (price_increase) and a "we miss you" email (unused): the streaming workflow, since Netflix
  has a direct cancel page (netflix.com/cancelplan)
- Hulu: an ordinary subscription with no signal either way
- DoorDash DashPass: one order a month, saving less than the fee (membership_losing_money)
- iCloud+ and Google One: two cloud storage plans (overlap); iCloud+ appears only as APPLE.COM/BILL and is named
  from an Apple receipt with no tax ($2.99)
- Calm, billed by Apple: $14.99 plus $1.05 tax ($16.04 APPLE.COM/BILL), named from its Apple receipts. The demo user
  started cancelling it after the fourth charge (decisions()); no charge has come since, so the cancellation is
  confirmed: it leaves the monthly total and shows in the history of money recovered
- Spotify: weekly listening emails (in use, no flag)
- Adobe, ChatGPT Plus: no usage evidence at all (needs a check-in)
- Super Duolingo: free trial about to convert, email only (trial_ending)
- Grocery, gas and one-off shopping: noise that must NOT be detected as subscriptions

Bills (matched to providers in rules/bills.json):
- Xfinity internet: $55 for 3 months, then $85 after a "promotional rate ends" email (bill_increase, high)
- Verizon Wireless: a steady $80 (negotiable)
- GEICO auto: $102, then $121 after a renewal email (+18.6%, bill_increase, high)
- PG&E electric: swings between $60 and $140 (a variable bill: no flag, "looks fine")

One-time money (findings):
- Staples: the same $129.99 charged twice on one day, one order email (duplicate_charge, high)
- Bank fees: overdraft $35.00, foreign transaction $4.17, out-of-network ATM $3.50 (bank_fee)
- Best Buy: AirPods Pro 2 bought 6 days ago at $249.00 (its regular price). With keys, today's price comes from a
  live bestbuy.com check (price_drop when lower; a price_watch entry when not); without, a simulated $189.99 that
  the finding's title calls simulated
- Orangetheory: $169.00 a month, and a preloaded Google Maps Timeline whose gym visits stop nine weeks ago (unused)
- Walmart: an air fryer whose price also dropped, NOT flagged because Walmart doesn't price-adjust
- United: a booking ($412.40) and then a cancellation offering a travel credit (flight_refund, $412.40)
- Settlements: the Kroger, Amazon and Apple charges / emails above match open settlements in
  rules/settlements.json. settlement_story() adds one dated return email inside the class period of a broad,
  nationwide one (today Amazon's return-policy settlement), so the demo always shows a match that fits.

PRICE_CHECKS is the simulated current-price table for demo mode (tools/prices.py says so in evidence and trace).
refund_credit() is the simulated bank for demo mode: when the user marks a finding done, the demo bank posts the
refund as a credit dated that day, so the next sync confirms it (pipeline/confirm.py). Its description says
"DEMO" so it reads as simulated.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from .models import Email, Finding, Transaction

# Simulated "current price" checks for demo mode: (store, words in the item name) -> price now.
PRICE_CHECKS: dict[tuple[str, str], float] = {
    # Used only when the live bestbuy.com check can't run; the finding then says "simulated" in its title.
    ("best buy", "airpods pro 2"): 189.99,
    ("walmart", "ninja air fryer"): 69.00,
}


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

    # Bills.
    for i, d in enumerate(_monthly_dates(today, 9)):
        add(d, "COMCAST XFINITY 800-266-2278", 55.00 if i < 3 else 85.00)
    for d in _monthly_dates(today, 14):
        add(d, "VERIZON WIRELESS PAYMENTS", 80.00)
    for i, d in enumerate(_monthly_dates(today, 21)):
        add(d, "GEICO *AUTO 800-841-3000", 102.00 if i < 4 else 121.00)
    for d, amount in zip(_monthly_dates(today, 25), (62.40, 88.15, 139.70, 121.05, 74.30, 60.12)):
        add(d, "PGANDE WEB ONLINE", amount)

    # One-time money.
    add(today - timedelta(days=9), "STAPLES 00123 ATLANTA", 129.99)
    add(today - timedelta(days=9), "STAPLES 00123 ATLANTA", 129.99)  # charged twice for one order
    add(today - timedelta(days=17), "OVERDRAFT ITEM FEE", 35.00)
    add(today - timedelta(days=23), "FOREIGN TRANSACTION FEE", 4.17)
    add(today - timedelta(days=11), "NON-NETWORK ATM FEE", 3.50)
    add(today - timedelta(days=6), "BEST BUY 00012345 ATLANTA", 249.00)  # AirPods Pro 2: the price-drop workflow
    add(today - timedelta(days=8), "WALMART.COM 8009256278", 89.00)
    add(today - timedelta(days=40), "UNITED 0162345678901", 412.40)

    # Noise: varying amounts, not subscriptions.
    for k in range(26):
        add(today - timedelta(days=7 * k + 1), "KROGER #0412 ATLANTA GA", round(48 + (k * 13.7) % 61, 2))
    for k in range(12):
        add(today - timedelta(days=15 * k + 4), "SHELL OIL 57444 ATLANTA", round(31 + (k * 7.3) % 22, 2))
    for k, d in enumerate(_monthly_dates(today, 17)):
        add(d, "DOORDASH*CHIPOTLE SAN FRANCISCO", round(22.4 + k * 2.15, 2))
    add(today - timedelta(days=40), "HOME DEPOT 0456 ATLANTA", 179.99)
    add(today - timedelta(days=95), "AMAZON MKTPL*2K4LP0", 34.18)
    add(today - timedelta(days=12), "AMAZON MKTPL*9Q1ZZ3", 12.49)

    # Calm through Apple: $14.99 + $1.05 tax, four months, then cancelled (decisions()). Added last: ids stay stable.
    for d in calm_dates(today):
        add(d, "APPLE.COM/BILL 866-712-7753 CA", 16.04)

    # Orangetheory: $169.00 on the 4th, every month. The Google Maps visits (gym_visits) stop eight weeks ago.
    for d in _monthly_dates(today, 4):
        add(d, "ORANGETHEORY FITNESS EDISON NJ", 169.00)

    return sorted(tx, key=lambda t: t.date)


GYM_STOPPED_DAYS = 63  # the demo user's last gym visit, nine weeks before today (outside the 60-day window)


def gym_visits(today: date) -> dict[str, list[date]]:
    """The demo's made-up Google Maps Timeline, already reduced to gym visits (as an upload would be): two or three a
    week for four months, then none for the last nine weeks."""
    from .gyms import demo_gym

    last = today - timedelta(days=GYM_STOPPED_DAYS)
    days, d = [], last - timedelta(days=120)
    while d <= last:
        if d.weekday() in (0, 2, 4) and (d.toordinal() % 7 != 4):  # Mon/Wed/Fri, skipping some weeks' Friday
            days.append(d)
        d += timedelta(days=1)
    if days[-1] != last:
        days.append(last)
    return {demo_gym()["id"]: days}


def calm_dates(today: date) -> list[date]:
    """The demo's four Calm charges: the 11th of the month, stopping two months before today's."""
    return _monthly_dates(today, 11)[:4]


def decisions(u, today: date) -> None:
    """What the demo user already did before today: started cancelling Calm nine days after its last charge."""
    u.cancel_pending["calm"] = calm_dates(today)[-1] + timedelta(days=9)


def refund_credit(f: Finding, today: date) -> Transaction | None:
    """The simulated demo bank: the refund for a finding marked done, as a credit dated today. None for
    settlements (they pay months later) and for EUR / GBP amounts."""
    d = f.details or {}
    if f.currency != "USD" or f.amount <= 0 or f.kind == "settlement":
        return None
    if f.kind == "duplicate_charge":
        desc = f"{d.get('description') or f.merchant.upper()} DEMO REFUND"
    elif f.kind == "bank_fee":
        desc = f"DEMO {d.get('description') or 'FEE'} REFUND"
    elif f.kind == "price_drop":
        desc = f"{(d.get('store') or f.merchant).upper()} DEMO PRICE ADJUSTMENT"
    else:
        desc = f"{(d.get('airline') or f.merchant).upper()} DEMO REFUND"
    return Transaction(id=f"demo-credit-{f.id}", date=today, description=desc, amount=-round(f.amount, 2))


def apple_receipt(on: date, order_id: str, section: str, app: str, plan: str, price: float, tax: float) -> str:
    """An Apple receipt as text, in the layout Apple has used since 2025 once its HTML is stripped: the header
    fields, one block per item (app, plan, renewal date, price), then Subtotal, Tax and the card line that carries
    the total charged."""
    renews = _monthly_dates(on + timedelta(days=40), on.day, 1)[0]
    document = sum(ord(c) * 7919 ** i for i, c in enumerate(order_id)) % 10**12
    return "\n".join([
        "Receipt",
        f"{on:%B} {on.day}, {on.year}",
        f"Order ID: {order_id}",
        f"Document: {document:012d}",
        "Apple Account: alex.demo@example.com",
        "",
        section,
        app,
        plan,
        f"Renews {renews:%B} {renews.day}, {renews.year}",
        f"${price:.2f}",
        "",
        "Billing and Payment",
        "Alex Demo",
        "Atlanta, GA 30301",
        "USA",
        f"Subtotal ${price:.2f}",
        f"Tax ${tax:.2f}",
        f"Visa •••• 4242 ${price + tax:.2f}",
        "",
        "You can turn off renewal receipts to stop getting emails each time your subscriptions renew.",
        "Turn Off Renewal Receipt Emails",
        "Manage Subscriptions › Purchase History › Report a Problem › Visit Apple Support ›",
    ])


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
    add(today - timedelta(days=18), "info@mailer.netflix.com", "We miss you! See what's new on Netflix",
        "It's been a while since you watched. Come back and catch up on what's new.")
    for k in range(4):
        add(today - timedelta(days=4 + 7 * k), "no-reply@spotify.com", "Your top songs this week",
            "You listened to 9 hours of music this week. Here are your top songs.")
    netflix_change = _monthly_dates(today, 5)[4] - timedelta(days=30)
    add(netflix_change, "info@account.netflix.com", "We're updating your Netflix price",
        "Starting with your next billing date, your monthly price will change from $15.49 to $17.99.")
    # Apple emails the receipt the day before the charge lands, like Calm's below. Tied to the latest iCloud+ charge
    # (the 15th), so the receipt and the charge always match, whatever day the demo is built.
    icloud_receipt = _monthly_dates(today, 15)[-1] - timedelta(days=1)
    add(icloud_receipt, "no_reply@email.apple.com", "Your receipt from Apple.",
        apple_receipt(icloud_receipt, "MT8Q2KX7LD", "iCloud", "iCloud+", "iCloud+ with 200 GB (Monthly)",
                      2.99, 0.00))
    for k, d in enumerate(calm_dates(today)):
        receipt_day = d - timedelta(days=1)
        add(receipt_day, "no_reply@email.apple.com", "Your receipt from Apple.",
            apple_receipt(receipt_day, f"MT4KX2P9{k}Z", "App Store", "Calm: Sleep & Meditation",
                          "Calm Premium (Monthly)", 14.99, 1.05))
    add(today - timedelta(days=2), "hello@duolingo.com", "Your Super Duolingo free trial ends in 3 days",
        "Your free trial ends in 3 days. After that you'll be charged $12.99/month unless you cancel.")

    # Bills.
    xfinity = _monthly_dates(today, 9)
    add(xfinity[3] - timedelta(days=15), "online.communications@alerts.comcast.net",
        "Your promotional rate is ending soon",
        f"Your promotional rate of $55.00/month ends on {xfinity[3] - timedelta(days=1):%B %d, %Y}. "
        "Starting with your next bill, your monthly rate for Xfinity Internet will be $85.00/month.")
    geico = _monthly_dates(today, 21)
    add(geico[4] - timedelta(days=20), "geico@email.geico.com", "Your GEICO policy renewal",
        f"Your auto policy renews on {geico[4]:%B %d, %Y}. Your new monthly payment will be $121.00 (was $102.00).")

    # One-time money.
    add(today - timedelta(days=9), "orders@staples.com", "Thanks for your Staples order",
        "Order number: 7712345678. Item: Logitech MX Master 3S Wireless Mouse, $129.99. "
        "Order total: $129.99. We'll email you when it ships.")
    add(today - timedelta(days=6), "BestBuyInfo@emailinfo.bestbuy.com", "Thanks for your order",
        "Order number: BBY01-806512345678. Item: Apple AirPods Pro 2, $249.00. "
        "Order total: $249.00. We'll email you when it ships.")
    add(today - timedelta(days=8), "help@walmart.com", "Your Walmart order is confirmed",
        "Order #200011122233. Item: Ninja Air Fryer AF101, $89.00. Order total: $89.00.")
    flight_day = today + timedelta(days=12)
    when = f"{flight_day:%b} {flight_day.day}, {flight_day.year}"
    add(today - timedelta(days=40), "unitedairlines@united.com", "Your United flight confirmation - K7Q2PL",
        f"Confirmation number: K7Q2PL. Flight UA 1532, San Francisco (SFO) to Chicago (ORD), {when} 8:05 AM. "
        "Total fare: $412.40, charged to your Visa ending in 4242.")
    add(today - timedelta(days=4), "notifications@united.com", "Your flight UA 1532 has been cancelled",
        f"We're sorry. Your flight UA 1532 from SFO to ORD on {when} has been cancelled. "
        "We've added a travel credit of $412.40 to your MileagePlus account for future travel.")

    # Noise the triage step should drop.
    add(today - timedelta(days=1), "noreply@medium.com", "Your daily digest", "Stories picked for you.")
    add(today - timedelta(days=3), "notifications@github.com", "[repo] New issue opened", "Someone opened an issue.")
    add(today - timedelta(days=6), "receipts@kroger.com", "Your Kroger receipt", "Total $61.20. Thanks for shopping.")
    add(today - timedelta(days=9), "team@linkedin.com", "You appeared in 12 searches", "See who's looking.")

    return sorted(out, key=lambda e: e.received_at)


# The demo's settlement must still be open on the last day of judging (Dec 15). The latest suitable settlements close
# Dec 21, so the story needs only a few days of headroom, not a month.
STORY_MIN_DAYS = 5


def settlement_story(today: date, transactions: list[Transaction], emails: list[Email], book) -> list[Email]:
    """One dated return email for a featured settlement, so the demo shows a match that fits who qualifies.

    Picks a verified, open, nationwide settlement (not limited to a state or venue) with its deadline at least 30
    days away, preferring one the demo data already touches but only outside its class period (today: Amazon's
    return-policy settlement), and adds a return email from its domain dated inside the class period.
    """
    from .findings.settlements import limited

    def touches(s: dict) -> list[date]:
        hits = [t.date for t in transactions if s in book.settlements_matching(t.description, today)]
        return hits + [e.received_at.date() for e in emails
                       if s in book.settlements_matching(f"{e.sender} {e.subject}", today)]

    def inside(s: dict, d: date) -> bool:
        return s["class_start"] <= d <= s["class_end"]

    pool = [s for s in book.settlements
            if not limited(s) and s["claim_deadline"] and s["claim_deadline"] >= today + timedelta(days=STORY_MIN_DAYS)
            and s["class_start"] and s["class_end"] and s["class_start"] < today
            and any(m == m.lower() and "." in m for m in s["match"])]
    pool.sort(key=lambda s: (not touches(s), any(inside(s, d) for d in touches(s)), s["claim_deadline"]))
    if not pool:
        return []
    s = pool[0]
    domain = next(m for m in s["match"] if m == m.lower() and "." in m)
    on = max(s["class_start"], min(s["class_end"], today) - timedelta(days=120))
    words = [w.lower() for w in s.get("evidence_words") or []]
    if "return" in words:  # Amazon's return-policy class: the purchase shows up as a return request
        subject = "Your return request for order 112-4839201"
        body = "We've received your return request. Your refund will be issued when we receive the item."
    else:  # an order receipt that names the product or service the class covers, when the row lists one
        what = f"{words[0]} " if words else ""
        subject = f"Your {what}order receipt 112-4839201"
        body = f"Thanks for your {what}order. This email is your receipt."
    return [Email(id="e-settlement", received_at=_dt(on), sender=f"orders@{domain}", subject=subject, body_text=body)]
