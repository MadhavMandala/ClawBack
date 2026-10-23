"""App-store resolution: APPLE.COM/BILL and GOOGLE * charges named from receipt emails.

The fixtures follow the formats seen in real receipts (2022-2025): Apple's layout since 2025 (header fields, an
item block, Subtotal / Tax, then the card line carrying the total), Apple's older layout (TOTAL at the top),
Apple's "Subscription Confirmation" email, and Google Play's "Your Google Play Order Receipt from <date>". Names,
order numbers and amounts are made up.
"""

import json
from datetime import date, datetime, timedelta, timezone

from clawback.models import Email, Transaction
from clawback.pipeline import store_billing
from clawback.pipeline.recurring import detect_series
from clawback.pipeline.store_billing import parse_receipt, read_receipts, resolve, store_of
from clawback.store import store

TODAY = date(2026, 10, 22)
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"


def email(eid: str, on: date, body: str, subject: str = "Your receipt from Apple.",
          sender: str = "Apple <no_reply@email.apple.com>") -> Email:
    return Email(id=eid, received_at=datetime(on.year, on.month, on.day, 8, tzinfo=timezone.utc), sender=sender,
                 subject=subject, body_text=body)


def apple_new(on: date, items: list[tuple[str, str, float]], tax: float, section: str = "App Store",
              order: str = "MT8KQ2ZX4L") -> str:
    """Apple's layout since 2025, as text once the HTML is stripped."""
    lines = ["Receipt", f"{on:%B} {on.day}, {on.year}", f"Order ID: {order}", "Document: 284019573316",
             "Apple Account: jane.doe@icloud.com", "", section]
    for app, plan, price in items:
        lines += [app, plan, f"Renews {on + timedelta(days=30):%B} {(on + timedelta(days=30)).day}, {on.year}",
                  "Jane's iPhone", f"${price:.2f}"]
    subtotal = sum(p for _, _, p in items)
    lines += ["", "Billing and Payment", "Jane Doe", "123 Main St", "Austin, TX 78701", "USA",
              f"Subtotal ${subtotal:.2f}", f"Tax ${tax:.2f}", f"Visa •••• 1234 ${subtotal + tax:.2f}",
              "", "You can turn off renewal receipts to stop getting emails each time your subscriptions renew.",
              "Turn Off Renewal Receipt Emails", "Manage Subscriptions › Purchase History › Report a Problem ›"]
    return "\n".join(lines)


def apple_old(on: date, app: str, plan: str, price: float, tax: float) -> str:
    """Apple's older layout: labels in capitals and TOTAL near the top as well as at the bottom."""
    return "\n".join([
        "APPLE ID", "jane.doe@icloud.com", "BILLED TO", "Visa .... 0002", "Jane Doe", "123 Main St",
        f"TOTAL ${price + tax:.2f}", "DATE", f"{on:%b} {on.day:02d}, {on.year}", "ORDER ID", "MT2QW7ZP4K",
        "DOCUMENT NO.", "173829102938", "App Store", app, plan,
        f"Monthly Renews {(on + timedelta(days=30)):%b} {(on + timedelta(days=30)).day}, {on.year}", "Report a Problem",
        f"${price:.2f}", f"Subtotal ${price:.2f}", f"Tax ${tax:.2f}", f"TOTAL ${price + tax:.2f}",
    ])


def google(on: date, product: str, app_title: str, seller: str, price: float, tax: float) -> str:
    return "\n".join([
        "Thank you",
        f"Your subscription from {seller} on Google Play continues and you've been charged. Manage your subscriptions",
        "Order number: GPA.3391-2045-7781-60234..3",
        f"Order date: {on:%b} {on.day}, {on.year} 9:14:02 AM CDT",
        "Your account: jane.doe@gmail.com",
        "Item Price",
        f"{product} ({app_title}) ${price:.2f}/month",
        "Auto-renewing subscription",
        f"State sales tax: ${tax:.2f}",
        f"Total: ${price + tax:.2f}/month",
        "Payment method:",
        "Visa-1234",
        "By subscribing, you authorize us to charge you the subscription cost (as described above) automatically.",
        "© 2026 Google | All Rights Reserved.",
    ])


def monthly(day: int, amount: float, n: int = 4, desc: str = "APPLE.COM/BILL 866-712-7753 CA", prefix: str = "t"):
    """The last n monthly charges on that day of the month, oldest first."""
    from clawback.demo_data import _monthly_dates

    return [Transaction(id=f"{prefix}{day}-{k}", date=d, description=desc, amount=amount)
            for k, d in enumerate(_monthly_dates(TODAY, day, n))]


