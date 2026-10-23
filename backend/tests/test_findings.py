"""Findings and bills: each detector on small inline rule data, the API routes, and the demo story on the real rules."""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from clawback import connections, demo_data
from clawback.connections import PlaidConnection, now
from clawback.findings import rulebook
from clawback.findings.bills import bill_flags, find_date, promo_notices
from clawback.findings.charges import bank_fees, dispute_deadline, duplicate_charges
from clawback.findings.purchases import Item, Purchase, extract_purchases, parse_rules
from clawback.findings.refunds import PriceCheck, _band, flight_emails, flight_findings, price_drops
from clawback.findings.rulebook import Rulebook
from clawback.findings.settlements import settlement_findings
from clawback.findings.util import end_of_month
from clawback.findings.airports import distance_km
from clawback.models import Email, Subscription, Transaction
from clawback.pipeline.recurring import detect_series
from clawback.pipeline.run import run
from clawback.store import store

TODAY = date(2026, 10, 22)
URL = "https://example.gov/rule"


def tx(i, d, desc, amount):
    return Transaction(id=f"x{i}", date=d, description=desc, amount=amount)


def mail(i, d, sender, subject, body=""):
    return Email(id=f"m{i}", received_at=datetime.combine(d, time(9), tzinfo=timezone.utc), sender=sender,
                 subject=subject, body_text=body)


RULES = dict(
    retailers={"retailers": [
        {"store": "Target", "match": ["TARGET", "target.com"], "adjusts": True, "window_days": 14,
         "window_from": "purchase", "conditions": "Same item, sold by Target.", "exclusions": ["Clearance"],
         "how_to_claim": "Start a chat on target.com.", "claim_url": "https://www.target.com/help",
         "source_url": "https://www.target.com/policy", "verified": True},
        {"store": "Best Buy", "match": ["BEST BUY", "bestbuy.com"], "adjusts": True, "window_days": 15,
         "window_from": "delivery", "conditions": "", "how_to_claim": "Call.", "claim_url": None,
         "source_url": "https://www.bestbuy.com/policy", "verified": True},
        {"store": "Walmart", "match": ["WALMART", "walmart.com"], "adjusts": False, "window_days": None,
         "window_from": None, "conditions": "", "how_to_claim": "", "claim_url": None,
         "source_url": "https://www.walmart.com/policy", "verified": True},
        {"store": "Shady", "match": ["SHADY", "shady.com"], "adjusts": True, "window_days": 30, "window_from": "purchase",
         "conditions": "", "how_to_claim": "", "claim_url": None, "source_url": "https://shady.com", "verified": False},
    ]},
    bills={"providers": [
        {"provider": "NetCo", "match": ["NETCO", "netco.com"], "category": "internet", "negotiable": True,
         "variable_amount": False, "account_url": "https://netco.com/account",
         "cancel_or_retention": "https://netco.com/cancel", "notes": "", "source_url": "https://netco.com", "verified": True},
        {"provider": "PowerCo", "match": ["POWERCO"], "category": "utility", "negotiable": False, "variable_amount": True,
         "account_url": None, "cancel_or_retention": None, "notes": "", "source_url": "https://powerco.com", "verified": True},
    ]},
    bank_fees={"fees": [
        {"kind": "overdraft", "label": "Overdraft fee", "patterns": ["OVERDRAFT.*FEE"], "rule": "A rule.",
         "reversal_tip": "Ask for a one-time courtesy reversal.", "source_url": "https://example.gov/od", "verified": True},
    ]},
    disputes={"rules": [
        {"kind": "credit_card_billing_error", "label": "Credit card billing error (FCBA)", "applies_to": "credit_card",
         "notice_deadline_days": 60, "summary": "Write within 60 days.", "source_urls": ["https://example.gov/fcba"],
         "verified": True},
        {"kind": "debit_card_error", "label": "Debit card error (Reg E)", "applies_to": "debit_card",
         "notice_deadline_days": 60, "summary": "Tell the bank within 60 days.", "source_urls": ["https://example.gov/rege"],
         "verified": True},
    ]},
    flights={
        "us_dot": {"law": "US DOT refund rule", "summary": "Refund when the airline cancels.", "source_urls": [URL],
                   "significant_change": {"domestic_hours": 3, "international_hours": 6}, "verified": True},
        "eu261": {"law": "EU261", "currency": "EUR", "delay_threshold_hours": 3, "cancellation_notice_days": 14,
                  "summary": "Compensation by distance.", "source_urls": [URL], "verified": True,
                  "bands": [{"label": "1,500 km or less", "min_km": 0, "max_km": 1500, "amount": 250},
                            {"label": "1,500 to 3,500 km", "min_km": 1500, "max_km": 3500, "amount": 400},
                            {"label": "over 3,500 km (not intra-EU)", "min_km": 3500, "max_km": None, "amount": 600}]},
        "uk261": {"law": "UK261", "currency": "GBP", "delay_threshold_hours": 3, "cancellation_notice_days": 14,
                  "summary": "UK compensation.", "source_urls": [URL], "verified": True,
                  "bands": [{"label": "1,500 km or less", "min_km": 0, "max_km": 1500, "amount": 220},
                            {"label": "1,500 to 3,500 km", "min_km": 1500, "max_km": 3500, "amount": 350},
                            {"label": "over 3,500 km", "min_km": 3500, "max_km": None, "amount": 520}]},
        "airlines": [{"name": "United", "match": ["united.com"], "refund_url": "https://www.united.com/refunds",
                      "compensation_url": None, "source_url": "https://www.united.com", "verified": True}],
    },
    settlements={"settlements": [
        {"id": "acme", "name": "Acme Widget Settlement", "defendant": "Acme Corp.", "match": ["ACME", "acme.com"],
         "who_qualifies": "People who bought Acme widgets.", "class_period": {"start": "2026-01-01", "end": "2026-06-30"},
         "claim_deadline": "2026-12-31", "payout": "About $20 each", "payout_estimate_usd": 20.0, "proof_required": False,
         "claim_url": "https://acmesettlement.com/claim", "source_url": "https://acmesettlement.com", "verified": True},
        {"id": "closed", "name": "Closed Settlement", "defendant": "Oldco", "match": ["OLDCO"], "who_qualifies": "",
         "class_period": {"start": None, "end": None}, "claim_deadline": "2026-01-01", "payout": "",
         "payout_estimate_usd": None, "claim_url": "https://old.com", "source_url": "https://old.com", "verified": True},
        {"id": "unsure", "name": "Unconfirmed Settlement", "defendant": "Acme Corp.", "match": ["ACME"],
         "who_qualifies": "", "class_period": {"start": None, "end": None}, "claim_deadline": "2027-01-01", "payout": "",
         "payout_estimate_usd": 99.0, "claim_url": "https://x.com", "source_url": "https://x.com", "verified": False},
    ]},
)


