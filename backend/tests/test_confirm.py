"""cancel-confirmation and recovered-history: did the charge stop, did the refund arrive, and the dated history."""

from datetime import date, timedelta

import pytest

from clawback import demo_data
from clawback.findings import rulebook
from clawback.models import Finding, Transaction
from clawback.pipeline import confirm
from clawback.pipeline.recovered import history, totals
from clawback.pipeline.run import run, summary
from clawback.store import store

TODAY = date(2026, 10, 22)


def days_ago(n):
    return TODAY - timedelta(days=n)


def netflix(last_days_ago: int, n: int = 5, desc="NETFLIX.COM 866-579-7172 CA"):
    return [Transaction(id=f"nf{k}", date=days_ago(last_days_ago + 30 * k), description=desc, amount=17.99)
            for k in range(n)]


def fresh(user, txs):
    u = store.reset(user)
    store.use_real_data(user)
    u.transactions = list(txs)
    return u


def nf(u):
    return next(s for s in u.subscriptions.values() if s.merchant == "Netflix")


# --- Cancellations ------------------------------------------------------------------------------------

def test_waiting_until_the_next_charge_is_due():
    u = fresh("c1", netflix(10))
    u.cancel_pending["merchant-netflix"] = days_ago(5)
    run("c1", TODAY)
    s = nf(u)
    assert s.status == "cancel_pending" and s.cancellation.status == "pending"
    assert s.cancellation.expected_by == days_ago(10) + timedelta(days=30 + 6)
    assert [f.kind for f in s.flags][:1] == ["cancel_pending"]
    assert "cancel:merchant-netflix" not in u.recovered


def test_no_charge_by_the_due_date_plus_grace_is_confirmed():
    u = fresh("c2", netflix(40))
    u.cancel_pending["merchant-netflix"] = days_ago(35)
    run("c2", TODAY)
    s = nf(u)
    assert s.status == "cancelled" and s.cancellation.status == "confirmed"
    assert s.cancellation.confirmed_on == days_ago(40) + timedelta(days=36)
    assert [f.kind for f in s.flags] == ["cancel_confirmed"]
    sm = summary("c2")
    assert sm["subscriptions"] == 0 and sm["monthly_total"] == 0 and sm["cancelled"] == 1
    assert sm["cancelled_monthly_savings"] == 17.99
    event = u.recovered["cancel:merchant-netflix"]
    assert (event.kind, event.status, event.monthly, event.amount) == ("cancelled_subscription", "confirmed", 17.99, 17.99)


def test_charge_after_starting_to_cancel_is_flagged_plainly():
    u = fresh("c3", netflix(3))
    u.cancel_pending["merchant-netflix"] = days_ago(10)  # cancelling started, then Netflix charged 3 days ago
    run("c3", TODAY)
    s = nf(u)
    assert s.status == "cancel_pending" and s.cancellation.status == "charged_again"
    [flag] = [f for f in s.flags if f.kind == "charged_after_cancel"]
    assert flag.severity == "high" and flag.message.startswith("Charged again after you started cancelling: $17.99")
    assert flag.monthly_savings == 17.99


def test_charged_once_more_then_stopped_is_confirmed_with_a_note():
    u = fresh("c4", netflix(45))
    u.cancel_pending["merchant-netflix"] = days_ago(50)  # the 45-days-ago charge came after starting
    run("c4", TODAY)
    c = nf(u).cancellation
    assert c.status == "confirmed" and c.charged_again_on == days_ago(45) and "charged once more" in c.note


def test_same_day_charge_counts_as_before():
    u = fresh("c5", netflix(10))
    u.cancel_pending["merchant-netflix"] = days_ago(10)
    run("c5", TODAY)
    assert nf(u).cancellation.status == "pending"


def test_confirmed_cancellation_survives_charges_rolling_out_of_the_bank_window():
    u = fresh("c6", netflix(40))
    u.cancel_pending["merchant-netflix"] = days_ago(35)
    run("c6", TODAY)
    u.transactions = []  # Plaid's window moved on
    run("c6", TODAY + timedelta(days=200))
    s = u.subscriptions["merchant-netflix"]
    assert s.status == "cancelled" and s.cancellation.status == "confirmed"
    assert "cancel:merchant-netflix" in u.recovered