def named(transactions, emails, user="sb"):
    store.reset(user)
    subs, series = detect_series(transactions, TODAY)
    receipts = read_receipts(user, emails)
    return {s.merchant: s for s in resolve(subs, series, receipts)}, series


# --- Reading receipts ---------------------------------------------------------------------------------

def test_apple_new_layout_single_item_with_tax():
    r = parse_receipt(email("a", TODAY, apple_new(TODAY, [("Calm: Sleep & Meditation", "Calm Premium (Monthly)", 14.99)],
                                                  1.24)), "apple")
    assert (r.subtotal, r.tax, r.total, r.order_id) == (14.99, 1.24, 16.23, "MT8KQ2ZX4L")
    [item] = r.items
    assert (item.name, item.plan, item.price, item.merchant) == ("Calm: Sleep & Meditation", "Calm Premium (Monthly)",
                                                                 14.99, "Calm")


def test_apple_old_layout():
    r = parse_receipt(email("o", TODAY, apple_old(TODAY, "Headspace: Sleep & Meditation", "Headspace (Monthly)",
                                                  12.99, 1.07)), "apple")
    assert r.total == 14.06 and r.tax == 1.07
    [item] = r.items
    assert item.price == 12.99 and item.merchant == "Headspace"


def test_apple_bundle_lists_every_item():
    body = apple_new(TODAY, [("Duolingo: Language Lessons", "Super Duolingo (Monthly)", 12.99),
                             ("Strava: Run, Bike, Hike", "Strava Subscription (Monthly)", 11.99)], 2.06)
    r = parse_receipt(email("b", TODAY, body), "apple")
    assert [(i.merchant, i.price) for i in r.items] == [("Super Duolingo", 12.99), ("Strava", 11.99)]
    assert r.total == 27.04


def test_google_play_receipt():
    body = google(TODAY, "Super Duolingo - Monthly", "Duolingo: Language Lessons", "Duolingo", 12.99, 1.07)
    e = email("g", TODAY, body, subject=f"Your Google Play Order Receipt from {TODAY:%b} {TODAY.day}, {TODAY.year}",
              sender="Google Play <googleplay-noreply@google.com>")
    assert store_of(e) == "google_play"
    r = parse_receipt(e, "google_play")
    assert (r.tax, r.total, r.order_id) == (1.07, 14.06, "GPA.3391-2045-7781-60234..3")
    [item] = r.items
    assert (item.name, item.price, item.merchant) == ("Super Duolingo", 12.99, "Super Duolingo")


def test_apple_subscription_confirmation_is_a_notice():
    body = ("Dear Jane,\nThis email confirms your subscription purchase:\nApp  Calm: Sleep & Meditation\n"
            "Subscription  Calm Premium (Annual)\nDate of Purchase  Oct 5, 2026\nRenewal Price  $69.99/year\n"
            "To avoid being charged, you must cancel at least a day before each renewal date.")
    r = parse_receipt(email("c", TODAY, body, subject="Subscription Confirmation"), "apple")
    assert r.kind == "notice" and r.total is None
    [item] = r.items
    assert (item.name, item.plan, item.price, item.merchant) == ("Calm: Sleep & Meditation", "Calm Premium (Annual)",
                                                                 69.99, "Calm")


def test_lookalike_sender_is_not_a_store_receipt():
    fake = email("x", TODAY, apple_new(TODAY, [("Calm", "Calm Premium (Monthly)", 14.99)], 1.0),
                 sender="Apple Support <billing@apple-receipts.example>")
    assert store_of(fake) is None
    assert store_of(email("n", TODAY, "Your order shipped", subject="Your order")) is None  # apple.com, not a receipt


def test_receipts_are_cached_by_email_id():
    e = email("a", TODAY, apple_new(TODAY, [("Calm: Sleep & Meditation", "Calm Premium (Monthly)", 14.99)], 1.24))
    store.reset("cache")
    read_receipts("cache", [e])
    assert "a" in store.user("cache").store_receipts
    assert store.user("cache").store_receipts["a"].read_by == "code"


# --- Matching charges to receipts ---------------------------------------------------------------------