@pytest.fixture()
def book() -> Rulebook:
    return Rulebook.from_data(**RULES)


def test_rulebook_keeps_only_verified(book):
    assert [r["store"] for r in book.retailers] == ["Target", "Best Buy", "Walmart"]
    assert book.retailer_for("SHADY STORE 123") is None
    assert [s["id"] for s in book.settlements] == ["acme", "closed"]
    assert book.disputes["credit"]["days"] == 60 and book.disputes["debit"]["source_url"] == "https://example.gov/rege"
    assert book.flights["us_dot"]["domestic_hours"] == 3 and book.flights["eu261"]["bands"][0]["amount"] == 250


# --- Bills -------------------------------------------------------------------------------------------

def _bill(name="NetCo", amount=85.0):
    return Subscription(id=name.lower(), merchant=name, category="internet", kind="bill", bill_category="internet",
                        amount=amount, monthly_cost=amount, first_seen=TODAY - timedelta(days=180))


def test_bill_increase_thresholds(book):
    rule = book.bill_provider_for("NETCO")
    exact = bill_flags(_bill(), [100, 100, 100, 110, 110], rule, [], TODAY)
    assert [(f.kind, f.severity, f.monthly_savings) for f in exact] == [("bill_increase", "medium", 10.0)]
    below = bill_flags(_bill(), [100, 100, 100, 109.99, 109.99], rule, [], TODAY)
    assert [f.kind for f in below] == ["negotiable"]  # under 10%: only the "you could ask" info flag
    high = bill_flags(_bill(), [55, 55, 55, 85, 85, 85], rule, [], TODAY)
    assert high[0].severity == "high" and high[0].monthly_savings == 30.0 and "$55.00 to $85.00" in high[0].message
    assert bill_flags(_bill(), [100, 115], rule, [], TODAY)[0].kind == "negotiable"  # too few charges to compare


