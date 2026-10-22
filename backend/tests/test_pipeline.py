"""Checks that the demo data produces the flags it was built to produce, with no API keys set."""

from datetime import date, timedelta

import pytest

from clawback import demo_data
from clawback.models import Transaction
from clawback.pipeline.recurring import detect
from clawback.pipeline.run import run
from clawback.sources.statements import parse_csv
from clawback.store import store

TODAY = date(2026, 10, 22)


@pytest.fixture()
def subs(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    u = store.reset("test")
    u.transactions = demo_data.transactions(TODAY)
    u.emails = demo_data.emails(TODAY)
    run("test", TODAY)
    return {s.merchant: s for s in u.subscriptions.values()}


def kinds(sub):
    return {f.kind for f in sub.flags}


def test_finds_subscriptions_and_ignores_noise(subs):
    assert {"Netflix", "Hulu", "Spotify", "DoorDash DashPass", "Google One", "iCloud+",
            "Adobe Creative Cloud", "ChatGPT Plus", "Super Duolingo"} <= set(subs)
    assert not any("Kroger" in m or "Shell" in m or "Chipotle" in m or "Best Buy" in m for m in subs)


def test_flags(subs):
    assert "price_increase" in kinds(subs["Netflix"])
    assert "unused" in kinds(subs["Hulu"])
    assert "membership_losing_money" in kinds(subs["DoorDash DashPass"])
    assert "overlap" in kinds(subs["iCloud+"]) and "overlap" in kinds(subs["Google One"])
    assert "trial_ending" in kinds(subs["Super Duolingo"])
    assert subs["Spotify"].usage.level == "normal" and not kinds(subs["Spotify"]) - {"unknown_usage"}
    assert subs["Adobe Creative Cloud"].usage.needs_checkin


def test_apple_charge_named_from_receipt(subs):
    assert subs["iCloud+"].detected_from == ["bank", "email"]


def test_dashpass_math(subs):
    v = subs["DoorDash DashPass"].value
    assert v.uses == 1 and v.savings == 2.99 and v.net == -7.0


def test_checkin_no_flags_unused(subs):
    u = store.user("test")
    adobe = subs["Adobe Creative Cloud"]
    u.checkins[adobe.id].append((TODAY, False))
    run("test", TODAY)
    assert "unused" in kinds(u.subscriptions[adobe.id])


def test_varying_amounts_are_not_subscriptions():
    txs = [Transaction(id=str(i), date=TODAY - timedelta(days=30 * i), description="GYM CLUB", amount=40 + i * 3)
           for i in range(5)]
    assert detect(txs, TODAY) == []


def test_statement_csv_negative_charges():
    csv_text = "Date,Description,Amount\n2026-10-01,NETFLIX.COM,-17.99\n2026-10-02,PAYROLL,2000.00\n2026-10-03,KROGER,-50.00\n"
    txs = parse_csv(csv_text)
    assert [t.amount for t in txs] == [17.99, -2000.0, 50.0]