def test_tax_on_top_is_matched_and_says_where_from():
    txs = monthly(10, 16.23)
    receipts = [email(f"r{k}", t.date - timedelta(days=1),
                      apple_new(t.date, [("Calm: Sleep & Meditation", "Calm Premium (Monthly)", 14.99)], 1.24))
                for k, t in enumerate(txs)]
    subs, _ = named(txs, receipts)
    calm = subs["Calm"]
    assert calm.id == "calm" and calm.billed_by == "apple" and calm.detected_from == ["bank", "email"]
    assert calm.category == "wellness" and calm.amount == 16.23
    assert "Apple receipt" in calm.matched_from and "$14.99 plus $1.24 tax" in calm.matched_from
    assert "All 4 charges" in calm.matched_from


def test_tax_band_match_when_the_receipt_has_no_total():
    """A receipt read only partly (the price but no total) still fits by price plus up to 12% tax."""
    txs = monthly(10, 13.94)
    body = "Receipt\nApp Store\nHeadspace: Sleep & Meditation\nHeadspace (Monthly)\n$12.99\n"
    subs, _ = named(txs, [email("r", txs[-1].date, body)])
    assert "Headspace" in subs and "sales tax on top" in subs["Headspace"].matched_from


def test_several_apps_in_one_apple_series_different_amounts_and_days():
    calm, duo = monthly(10, 16.23), monthly(24, 13.94, prefix="d")
    receipts = [email("c", calm[-1].date, apple_new(calm[-1].date, [("Calm: Sleep & Meditation",
                                                                      "Calm Premium (Monthly)", 14.99)], 1.24)),
                email("d", duo[-1].date, apple_new(duo[-1].date, [("Duolingo: Language Lessons",
                                                                    "Super Duolingo (Monthly)", 12.99)], 0.95,
                                                    order="MSQ7R4V2NB"))]
    subs, _ = named(calm + duo, receipts)
    assert {"Calm", "Super Duolingo"} <= set(subs) and not any(m.endswith("(unmatched)") for m in subs)


def test_same_price_on_different_days_is_split_and_matched():
    a, b = monthly(5, 10.69), monthly(20, 10.69, prefix="b")
    receipts = [email("a", a[-1].date, apple_new(a[-1].date, [("Calm: Sleep & Meditation", "Calm Premium (Monthly)",
                                                                9.99)], 0.70)),
                email("b", b[-1].date, apple_new(b[-1].date, [("Headspace: Sleep & Meditation", "Headspace (Monthly)",
                                                                9.99)], 0.70, order="MQX3FWHJMN"))]
    subs, _ = named(a + b, receipts)
    assert {"Calm", "Headspace"} <= set(subs)
    assert subs["Calm"].cadence.value == "monthly" and subs["Calm"].last_charged.day == 5


def test_bundled_receipt_splits_one_charge_into_two_subscriptions():
    txs = monthly(12, 27.04)
    body = apple_new(txs[-1].date, [("Duolingo: Language Lessons", "Super Duolingo (Monthly)", 12.99),
                                    ("Strava: Run, Bike, Hike", "Strava Subscription (Monthly)", 11.99)], 2.06)
    subs, series = named(txs, [email("b", txs[-1].date, body)])
    duo, strava = subs["Super Duolingo"], subs["Strava"]
    assert round(duo.amount + strava.amount, 2) == 27.04  # they still add up to the bank amount
    assert duo.amount == 14.06 and strava.amount == 12.98
    assert "bills 2 subscriptions together" in duo.matched_from
    assert series[duo.id] == series[strava.id]


def test_no_receipt_stays_unmatched_with_a_clear_note():
    subs, _ = named(monthly(15, 7.48), [])
    [s] = subs.values()
    assert s.merchant == "Apple (unmatched)" and s.billed_by == "apple"
    assert "No Apple receipt" in s.matched_from and "$7.48" in s.matched_from


def test_receipt_too_far_from_any_charge_does_not_match():
    txs = monthly(10, 16.23)
    old = email("r", txs[0].date - timedelta(days=20),
                apple_new(txs[0].date, [("Calm: Sleep & Meditation", "Calm Premium (Monthly)", 14.99)], 1.24))
    subs, _ = named(txs, [old])
    assert "Apple (unmatched)" in subs


def test_two_apps_tied_stay_unmatched():
    txs = monthly(10, 10.69, n=2)
    receipts = [email("a", txs[-1].date, apple_new(txs[-1].date, [("Calm: Sleep & Meditation",
                                                                    "Calm Premium (Monthly)", 9.99)], 0.0)),
                email("b", txs[-1].date, apple_new(txs[-1].date, [("Headspace: Sleep & Meditation",
                                                                    "Headspace (Monthly)", 9.99)], 0.0, order="MQX3FWHJMN"))]
    # neither total equals the charge; both prices fit with tax on top, equally
    subs, _ = named(txs, receipts)
    [s] = subs.values()
    assert s.merchant == "Apple (unmatched)" and "equally" in s.matched_from