def test_variable_utility_swings_are_not_flagged(book):
    rule = book.bill_provider_for("POWERCO ONLINE PMT")
    assert rule["variable_amount"]
    assert bill_flags(_bill("PowerCo"), [60.0, 140.0, 61.0, 139.0, 60.0, 140.0], rule, [], TODAY) == []

    days = [TODAY - timedelta(days=30 * k + 3) for k in range(6)]
    txs = [tx(i, d, "POWERCO ONLINE PMT", a) for i, (d, a) in enumerate(zip(days, (60, 140, 61, 139, 60, 140)))]
    assert detect_series(txs, TODAY)[0] == []  # without the bill rules, swinging amounts aren't recurring
    subs, series = detect_series(txs, TODAY, book.bill_provider_for)
    assert [(s.merchant, s.kind, s.bill_category) for s in subs] == [("PowerCo", "bill", "utility")]
    assert len(series[subs[0].id]) == 6


def test_promo_ending_from_email(book):
    email = mail(1, TODAY - timedelta(days=5), "offers@netco.com", "Your promotional rate is ending",
                 "Your promotional rate of $55.00/month ends on November 15, 2026. Your new rate will be $85.00/month.")
    notices = promo_notices([email], book.bill_provider_for)
    assert [(n.provider, n.ends_on, n.old_price, n.new_price) for n in notices] == [("NetCo", date(2026, 11, 15), 55.0, 85.0)]
    flags = bill_flags(_bill(amount=55.0), [55, 55, 55, 55], book.bill_provider_for("NETCO"), notices, TODAY)
    assert [(f.kind, f.severity, f.monthly_savings) for f in flags] == [("promo_ending", "medium", 30.0)]
    assert find_date("ends Jan 3", date(2026, 12, 20)) == date(2027, 1, 3)  # no year: the next one


# --- Duplicate charges and fees ----------------------------------------------------------------------

def _receipt(store, total, d, number="A-12345"):
    return Purchase(store=store, order_date=d, email_id="r", sender="x@x.com", items=[Item("Thing", total)],
                    total=total, order_number=number)


def test_duplicate_charge_with_one_receipt_is_high(book):
    d = date(2026, 10, 13)
    txs = [tx(1, d, "BEST BUY 00012345 ATLANTA", 129.99), tx(2, d, "BEST BUY 00012345 ATLANTA", 129.99)]
    [f] = duplicate_charges(txs, set(), [_receipt("Best Buy", 129.99, d)], book.disputes, TODAY)
    assert (f.kind, f.merchant, f.amount, f.confidence) == ("duplicate_charge", "Best Buy", 129.99, "high")
    assert f.deadline == date(2026, 12, 30) and f.deadline_label == "Dispute window closes (estimated)"
    assert any("estimate" in e for e in f.evidence) and f.rule.source_url == "https://example.gov/fcba"

    [medium] = duplicate_charges(txs, set(), [], book.disputes, TODAY)
    assert medium.confidence == "medium"
    two_orders = [_receipt("Best Buy", 129.99, d, "A1"), _receipt("Best Buy", 129.99, d, "A2")]
    assert duplicate_charges(txs, set(), two_orders, book.disputes, TODAY) == []  # really bought twice


def test_duplicate_window_amount_and_recurring_rules(book):
    d = date(2026, 10, 1)
    three_days = [tx(1, d, "SHOP ONE", 20.0), tx(2, d + timedelta(days=3), "SHOP ONE", 20.0)]
    four_days = [tx(3, d, "SHOP TWO", 20.0), tx(4, d + timedelta(days=4), "SHOP TWO", 20.0)]
    small = [tx(5, d, "SHOP THREE", 4.99), tx(6, d, "SHOP THREE", 4.99)]
    found = duplicate_charges(three_days + four_days + small, set(), [], book.disputes, TODAY)
    assert [f.merchant for f in found] == ["Shop One"]
    assert duplicate_charges(three_days, {"x1", "x2"}, [], book.disputes, TODAY) == []  # part of a recurring series


