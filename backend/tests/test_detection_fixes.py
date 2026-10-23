"""General fixes from the eval baseline: app-store naming, fuzzy merchant joins, steadier recurring detection,
things that are not subscriptions, and category overlaps on the bigger merchant list. All data made up."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from clawback.demo_data import _monthly_dates
from clawback.merchants import same_merchant
from clawback.models import Cadence, Email, Fact, Subscription, Transaction
from clawback.pipeline.extract import extract_all
from clawback.pipeline.flags import flag_overlaps
from clawback.pipeline.recurring import detect, set_aside
from clawback.pipeline.run import run
from clawback.store import store

TODAY = date(2026, 10, 22)
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"
NULLS = {"kind": "other", "merchant": None, "amount": None, "saved_amount": None,
         "old_price": None, "new_price": None, "trial_days_left": None}


def tx(tid, d, desc, amount, category=None):
    return Transaction(id=tid, date=d, description=desc, amount=amount, source="plaid", category=category)


def monthly(desc, amount, day=10, n=6, prefix="m", category=None):
    return [tx(f"{prefix}{k}", d, desc, amount, category) for k, d in enumerate(_monthly_dates(TODAY, day, n))]


def mail(eid, d, sender, subject, body):
    return Email(id=eid, received_at=datetime(d.year, d.month, d.day, 9, tzinfo=timezone.utc), sender=sender,
                 subject=subject, body_text=body)


def apple_receipt(d, app, plan, price, tax, order="MT8KQ2ZX4L"):
    return "\n".join(["Receipt", f"{d:%B} {d.day}, {d.year}", f"Order ID: {order}", "Document: 284019573316",
                      "Apple Account: jane.doe@icloud.com", "", "App Store", app, plan, "Renews soon", f"${price:.2f}",
                      "", "Billing and Payment", f"Subtotal ${price:.2f}", f"Tax ${tax:.2f}",
                      f"Visa •••• 1234 ${price + tax:.2f}"])


# --- 1. App-store naming -------------------------------------------------------------------------------

HEADSPACE = mail("hs", TODAY - timedelta(days=3), "no_reply@email.apple.com", "Your receipt from Apple.",
                 apple_receipt(TODAY - timedelta(days=3), "Headspace: Sleep & Meditation", "Headspace (Monthly)",
                               12.99, 0.95))
APPLE_MUSIC = mail("am", TODAY - timedelta(days=12), "no_reply@email.apple.com", "Your receipt from Apple.",
                   apple_receipt(TODAY - timedelta(days=12), "Apple Music", "Apple Music Individual (Monthly)",
                                 10.99, 0.80, order="MQX3FWHJMN"))
YOUTUBE = mail("yt", TODAY - timedelta(days=5), "Google Play <googleplay-noreply@google.com>",
               "Your Google Play Order Receipt from Oct 17, 2026",
               "Thank you\nOrder number: GPA.3391-2045-7781-60234\nItem Price\n"
               "YouTube Premium - Monthly (YouTube) $13.99/month\nState sales tax: $1.12\nTotal: $15.11/month")


@pytest.mark.parametrize("email, expected", [(HEADSPACE, "Headspace"), (APPLE_MUSIC, "Apple Music"),
                                             (YOUTUBE, "YouTube Premium")])
def test_store_receipt_names_the_app_not_the_sender_without_a_key(email, expected):
    store.reset("x")
    [fact] = extract_all("x", [email])
    assert fact.kind == "store_receipt" and fact.merchant == expected


@pytest.mark.parametrize("model_name", [None, "Apple", "Headspace: Sleep & Meditation"])
def test_store_receipt_names_the_app_with_the_model(fake_llm, model_name):
    fake_llm.default = json.dumps({**NULLS, "kind": "store_receipt", "merchant": model_name, "amount": 12.99})
    store.reset("y")
    [fact] = extract_all("y", [HEADSPACE])
    assert fact.merchant in ("Headspace", "Apple") and fact.merchant != "iCloud+"
    if model_name != "Apple":
        assert fact.merchant == "Headspace"


def test_two_apple_apps_get_their_own_ids_and_never_overlap_with_themselves():
    u = store.reset("apps")
    store.use_real_data("apps")
    hs = monthly("APPLE.COM/BILL 866-712-7753 CA", 13.94, day=TODAY.day - 3 if TODAY.day > 3 else 1, prefix="h")
    am = monthly("APPLE.COM/BILL 866-712-7753 CA", 11.79, day=10, prefix="a")
    u.transactions = hs + am
    u.emails = [HEADSPACE, APPLE_MUSIC]
    run("apps", TODAY)
    names = sorted(s.merchant for s in u.subscriptions.values())
    assert names == ["Apple Music", "Headspace"]
    assert len({s.id for s in u.subscriptions.values()}) == 2
    for s in u.subscriptions.values():
        assert not any(f.kind == "overlap" and s.merchant + " and " + s.merchant in f.message for f in s.flags)


def test_one_service_billed_twice_is_paid_twice_not_an_overlap():
    a = Subscription(id="spotify", merchant="Spotify", category="music", monthly_cost=11.99, billed_by="apple")
    b = Subscription(id="merchant-spotify", merchant="Spotify", category="music", monthly_cost=11.99)
    flag_overlaps([a, b])
    assert [f.kind for f in a.flags] == ["paid_twice"] and "through Apple, directly" in a.flags[0].message
    assert sorted(f.monthly_savings for f in a.flags + b.flags) == [0.0, 11.99]


# --- 2. Merchant joins ---------------------------------------------------------------------------------

def test_names_join_on_shared_words_and_aliases():
    assert same_merchant("Crunchyroll", "Crunchyroll Mega Fan")
    assert same_merchant("Max", "HBO Max")
    assert same_merchant("Bluebird Radio", "Bluebird Radio Plus")
    assert not same_merchant("Apple Music", "Apple TV")
    assert not same_merchant("YouTube Premium", "YouTube TV")
    assert not same_merchant("Joe Pizza", "Joe Coffee")


def test_usage_email_joins_a_bank_series_with_a_longer_name(fake_llm):  # cached facts are used with a key
    u = store.reset("join")
    store.use_real_data("join")
    u.transactions = monthly("BLUEBIRD RADIO PLUS", 7.99, prefix="b")
    u.emails = [mail("miss", TODAY - timedelta(days=6), "hello@bluebird.example", "We miss you at Bluebird Radio",
                     "It's been a while since you listened.")]
    u.facts["miss"] = Fact(email_id="miss", received=TODAY - timedelta(days=6), kind="inactivity",
                           merchant="Bluebird Radio")
    run("join", TODAY)
    [s] = u.subscriptions.values()
    assert s.merchant == "Bluebird Radio Plus" and s.usage.level == "low"


# --- 3. Recurring detection ----------------------------------------------------------------------------

def test_a_one_off_charge_does_not_break_the_series():
    adobe = monthly("ADOBE *CREATIVE CLD 408-536-6000", 59.99) + [
        tx("stock", TODAY - timedelta(days=50), "ADOBE *ADOBE STOCK 408-536-6000", 29.99)]
    [s] = detect(adobe, TODAY)
    assert (s.merchant, s.amount, s.charge_count, s.cadence) == ("Adobe Creative Cloud", 59.99, 6, Cadence.monthly)


def test_gym_monthly_fee_plus_annual_fee():
    gym = monthly("PLANET FITNESS 844-880-7180", 10.0, day=17) + [
        tx("annual", TODAY - timedelta(days=80), "PLANET FITNESS 844-880-7180", 49.0)]
    [s] = detect(gym, TODAY)
    assert s.merchant == "Planet Fitness" and s.amount == 10.0 and s.charge_count == 6


def test_unknown_merchant_needs_a_real_run():
    """An unknown shop where one order often costs the same is not a plan."""
    coffee = [tx(f"c{k}", TODAY - timedelta(days=3 * k), "BLUE BOTTLE COFFEE 0042", 5.45 if k % 9 == 0 else 4.0 + k / 10)
              for k in range(30)]
    assert detect(coffee, TODAY) == []


def test_descriptor_change_keeps_one_series_and_shows_the_price_step():
    dates = _monthly_dates(TODAY, 14, 6)
    txs = [tx(f"h{k}", d, "HBO MAX HELP.HBOMAX.COM NY" if k < 3 else "MAX.COM NEW YORK NY", 15.99 if k < 3 else 16.99)
           for k, d in enumerate(dates)]
    [s] = detect(txs, TODAY)
    assert s.merchant == "HBO Max" and s.charge_count == 6
    assert (s.price_change.old_amount, s.price_change.new_amount) == (15.99, 16.99)


def test_quarterly_plans():
    dates = [TODAY - timedelta(days=5 + 91 * k) for k in range(3)][::-1]
    txs = [tx(f"q{k}", d, "MINT MOBILE 800-683-7392", 45.0) for k, d in enumerate(dates)]
    [s] = detect(txs, TODAY)
    assert s.cadence == Cadence.quarterly and s.monthly_cost == 15.0 and s.kind == "bill"


def test_annual_plan_with_one_charge_confirmed_by_a_renewal_email():
    u = store.reset("annual")
    store.use_real_data("annual")
    u.transactions = [tx("y1", TODAY - timedelta(days=40), "NYTIMES*NYTDIGITAL 800-698-4637 NY", 195.0)]
    u.emails = [mail("r", TODAY - timedelta(days=60), "nytdirect@nytimes.com", "Your subscription renews soon",
                     "Your All Access subscription renews on the date below at $195.00/year.")]
    run("annual", TODAY)
    [s] = u.subscriptions.values()
    assert s.cadence == Cadence.annual and s.monthly_cost == 16.25 and s.detected_from == ["bank", "email"]
    assert "yearly plan" in s.matched_from


def test_one_charge_without_an_email_is_not_a_subscription():
    u = store.reset("one")
    store.use_real_data("one")
    u.transactions = [tx("y1", TODAY - timedelta(days=40), "NYTIMES*NYTDIGITAL 800-698-4637 NY", 195.0)]
    run("one", TODAY)
    assert u.subscriptions == {}


def test_apple_annual_plan_with_one_charge_and_its_receipt():
    u = store.reset("apple-annual")
    store.use_real_data("apple-annual")
    d = TODAY - timedelta(days=20)
    u.transactions = [tx("a1", d, "APPLE.COM/BILL 866-712-7753 CA", 75.76)]
    u.emails = [mail("r", d - timedelta(days=1), "no_reply@email.apple.com", "Your receipt from Apple.",
                     apple_receipt(d, "Calm: Sleep & Meditation", "Calm Premium (Annual)", 69.99, 5.77))]
    run("apple-annual", TODAY)
    [s] = u.subscriptions.values()
    assert (s.merchant, s.cadence, s.billed_by) == ("Calm", Cadence.annual, "apple")


@pytest.mark.parametrize("desc, category, kind", [
    ("ZELLE TO JORDAN LANDLORD", None, "transfer"),
    ("ONLINE TRANSFER TO SAVINGS 4421", None, "transfer"),
    ("CHASE CREDIT CRD AUTOPAY", None, "transfer"),
    ("AVALON APARTMENTS RENT", None, "housing"),
    ("TOYOTA FINANCIAL SVCS", None, "loan"),
    ("ROCKET MORTGAGE PMT", None, "loan"),
    ("AFFIRM *PAYMENT", None, "loan"),
    ("SQ *MINDFUL THERAPY GROUP", None, "healthcare"),
    ("PIEDMONT PHYSICIANS COPAY", None, "healthcare"),
    ("ACME SERVICING CO", "LOAN_PAYMENTS_CAR_PAYMENT", "loan"),
    ("SUNRISE HOLDINGS LLC", "RENT_AND_UTILITIES_RENT", "housing"),
    ("NORTHSIDE PEDS", "MEDICAL_PRIMARY_CARE", "healthcare"),
    ("MONTHLY MAINTENANCE FEE", None, "bank_fee"),
])
def test_not_subscriptions(desc, category, kind):
    t = tx("x", TODAY, desc, 1450.0, category)
    assert set_aside(t) == kind
    assert detect(monthly(desc, 1450.0, category=category), TODAY) == []


@pytest.mark.parametrize("desc", ["RENT THE RUNWAY", "SQ *IRON TEMPLE GYM", "STARLINK INTERNET"])
def test_real_plans_are_not_set_aside(desc):
    assert detect(monthly(desc, 89.0), TODAY) != []


def test_merchant_list_wins_over_a_plaid_transfer_category():
    """Plaid sometimes files a subscription paid by card under a transfer category; the merchant list wins."""
    assert detect(monthly("SPOTIFY USA", 11.99, category="TRANSFER_OUT_ACCOUNT_TRANSFER"), TODAY) != []


# --- 4. Category overlaps on the bigger list ------------------------------------------------------------

def test_two_ai_tools_and_two_music_services_overlap():
    u = store.reset("ov")
    store.use_real_data("ov")
    u.transactions = (monthly("OPENAI *CHATGPT SUBSCR", 20.0, prefix="o") + monthly("ANTHROPIC CLAUDE.AI", 20.0, day=12, prefix="c")
                      + monthly("SPOTIFY USA", 11.99, day=14, prefix="s")
                      + monthly("GOOGLE *YouTube Music g.co/helppay#", 10.99, day=16, prefix="y"))
    run("ov", TODAY)
    flags = {s.merchant: {f.kind for f in s.flags} for s in u.subscriptions.values()}
    assert all("overlap" in flags[m] for m in ("ChatGPT Plus", "Claude (Anthropic)", "Spotify", "YouTube Music"))


def test_trial_without_a_price_still_flags_and_never_crashes():
    from datetime import date, timedelta

    from clawback.models import Subscription
    from clawback.pipeline.flags import flag_one

    today = date(2026, 10, 20)
    sub = Subscription(id="t", merchant="Trialco", category="other", status="trial",
                       next_expected=today + timedelta(days=3), amount=None)
    flags = flag_one(sub, None, today)
    trial = next(f for f in flags if f.kind == "trial_ending")
    assert "starts charging" in trial.message and "None" not in trial.message