def test_new_charge_after_confirmation_reopens_it():
    u = fresh("c7", netflix(40))
    u.cancel_pending["merchant-netflix"] = days_ago(35)
    run("c7", TODAY)
    u.transactions.append(Transaction(id="again", date=TODAY, description="NETFLIX.COM", amount=17.99))
    run("c7", TODAY)
    s = nf(u)
    assert s.cancellation.status == "charged_again" and "cancel:merchant-netflix" not in u.recovered


def test_keep_drops_the_cancellation_and_its_history():
    u = fresh("c8", netflix(40))
    u.cancel_pending["merchant-netflix"] = days_ago(35)
    run("c8", TODAY)
    u.cancel_pending.pop("merchant-netflix")
    u.kept["merchant-netflix"] = TODAY
    run("c8", TODAY)
    assert not u.cancellations and not u.recovered


def test_cancelled_trial_is_confirmed_when_no_first_charge_comes():
    u = store.reset("c9")
    u.transactions = demo_data.transactions(TODAY)
    u.emails = demo_data.emails(TODAY)
    u.cancel_pending["super-duolingo"] = TODAY
    run("c9", TODAY)
    duo = u.subscriptions["super-duolingo"]
    assert duo.status == "cancel_pending" and duo.cancellation.series_key == "merchant:Super Duolingo"
    later = TODAY + timedelta(days=12)
    run("c9", later)
    assert u.cancellations["super-duolingo"].status == "confirmed"


def test_apple_series_cancellation_watches_only_that_amount():
    """Cancelling one app billed through Apple: another app's APPLE.COM/BILL charge isn't a charge again."""
    calm = [Transaction(id=f"c{k}", date=days_ago(40 + 30 * k), description="APPLE.COM/BILL", amount=16.04)
            for k in range(4)]
    other = [Transaction(id=f"o{k}", date=days_ago(2 + 30 * k), description="APPLE.COM/BILL", amount=2.99)
             for k in range(4)]
    u = fresh("c10", calm + other)
    u.cancel_pending["apple-bill-16-04"] = days_ago(35)
    run("c10", TODAY)
    assert u.cancellations["apple-bill-16-04"].status == "confirmed"


# --- Refunds for done findings ------------------------------------------------------------------------

def finding(kind="duplicate_charge", amount=129.99, merchant="Best Buy", **details):
    base = {"duplicate_charge": {"description": "BEST BUY 00012345 ATLANTA", "charges": [days_ago(9).isoformat()] * 2},
            "bank_fee": {"description": "OVERDRAFT ITEM FEE", "date": days_ago(17).isoformat()},
            "price_drop": {"store": "Target", "order_date": days_ago(6).isoformat()},
            "flight_refund": {"airline": "United"},
            "settlement": {}}[kind]
    return Finding(id=f"{kind}-x", category="charges", kind=kind, merchant=merchant, title="t", message="m",
                   amount=amount, found_on=TODAY, details={**base, **details})


def watch_and_check(user, f, credits, got_back=0.0, done=TODAY):
    u = fresh(user, credits)
    u.findings = {f.id: f}
    confirm.mark_done(u, f, got_back, done)
    confirm.check_refunds(u, TODAY)
    return u


def credit(desc, amount, n=1, tid=None):
    return Transaction(id=tid or f"cr-{desc[:6]}-{n}", date=days_ago(n), description=desc, amount=-amount)


def test_duplicate_charge_refund_is_confirmed():
    u = watch_and_check("r1", finding(), [credit("BEST BUY 00012345 ATLANTA", 129.99)], done=days_ago(3))
    w = u.refund_watch["duplicate_charge-x"]
    assert w.status == "confirmed" and w.confirmed_amount == 129.99 and "BEST BUY" in w.confirmed_from
    f = u.findings["duplicate_charge-x"]
    assert f.confirmed_amount == 129.99 and f.confirmed_on == days_ago(1)
    assert totals(u)["confirmed"] == 129.99