def test_dispute_deadline_boundaries(book):
    rule = book.disputes["credit"]
    assert end_of_month(date(2026, 2, 3)) == date(2026, 2, 28)
    assert dispute_deadline(date(2026, 1, 31), rule) == date(2026, 4, 1)
    txs = [tx(1, date(2026, 1, 31), "SHOP ONE", 50.0), tx(2, date(2026, 1, 31), "SHOP ONE", 50.0)]
    assert duplicate_charges(txs, set(), [], book.disputes, date(2026, 4, 1))  # last day: still open
    assert duplicate_charges(txs, set(), [], book.disputes, date(2026, 4, 2)) == []  # window closed


def test_recurring_series_with_close_charges_is_not_a_duplicate():
    start = TODAY - timedelta(days=24)
    days = [start, start + timedelta(days=7), start + timedelta(days=14), start + timedelta(days=17),
            start + timedelta(days=24)]
    u = store.reset("dup-test")
    u.transactions = [tx(i, d, "SPIN CLASS STUDIO", 10.0) for i, d in enumerate(days)]
    run("dup-test", TODAY)
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    assert any(s.merchant.startswith("Spin") for s in u.subscriptions.values())
    assert not [f for f in u.findings.values() if f.kind == "duplicate_charge"]


def test_bank_fees(book):
    txs = [tx(1, TODAY, "OVERDRAFT ITEM FEE", 35.0), tx(2, TODAY, "COFFEE SHOP", 4.0)]
    found, ids = bank_fees(txs, book.fee_kind_for, "First Bank", TODAY)
    assert ids == {"x1"} and [(f.kind, f.merchant, f.amount, f.deadline) for f in found] == [
        ("bank_fee", "First Bank", 35.0, None)]
    assert found[0].rule.source_url == "https://example.gov/od"


# --- Price drops -------------------------------------------------------------------------------------

def _checker(prices: dict[str, float]):
    def check(p, item, adjusts):
        return PriceCheck(price=prices[item.name], how="simulated") if item.name in prices else None
    return check


def test_purchase_parsing(book):
    e = mail(1, TODAY - timedelta(days=6), "orders@oe.target.com", "Thanks for your order!",
             "Order #102938475610. Item: Sony WH-1000XM5 Headphones, $199.99. Order total: $199.99.")
    p = parse_rules(e, book.retailer_for(e.sender))
    assert (p.store, p.order_number, p.total, p.order_date) == ("Target", "102938475610", 199.99, TODAY - timedelta(days=6))
    assert [(i.name, i.price) for i in p.items] == [("Sony WH-1000XM5 Headphones", 199.99)]
    noise = mail(2, TODAY, "friend@example.com", "Lunch?", "See you at noon")
    assert extract_purchases("t", [e, noise], book.retailer_for)[0].store == "Target"


def test_price_drop_window_and_minimum(book):
    target = book.retailer_for("target.com")
    p = Purchase(store="Target", order_date=date(2026, 10, 1), email_id="e", sender="orders@target.com",
                 items=[Item("Headphones", 199.99), Item("Cable", 20.00)], order_number="123", retailer=target)
    notes: list[str] = []
    found = price_drops([p], _checker({"Headphones": 169.99, "Cable": 15.01}), date(2026, 10, 15), notes)
    assert [(f.kind, f.amount, f.deadline) for f in found] == [("price_drop", 30.0, date(2026, 10, 15))]  # last day
    assert "Cable" in " ".join(notes)  # a $4.99 drop isn't worth a claim
    assert price_drops([p], _checker({"Headphones": 169.99}), date(2026, 10, 16), []) == []  # window closed
    five = price_drops([p], _checker({"Cable": 15.00}), date(2026, 10, 2), [])
    assert [f.amount for f in five] == [5.0]


