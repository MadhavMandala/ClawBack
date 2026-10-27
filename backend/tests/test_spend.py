"""The dashboard donut: monthly spend in at most six groups, the part you could cut, and trials about to start."""

from datetime import date

import pytest

from clawback import demo_data
from clawback.models import Flag, Subscription
from clawback.pipeline.run import run, summary
from clawback.pipeline.spend import could_cut, spend_groups, trial_notes
from clawback.store import store

TODAY = date(2026, 10, 22)


@pytest.fixture(autouse=True)
def demo():
    u = store.reset("test")
    u.transactions = demo_data.transactions(TODAY)
    u.emails = demo_data.emails(TODAY)
    run("test", TODAY)
    return u


def sub(id: str, category: str, cost: float, saving: float = 0.0, status: str = "active") -> Subscription:
    flags = [Flag(kind="unused", severity="high", message="x", monthly_savings=saving)] if saving else []
    return Subscription(id=id, merchant=id.title(), category=category, monthly_cost=cost, flags=flags, status=status)


def test_demo_groups_match_month_sentence():
    s = summary("test", TODAY)
    groups = s["spend_groups"]
    assert [g["label"] for g in groups][:3] == ["Home and phone", "Gym and fitness", "Insurance"]
    assert round(sum(g["monthly"] for g in groups), 2) == s["monthly_total"]
    assert len(groups) <= 6


def test_yellow_plus_trials_equals_potential_savings():
    s = summary("test", TODAY)
    cut = sum(g["could_cut"] for g in s["spend_groups"]) + sum(t["amount"] for t in s["trials"])
    assert round(cut, 2) == s["potential_monthly_savings"]


def test_trial_note_for_duolingo():
    [t] = summary("test", TODAY)["trials"]
    assert t["merchant"] == "Super Duolingo" and t["amount"] == 12.99


def test_kept_item_cuts_nothing(demo):
    hulu = next(s for s in demo.subscriptions.values() if s.merchant == "Hulu")
    before = next(g for g in summary("test", TODAY)["spend_groups"] if g["label"] == "Streaming")["could_cut"]
    demo.kept[hulu.id] = TODAY
    run("test", TODAY)
    after = next(g for g in summary("test", TODAY)["spend_groups"] if g["label"] == "Streaming")["could_cut"]
    assert round(before - after, 2) == 9.99


def test_could_cut_capped_at_cost():
    assert could_cut(sub("a", "music", 5.0, saving=9.0)) == 5.0


def test_more_than_six_groups_merge_into_other():
    cats = ["internet", "insurance", "software", "video_streaming", "cloud_storage", "delivery_membership",
            "fitness", "news"]
    subs = [sub(f"s{i}", c, 100.0 - i * 10) for i, c in enumerate(cats)]
    groups = spend_groups(subs)
    assert len(groups) == 6 and groups[-1]["label"] == "Other"
    assert round(sum(g["monthly"] for g in groups), 2) == round(sum(s.monthly_cost for s in subs), 2)


def test_spend_groups_empty_and_single():
    assert spend_groups([]) == []
    [g] = spend_groups([sub("netflix", "video_streaming", 17.99)])
    assert g["label"] == "Streaming" and g["items"][0]["monthly"] == 17.99


def test_trials_and_cancelled_are_not_spend():
    subs = [sub("a", "music", 10.0, status="trial"), sub("b", "music", 10.0, status="cancelled")]
    assert spend_groups(subs) == []


def test_past_or_undated_trial_has_no_note():
    t = sub("t", "education", 12.99, status="trial")
    assert trial_notes([t], TODAY) == []
    t.next_expected = date(2026, 10, 1)
    assert trial_notes([t], TODAY) == []


def test_sentence_matches_donut_after_a_trial_date_passes():
    later = date(2026, 10, 25)  # the demo trial ended Oct 23; no bank charge seen yet, so it's still a trial
    s = summary("test", later)
    assert s["trials"] == []
    cut = sum(g["could_cut"] for g in s["spend_groups"]) + sum(t["amount"] for t in s["trials"])
    assert round(cut, 2) == s["potential_monthly_savings"]


def test_sentence_savings_are_capped_like_the_donut(demo):
    hulu = next(s for s in demo.subscriptions.values() if s.merchant == "Hulu")
    hulu.flags[0].monthly_savings = 500.0  # a saving bigger than the price
    s = summary("test", TODAY)
    cut = sum(g["could_cut"] for g in s["spend_groups"]) + sum(t["amount"] for t in s["trials"])
    assert round(cut, 2) == s["potential_monthly_savings"]