def test_bank_fee_reversal_needs_refund_and_fee_words():
    f = finding("bank_fee", 35.0, "Your bank")
    assert watch_and_check("r2", f, [credit("OVERDRAFT FEE REVERSAL", 35.0)]).refund_watch[f.id].status == "confirmed"
    assert watch_and_check("r3", f, [credit("ZELLE FROM MOM", 35.0)]).refund_watch[f.id].status == "waiting"


def test_price_drop_refund_may_include_tax():
    f = finding("price_drop", 30.0, "Target")
    assert watch_and_check("r4", f, [credit("TARGET 00011111 ATLANTA", 32.40)]).refund_watch[f.id].status == "confirmed"
    assert watch_and_check("r5", f, [credit("TARGET 00011111 ATLANTA", 45.00)]).refund_watch[f.id].status == "waiting"


def test_self_reported_amount_also_matches():
    f = finding("flight_refund", 412.40, "United")
    u = watch_and_check("r6", f, [credit("UNITED AIRLINES REFUND", 380.00)], got_back=380.0)
    assert u.refund_watch[f.id].status == "confirmed"


def test_wrong_merchant_or_too_early_does_not_match():
    f = finding()
    assert watch_and_check("r7", f, [credit("AMAZON MKTPL REFUND", 129.99)]).refund_watch[f.id].status == "waiting"
    early = credit("BEST BUY 00012345 ATLANTA", 129.99, n=12)  # before the duplicate charge itself
    assert watch_and_check("r8", f, [early]).refund_watch[f.id].status == "waiting"
    late_done = watch_and_check("r9", f, [credit("BEST BUY 00012345 ATLANTA", 129.99, n=6)], done=days_ago(0))
    assert late_done.refund_watch[f.id].status == "confirmed"  # within the 7 days before marking it done
    too_old = watch_and_check("r9b", f, [credit("BEST BUY 00012345 ATLANTA", 129.99, n=8)], done=days_ago(0))
    assert too_old.refund_watch[f.id].status == "waiting"


def test_settlement_payout_any_amount_but_must_name_it():
    f = finding("settlement", 0.0, "The Kroger Co.")
    assert watch_and_check("s1", f, [credit("KROGER SETTLEMENT PAYMENT", 12.34)]).refund_watch[f.id].status == "confirmed"
    assert watch_and_check("s2", f, [credit("KROGER #0412 REFUND", 12.34)]).refund_watch[f.id].status == "waiting"


def test_one_credit_confirms_one_finding():
    a, b = finding(), finding()
    b.id = "duplicate_charge-y"
    u = fresh("r10", [credit("BEST BUY 00012345 ATLANTA", 129.99)])
    u.findings = {a.id: a, b.id: b}
    confirm.mark_done(u, a, 0, TODAY)
    confirm.mark_done(u, b, 0, TODAY)
    assert confirm.check_refunds(u, TODAY) == 1


def test_eur_compensation_stays_self_reported():
    f = finding("flight_refund", 250.0, "Lufthansa")
    f.currency = "EUR"
    u = watch_and_check("r11", f, [credit("LUFTHANSA REFUND", 250.0)], got_back=250.0)
    assert u.refund_watch[f.id].status == "waiting"
    t = totals(u)
    assert t["confirmed"] == 0 and t["self_reported"] == 250.0


def test_dismissing_a_done_finding_drops_its_watch():
    f = finding()
    u = watch_and_check("r12", f, [credit("BEST BUY 00012345 ATLANTA", 129.99)])
    u.finding_status[f.id] = "dismissed"
    confirm.check_refunds(u, TODAY)
    assert not u.refund_watch and "refund:" + f.id not in u.recovered


def test_confirmed_refund_replaces_the_self_reported_amount():
    f = finding()
    u = fresh("r13", [])
    u.findings = {f.id: f}
    confirm.mark_done(u, f, 129.99, days_ago(2))
    assert totals(u) == {**totals(u), "confirmed": 0, "self_reported": 129.99}
    u.transactions.append(credit("BEST BUY 00012345 ATLANTA", 129.99))
    confirm.check_refunds(u, TODAY)
    t = totals(u)
    assert (t["confirmed"], t["self_reported"]) == (129.99, 0)
    [event] = history("r13")["events"]
    assert event["kind"] == "refund" and event["status"] == "confirmed" and "BEST BUY" in event["note"]