def test_walmart_doesnt_adjust_and_delivery_windows(book):
    walmart = Purchase(store="Walmart", order_date=TODAY - timedelta(days=3), email_id="w", sender="help@walmart.com",
                       items=[Item("Air Fryer", 89.0)], retailer=book.retailer_for("walmart.com"))
    notes: list[str] = []
    assert price_drops([walmart], _checker({"Air Fryer": 69.0}), TODAY, notes) == []
    assert "Walmart doesn't adjust prices" in notes[0]
    bestbuy = Purchase(store="Best Buy", order_date=TODAY - timedelta(days=2), email_id="b", sender="x@bestbuy.com",
                       items=[Item("Mouse", 129.99)], retailer=book.retailer_for("bestbuy.com"))
    [f] = price_drops([bestbuy], _checker({"Mouse": 99.99}), TODAY, [])
    assert f.deadline == TODAY + timedelta(days=13) and any("delivery date isn't known" in e for e in f.evidence)


def test_real_mode_without_tavily_checks_no_prices():
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    u = store.reset("price-real")
    store.use_real_data("price-real")
    u.emails = [mail(1, TODAY - timedelta(days=3), "orders@oe.target.com", "Thanks for your order!",
                     "Order #55555. Item: Sony WH-1000XM5 Headphones, $199.99. Order total: $199.99.")]
    run("price-real", TODAY)
    assert not [f for f in u.findings.values() if f.kind == "price_drop"]
    row = next(t for t in u.trace if t.stage == "price drops")
    assert row.status == "missing" and "live-price-check" in row.note


# --- Flights -----------------------------------------------------------------------------------------

def _flight_mails(origin, dest, flight_day, notice_days, kind="cancelled", extra=""):
    when = f"{flight_day:%b} {flight_day.day}, {flight_day.year}"
    booking = mail(1, flight_day - timedelta(days=60), "unitedairlines@united.com", "Your flight confirmation",
                   f"Confirmation number: K7Q2PL. Flight UA 1532, Somewhere ({origin}) to Elsewhere ({dest}), {when} "
                   "8:05 AM. Total fare: $412.40.")
    body = (f"Your flight UA 1532 from {origin} to {dest} on {when} has been cancelled. We've added a travel credit."
            if kind == "cancelled" else
            f"Schedule change for flight UA 1532 from {origin} to {dest} on {when}. {extra}")
    notice = mail(2, flight_day - timedelta(days=notice_days), "notifications@united.com", "About your flight", body)
    return [booking, notice]


def test_us_cancellation_refund(book):
    flight_day = TODAY + timedelta(days=10)
    events = flight_emails("t", _flight_mails("SFO", "ORD", flight_day, 5), book.airline_for)
    [f] = flight_findings(events, book.flights, TODAY)
    assert (f.kind, f.merchant, f.amount, f.currency, f.confidence) == ("flight_refund", "United", 412.40, "USD", "high")
    assert f.details["refund_url"] == "https://www.united.com/refunds" and f.rule.name == "US DOT refund rule"
    accepted = _flight_mails("SFO", "ORD", flight_day, 5)
    accepted[1].body_text += " Thanks for accepting your new flight."
    assert flight_findings(flight_emails("t", accepted, book.airline_for), book.flights, TODAY) == []


def test_schedule_change_thresholds(book):
    flight_day = TODAY + timedelta(days=30)

    def found(origin, dest, new_time):
        mails = _flight_mails(origin, dest, flight_day, 20, kind="changed",
                              extra=f"It was scheduled at 8:00 AM. New departure time is {new_time}.")
        return [f.kind for f in flight_findings(flight_emails("t", mails, book.airline_for), book.flights, TODAY)]

    assert found("SFO", "ORD", "10:30 AM") == []  # 2.5 h domestic: not significant
    assert found("SFO", "ORD", "11:00 AM") == ["flight_refund"]  # 3 h domestic
    assert found("SFO", "NRT", "1:00 PM") == []  # 5 h international
    assert found("SFO", "NRT", "2:00 PM") == ["flight_refund"]  # 6 h international


def test_eu_and_uk_compensation(book):
    flight_day = TODAY + timedelta(days=10)
    short = flight_findings(flight_emails("t", _flight_mails("CDG", "FCO", flight_day, 5), book.airline_for),
                            book.flights, TODAY)
    assert [(f.kind, f.amount, f.currency) for f in short] == [("flight_compensation", 250.0, "EUR")]
    early = flight_findings(flight_emails("t", _flight_mails("CDG", "FCO", flight_day, 20), book.airline_for),
                            book.flights, TODAY)
    assert early == []  # 14+ days' notice
    uk = flight_findings(flight_emails("t", _flight_mails("LHR", "JFK", flight_day, 3), book.airline_for),
                         book.flights, TODAY)
    assert sorted((f.kind, f.amount, f.currency) for f in uk) == [("flight_compensation", 520.0, "GBP"),
                                                                    ("flight_refund", 412.40, "USD")]
    assert 2900 < distance_km("SFO", "ORD") < 3000
    rule = book.flights["eu261"]
    assert _band(rule, 3600, intra_eu=True)["amount"] == 400 and _band(rule, 3600, intra_eu=False)["amount"] == 600
    assert _band(rule, 1500, intra_eu=False)["amount"] == 250