def test_subscription_confirmation_names_the_first_charge_of_a_trial():
    txs = monthly(25, 75.94, n=2)
    txs = [Transaction(id="y1", date=TODAY - timedelta(days=370), description="APPLE.COM/BILL", amount=75.94),
           Transaction(id="y2", date=TODAY - timedelta(days=5), description="APPLE.COM/BILL", amount=75.94)]
    notice = ("This email confirms your subscription purchase:\nApp  Calm: Sleep & Meditation\n"
              "Subscription  Calm Premium (Annual)\nRenewal Price  $69.99/year")
    subs, _ = named(txs, [email("c", txs[0].date - timedelta(days=7), notice, subject="Subscription Confirmation")])
    assert "Calm" in subs and "subscription email" in subs["Calm"].matched_from


def test_google_play_named_from_receipt_and_from_descriptor():
    known = monthly(8, 14.06, desc="GOOGLE *Duolingo g.co/payhelp#CA")
    unknown = monthly(18, 4.27, desc="GOOGLE *Sleep Sounds g.co/payhelp#CA", prefix="s")
    subs, _ = named(known + unknown, [])
    assert subs["Super Duolingo"].billed_by == "google_play"  # a known app's charge reads GOOGLE *<app>
    sleep = subs["Sleep Sounds"]
    assert sleep.billed_by == "google_play" and "bank descriptor" in sleep.matched_from


def test_google_play_receipt_names_a_generic_descriptor():
    txs = monthly(8, 14.06, desc="GOOGLE *Google Play g.co/payhelp#CA")
    body = google(txs[-1].date, "Noom Premium - Monthly", "Noom: Healthy Weight Loss", "Noom Inc", 12.99, 1.07)
    e = email("g", txs[-1].date, body, subject="Your Google Play Order Receipt",
              sender="googleplay-noreply@google.com")
    subs, _ = named(txs, [e])
    assert "Noom" in subs and "Google Play receipt" in subs["Noom"].matched_from


# --- Lightning reads a layout code doesn't know ----------------------------------------------------------

def test_model_reads_an_unknown_layout_but_cannot_invent_amounts(fake_llm):
    body = "Thanks for subscribing!\nPocket Casts Plus, billed yearly: USD 39.99 + 3.30 tax = USD 43.29"
    fake_llm.script[LIGHTNING] = [json.dumps({
        "items": [{"name": "Pocket Casts Plus", "plan": "Yearly", "price": 39.99}],
        "subtotal": 39.99, "tax": 3.30, "total": 99.99})]  # 99.99 isn't in the email
    store.reset("m")
    [r] = read_receipts("m", [email("p", TODAY, body)])
    assert r.read_by == LIGHTNING and r.items[0].name == "Pocket Casts Plus"
    assert r.total is None  # an amount the email doesn't show is dropped
    assert fake_llm.calls[0]["response_format"]["json_schema"]["strict"] is True
    msg = fake_llm.calls[0]["messages"][-1]["content"]
    assert msg.startswith("<email>") and msg.rstrip().endswith("</email>")


def test_model_is_not_called_when_code_reads_the_receipt(fake_llm):
    store.reset("m2")
    read_receipts("m2", [email("a", TODAY, apple_new(TODAY, [("Calm: Sleep & Meditation", "Calm Premium (Monthly)",
                                                             14.99)], 1.24))])
    assert fake_llm.calls == []


def test_model_failure_keeps_the_code_reading(fake_llm):
    fake_llm.default = RuntimeError("down")
    store.reset("m3")
    [r] = read_receipts("m3", [email("p", TODAY, "Thanks for subscribing! Pocket Casts Plus USD 39.99")])
    assert r.read_by == "code" and not any(i.price for i in r.items)


def test_extraction_fact_is_the_last_fallback():
    from clawback.models import Fact

    e = email("f", TODAY, "Something Apple sent that code can't read")
    fact = Fact(email_id="f", received=TODAY, kind="store_receipt", merchant="Calm", amount=14.99)
    store.reset("f")
    [r] = store_billing.read_receipts("f", [e], [fact])
    assert r.read_by == "extract" and r.items[0].merchant == "Calm"