# --- The demo and the API ------------------------------------------------------------------------------

def test_demo_numbers_stay_and_calm_is_a_confirmed_cancellation(client):
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    s = client.post("/api/demo/seed").json()
    assert (s["monthly_total"], s["potential_monthly_savings"], s["owed_total"], s["owed_count"]) == (
        672.23, 250.97, 615.06, 7)  # includes the unused $169.00 Orangetheory membership
    assert s["recovered_total"] == 0 and s["cancelled_monthly_savings"] == 16.04
    subs = {x["merchant"]: x for x in client.get("/api/subscriptions").json()}
    calm = subs["Calm"]
    assert calm["status"] == "cancelled" and calm["billed_by"] == "apple"
    assert calm["matched_from"].startswith("Matched from the Apple receipt") and "$1.05 tax" in calm["matched_from"]
    assert calm["cancellation"]["status"] == "confirmed" and calm["cancellation"]["skipped_charges"] == 2
    assert "series_key" not in calm
    rec = client.get("/api/recovered").json()
    assert set(rec) == {"totals", "note", "events"}
    assert rec["totals"]["cancelled_monthly"] == 16.04 and rec["totals"]["cancelled_saved"] == 32.08
    assert [e["kind"] for e in rec["events"]] == ["cancelled_subscription"]


def test_demo_refund_is_confirmed_on_the_next_sync(client):
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    client.post("/api/demo/seed")
    dup = next(f for f in client.get("/api/findings").json() if f["kind"] == "duplicate_charge")
    client.post(f"/api/findings/{dup['id']}/done", json={"got_back": 129.99})
    before = client.get("/api/summary").json()
    assert before["recovered_self_reported"] == 129.99 and before["recovered_confirmed"] == 0
    assert "Self-reported" in before["recovered_note"]

    client.post("/api/sync")
    after = client.get("/api/summary").json()
    assert after["recovered_confirmed"] == 129.99 and after["recovered_self_reported"] == 0
    assert after["recovered_total"] == 129.99 and "Confirmed in your bank data" in after["recovered_note"]
    found = {f["id"]: f for f in client.get("/api/findings").json()}
    assert found[dup["id"]]["confirmed_amount"] == 129.99 and "DEMO REFUND" in found[dup["id"]]["confirmed_from"]
    kinds = [e["kind"] for e in client.get("/api/recovered").json()["events"]]
    assert sorted(kinds) == ["cancelled_subscription", "refund"]


def test_cancelling_an_unmatched_apple_charge_keeps_watching_once_a_receipt_names_it():
    from datetime import datetime, timezone

    from clawback.models import Email

    charges = [Transaction(id=f"a{k}", date=days_ago(40 + 30 * k), description="APPLE.COM/BILL", amount=16.04)
               for k in range(4)]
    u = fresh("c11", charges)
    u.cancel_pending["apple-bill-16-04"] = days_ago(35)
    run("c11", TODAY)  # no receipt yet: "Apple (unmatched)"
    assert u.cancellations["apple-bill-16-04"].merchant == "Apple (unmatched)"
    d = charges[0].date - timedelta(days=1)
    body = (f"Receipt\n{d:%B} {d.day}, {d.year}\nOrder ID: MT4KX2P90Z\nApp Store\nCalm: Sleep & Meditation\n"
            "Calm Premium (Monthly)\n$14.99\nSubtotal $14.99\nTax $1.05\nVisa •••• 4242 $16.04")
    u.emails = [Email(id="late", received_at=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                      sender="no_reply@email.apple.com", subject="Your receipt from Apple.", body_text=body)]
    run("c11", TODAY)
    s = u.subscriptions["apple-bill-16-04"]
    assert s.merchant == "Calm" and s.status == "cancelled" and len(u.subscriptions) == 1
    assert u.recovered["cancel:apple-bill-16-04"].merchant == "Calm"