# --- Settlements -------------------------------------------------------------------------------------

def test_settlements(book):
    inside = settlement_findings([tx(1, date(2026, 3, 1), "ACME WIDGETS 123", 30.0)], [], book.settlements_matching, TODAY)
    assert [(f.kind, f.confidence, f.amount, f.deadline, f.amount_note) for f in inside] == [
        ("settlement", "medium", 20.0, date(2026, 12, 31), "About $20 each")]
    outside = settlement_findings([], [mail(1, date(2026, 9, 1), "news@acme.com", "Acme news")],
                                  book.settlements_matching, TODAY)
    assert [f.confidence for f in outside] == ["low"]  # only an email outside the class period: "might apply"
    assert settlement_findings([tx(2, TODAY, "OLDCO 1", 9.0)], [], book.settlements_matching, TODAY) == []  # closed
    assert settlement_findings([tx(3, TODAY, "COFFEE", 4.0)], [], book.settlements_matching, TODAY) == []


# --- The pipeline, ids and the API --------------------------------------------------------------------

def _seed_demo(client):
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    client.post("/api/demo/seed")


def test_findings_api_prepare_dismiss_done(client):
    _seed_demo(client)
    found = client.get("/api/findings").json()
    assert found and all(f["status"] == "open" for f in found)
    deadlines = [f["deadline"] for f in found]
    dated = [d for d in deadlines if d]
    assert dated == sorted(dated) and deadlines[: len(dated)] == dated  # soonest first, no deadline last
    assert set(found[0]) >= {"id", "category", "kind", "merchant", "title", "message", "amount", "currency",
                             "amount_note", "deadline", "deadline_label", "confidence", "evidence", "rule", "status",
                             "found_on"} and "details" not in found[0]

    for f in found:
        prep = client.post(f"/api/findings/{f['id']}/prepare").json()
        assert set(prep) == {"title", "summary", "channel", "steps", "links", "message", "script", "deadline", "missing"}
        assert prep["channel"] in ("email", "chat", "phone", "form", "dispute", "in_person") and prep["steps"]
        if f["kind"] == "settlement":
            assert len(prep["links"]) == 1 and "perjury" in " ".join(prep["steps"])

    before = client.get("/api/summary").json()
    fee = next(f for f in found if f["kind"] == "bank_fee")
    assert client.post(f"/api/findings/{fee['id']}/dismiss").json()["status"] == "dismissed"
    client.post("/api/sync")  # re-run: the same id keeps its status
    after = {f["id"]: f for f in client.get("/api/findings").json()}
    assert after[fee["id"]]["status"] == "dismissed" and client.get("/api/findings").json()[-1]["id"] == fee["id"]

    drop = next(f for f in found if f["kind"] == "price_drop")
    done = client.post(f"/api/findings/{drop['id']}/done", json={"got_back": 30}).json()
    assert done["status"] == "done"
    summary = client.get("/api/summary").json()
    assert summary["recovered_total"] == 30.0 and "Self-reported" in summary["recovered_note"]
    assert summary["owed_count"] == before["owed_count"] - 2
    assert summary["owed_total"] == round(before["owed_total"] - fee["amount"] - drop["amount"], 2)

    assert client.post("/api/findings/nope/prepare").status_code == 404
    assert client.post(f"/api/findings/{drop['id']}/done", json={"got_back": -1}).status_code == 422


