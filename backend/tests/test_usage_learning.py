"""usage-learning: the check-in history changes how strongly ClawBack judges use and how often it asks."""

from datetime import date, timedelta

import pytest

from clawback import demo_data
from clawback.models import Fact, Subscription
from clawback.pipeline.run import run
from clawback.pipeline.usage import (checkin_window, history, keep_holds, signal_trust, signals_for, streak,
                                     summarize)
from clawback.store import store

TODAY = date(2026, 10, 22)


def sub(name="Adobe Creative Cloud", sid="adobe"):
    return Subscription(id=sid, merchant=name, category="software_creative", amount=59.99, monthly_cost=59.99)


def days_ago(n):
    return TODAY - timedelta(days=n)


def usage(checkins, facts=(), trust=None, s=None):
    s = s or sub()
    return summarize(signals_for(s, list(facts), checkins, TODAY, trust), checkins, TODAY)


def fact(kind, n, merchant="Adobe Creative Cloud", eid=None):
    return Fact(email_id=eid or f"{kind}{n}", received=days_ago(n), kind=kind, merchant=merchant)


def test_history_is_sorted_and_accepts_stored_json():
    raw = [[days_ago(3).isoformat(), True], (days_ago(40), False)]
    assert history(raw) == [(days_ago(40), False), (days_ago(3), True)]
    assert streak(history(raw)) == (True, 1)
    assert streak([]) == (None, 0)


def test_two_no_in_a_row_is_strong_unused():
    u = usage([(days_ago(50), False), (days_ago(20), False)])
    assert (u.level, u.strength) == ("none", "strong")
    assert "twice in a row" in u.evidence[0] and "Sep 2 and Oct 2" in u.evidence[0]


def test_one_no_alone_is_not_strong_and_expires():
    assert usage([(days_ago(20), False)]).strength == ""
    assert usage([(days_ago(40), False)]).level == "unknown"  # older than 35 days: ask again


def test_strong_unused_outweighs_engagement_emails_but_not_a_later_order():
    checkins = [(days_ago(50), False), (days_ago(20), False)]
    assert usage(checkins, [fact("engagement", 5), fact("engagement", 12)]).level == "none"
    ordered = usage(checkins, [fact("delivery_order", 5)])
    assert ordered.strength == "" and ordered.evidence[0].endswith("order receipt")  # back to the plain score


def test_a_yes_breaks_the_no_streak():
    u = usage([(days_ago(60), False), (days_ago(45), False), (days_ago(10), True)])
    assert u.level == "normal" and u.strength == ""


def test_three_yes_in_a_row_backs_off_the_checkin():
    three = [(days_ago(100), True), (days_ago(70), True), (days_ago(40), True)]
    assert checkin_window(history(three)) == timedelta(days=90)
    u = usage(three)
    assert u.level == "normal" and not u.needs_checkin  # the last yes is 40 days old but still counts
    assert u.next_checkin == days_ago(40) + timedelta(days=90)
    two = three[1:]
    assert usage(two).level == "unknown" and usage(two).needs_checkin  # two yes: ask monthly as before


def test_backed_off_yes_still_expires():
    old = [(days_ago(200), True), (days_ago(170), True), (days_ago(140), True)]
    assert usage(old).needs_checkin


def test_keep_then_no_reraises():
    kept = days_ago(30)
    assert keep_holds(kept, [], TODAY)
    assert not keep_holds(kept, [(days_ago(10), False)], TODAY)
    assert keep_holds(kept, [(days_ago(10), True)], TODAY)
    assert keep_holds(kept, [(days_ago(30), False)], TODAY)  # a "no" on the keep day itself came before it
    assert not keep_holds(days_ago(100), [], TODAY)  # 90 days are over


def test_per_user_trust_halves_an_email_type_the_user_keeps_contradicting():
    hulu = sub("Hulu", "hulu")
    facts = [fact("inactivity", 80, "Hulu", "i1"), fact("inactivity", 40, "Hulu", "i2")]
    checkins = {"hulu": [(days_ago(75), True), (days_ago(35), True)]}
    trust = signal_trust([hulu], facts, checkins)
    assert trust == {"inactivity_email": 0.5}
    new = [fact("inactivity", 5, "Hulu", "i3")]
    [signal] = signals_for(hulu, new, [], TODAY, trust)
    assert signal.weight == -0.75 and "counted half" in signal.detail


def test_trust_stays_full_when_emails_and_answers_agree():
    hulu = sub("Hulu", "hulu")
    facts = [fact("inactivity", 80, "Hulu", "i1"), fact("inactivity", 40, "Hulu", "i2")]
    assert signal_trust([hulu], facts, {"hulu": [(days_ago(75), False), (days_ago(35), False)]}) == {}


# --- In the pipeline ----------------------------------------------------------------------------------

@pytest.fixture()
def demo():
    u = store.reset("learn")
    u.transactions = demo_data.transactions(TODAY)
    u.emails = demo_data.emails(TODAY)
    run("learn", TODAY)
    return u


def by_merchant(u):
    return {s.merchant: s for s in u.subscriptions.values()}


def test_pipeline_two_no_answers_flag_unused_strongly(demo):
    adobe = by_merchant(demo)["Adobe Creative Cloud"]
    demo.checkins[adobe.id] += [(days_ago(45), False), (days_ago(15), False)]
    run("learn", TODAY)
    adobe = demo.subscriptions[adobe.id]
    assert adobe.usage.strength == "strong"
    [flag] = [f for f in adobe.flags if f.kind == "unused"]
    assert "twice in a row" in flag.message and flag.monthly_savings == 59.99


def test_pipeline_keep_then_no_brings_it_back(demo):
    adobe = by_merchant(demo)["Adobe Creative Cloud"]
    demo.kept[adobe.id] = days_ago(20)
    run("learn", TODAY)
    assert demo.subscriptions[adobe.id].status == "kept"
    assert not any(f.kind == "unknown_usage" for f in demo.subscriptions[adobe.id].flags)

    demo.checkins[adobe.id].append((days_ago(2), False))
    run("learn", TODAY)
    adobe = demo.subscriptions[adobe.id]
    assert adobe.status == "active"
    assert "you kept it on Oct 2, then said you didn't use it" in adobe.usage.evidence[0]
    assert any(f.kind == "unused" for f in adobe.flags)


def test_pipeline_three_yes_stops_asking(demo):
    netflix = by_merchant(demo)["Netflix"]
    demo.checkins[netflix.id] += [(days_ago(95), True), (days_ago(65), True), (days_ago(38), True)]
    run("learn", TODAY)
    netflix = demo.subscriptions[netflix.id]
    assert not netflix.usage.needs_checkin and not any(f.kind == "unknown_usage" for f in netflix.flags)