def test_negotiate_route(client):
    _seed_demo(client)
    subs = {s["merchant"]: s for s in client.get("/api/subscriptions").json()}
    xfinity = next(s for m, s in subs.items() if m.startswith("Xfinity"))
    prep = client.post(f"/api/subscriptions/{xfinity['id']}/negotiate").json()
    talk = " ".join(prep["script"])
    assert prep["channel"] in ("phone", "chat") and "$55.00" in talk and "$85.00" in talk and "customer since" in talk
    assert prep["message"]["body"] and any(link["verified"] for link in prep["links"])
    assert any("bill-market-rates" in m for m in prep["missing"])
    assert client.post("/api/subscriptions/nope/negotiate").status_code == 404


def test_demo_story(client):
    _seed_demo(client)
    today = date.today()
    found = client.get("/api/findings").json()
    by_kind: dict[str, list] = {}
    for f in found:
        by_kind.setdefault(f["kind"], []).append(f)

    [drop] = by_kind["price_drop"]
    target = rulebook.current().retailer_for("target.com")
    assert (drop["merchant"], drop["amount"]) == ("Target", 30.0)
    assert drop["deadline"] == (today - timedelta(days=6) + timedelta(days=target["window_days"])).isoformat()
    assert any("simulated price check (demo data)" in e for e in drop["evidence"])

    [dup] = by_kind["duplicate_charge"]
    assert (dup["merchant"], dup["amount"], dup["confidence"]) == ("Best Buy", 129.99, "high")
    assert dup["deadline"] == (end_of_month(today - timedelta(days=9)) + timedelta(days=60)).isoformat()

    assert sorted(f["amount"] for f in by_kind["bank_fee"]) == [3.5, 4.17, 35.0]
    [flight] = by_kind["flight_refund"]
    assert (flight["merchant"], flight["amount"], flight["currency"]) == ("United", 412.40, "USD")
    assert by_kind["settlement"] and all(f["rule"]["source_url"].startswith("https://") for f in by_kind["settlement"])
    assert not any(f["merchant"] == "Walmart" for f in found)
    trace = client.get("/api/trace").json()
    assert any(t["stage"] == "price drops" and "Walmart doesn't adjust prices" in t["note"] for t in trace)
    assert {t["stage"] for t in trace} >= {"bank fees", "extract purchases", "duplicate charges", "price drops",
                                           "flights", "settlements"}

    bills = {s["merchant"]: s for s in client.get("/api/subscriptions").json() if s["kind"] == "bill"}
    flags = {m.split(" (")[0]: [(f["kind"], f["severity"], f["monthly_savings"]) for f in s["flags"]] for m, s in bills.items()}
    assert flags["Xfinity"] == [("bill_increase", "high", 30.0)]
    assert flags["GEICO"] == [("bill_increase", "high", 19.0)]
    assert flags["Verizon Wireless"] == [("negotiable", "info", 0.0)]
    assert flags["PG&E"] == []
    assert bills[next(m for m in bills if m.startswith("Xfinity"))]["bill_category"] == "internet"

    summary = client.get("/api/summary").json()
    assert summary["bills"] == 4 and summary["subscriptions"] >= 9
    assert summary["monthly_total"] == round(summary["subscriptions_total"] + summary["bills_total"], 2)
    assert summary["owed_total"] == round(sum(f["amount"] for f in found if f["currency"] == "USD"), 2)
    assert summary["owed_count"] == len(found)


def test_ids_are_stable_across_runs():
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    u = store.reset("ids")
    u.transactions = demo_data.transactions(TODAY)
    u.emails = demo_data.emails(TODAY)
    run("ids", TODAY)
    first = set(u.findings)
    run("ids", TODAY)
    assert first and set(u.findings) == first


def test_real_mode_bank_fee_names_the_connected_bank():
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    connections.set_plaid("real-fee", PlaidConnection(access_token="a", item_id="i", institution="First Platypus Bank",
                                                      connected_at=now()))
    u = store.reset("real-fee")
    store.use_real_data("real-fee")
    u.transactions = [Transaction(id="p1", date=TODAY, description="OVERDRAFT ITEM FEE", amount=34.0, source="plaid")]
    run("real-fee", TODAY)
    [f] = u.findings.values()
    assert (f.kind, f.merchant, f.amount) == ("bank_fee", "First Platypus Bank", 34.0)


# --- Corrections from the rules data -----------------------------------------------------------------

def test_self_file_store_gets_a_reminder_without_a_drafted_message():
    from clawback.findings.actions import prepare

    book = Rulebook.from_data(retailers={"retailers": [
        {"store": "Nordstrom", "match": ["NORDSTROM"], "adjusts": True, "window_days": 10, "window_from": "purchase",
         "conditions": "Full-price items.", "how_to_claim": "File it in your account.", "claim_url": "https://n.com/pa",
         "source_url": "https://n.com/policy", "no_automated_requests": True, "verified": True}]})
    p = Purchase(store="Nordstrom", order_date=TODAY - timedelta(days=2), email_id="n", sender="x@nordstrom.com",
                 items=[Item("Boots", 150.0)], retailer=book.retailer_for("NORDSTROM"))
    [f] = price_drops([p], _checker({"Boots": 120.0}), TODAY, [])
    assert f.title.startswith("Reminder: ask Nordstrom yourself") and any("ask them yourself" in e for e in f.evidence)
    prep = prepare(f, TODAY)
    assert prep.message is None and prep.script is None and "personally" in prep.steps[0]


def test_store_only_policy_is_low_confidence():
    book = Rulebook.from_data(retailers={"retailers": [
        {"store": "Staples", "match": ["STAPLES"], "adjusts": True, "window_days": 14, "window_from": "purchase",
         "conditions": "Only purchases made in a Staples store qualify.", "exclusions": ["purchases made on staples.com"],
         "how_to_claim": "Bring the receipt to the store.", "claim_url": None, "source_url": "https://s.com", "verified": True}]})
    p = Purchase(store="Staples", order_date=TODAY - timedelta(days=2), email_id="s", sender="x@staples.com",
                 items=[Item("Chair", 200.0)], retailer=book.retailer_for("STAPLES"))
    [f] = price_drops([p], _checker({"Chair": 150.0}), TODAY, [])
    assert f.confidence == "low" and any("in store" in e for e in f.evidence)


def test_limited_settlement_stays_low_and_notice_codes_are_mentioned():
    from clawback.findings.actions import prepare

    raw = dict(RULES["settlements"]["settlements"][0])
    raw.update(id="nv", match=["SEATSELLER"], who_qualifies="NEVADA EVENTS ONLY. Ticket buyers.",
               notes="Online claim needs the Claim ID and PIN from the notice.")
    book = Rulebook.from_data(settlements={"settlements": [raw]})
    [f] = settlement_findings([tx(1, date(2026, 3, 1), "SEATSELLER TIX", 80.0)], [], book.settlements_matching, TODAY)
    assert f.confidence == "low" and any("one state or venue" in e for e in f.evidence)
    assert any("Claim ID / PIN" in step for step in prepare(f, TODAY).steps)


def test_settlement_needs_its_evidence_words_to_count_as_likely():
    # A prescriptions-only class: grocery charges alone shouldn't look like a likely match.
    raw = dict(RULES["settlements"]["settlements"][0])
    raw.update(id="rx", match=["GROCERCO"], evidence_words=["PHARMACY", "RX"])
    book = Rulebook.from_data(settlements={"settlements": [raw]})
    [groceries] = settlement_findings([tx(1, date(2026, 3, 1), "GROCERCO #12", 54.0)], [], book.settlements_matching, TODAY)
    assert groceries.confidence == "low" and any("might not apply" in e for e in groceries.evidence)
    [pharmacy] = settlement_findings([tx(2, date(2026, 3, 1), "GROCERCO PHARMACY #12", 15.0)], [], book.settlements_matching, TODAY)
    assert pharmacy.confidence == "medium"


def test_package_matching_rules_are_used():
    book = rulebook.current()
    if book is None or book.origin != "package":
        pytest.skip("rules package not available")
    assert book.fee_kind_for("ATM FEE REFUND") is None  # refunds and reversals are excluded
    assert book.fee_kind_for("ATM WITHDRAWAL 1234 MAIN ST") is None  # cash, not a fee
    assert book.fee_kind_for("OVERDRAFT ITEM FEE")["kind"] == "overdraft"
    assert book.bill_provider_for("VERIZON WIRELESS PAYMENTS")["provider"] == "Verizon Wireless"  # longest match
    assert book.bill_provider_for("SPECTRUM CABLE") is None  # an unverified row is never used
    assert all(r["verified"] for r in book.retailers + book.bills + book.settlements)
