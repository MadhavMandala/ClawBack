"""The demo month has to hold up on every day someone might open it: from now through the end of judging (Dec 15),
plus a day. Each day it must show all five areas and the stories the video and the write-up rely on."""

from datetime import date, timedelta

import pytest

from clawback import demo

FIRST, LAST = date(2026, 10, 24), date(2026, 12, 16)
DAYS = [FIRST + timedelta(days=i) for i in range((LAST - FIRST).days + 1)]
FINDING_KINDS = {"price_drop", "duplicate_charge", "flight_refund", "bank_fee", "settlement"}


@pytest.fixture(scope="module", autouse=True)
def fresh_template():
    demo.clear()
    yield
    demo.clear()


@pytest.mark.parametrize("today", DAYS, ids=[d.isoformat() for d in DAYS])
def test_demo_holds_up(today):
    demo.clear()
    u = demo.template(today)
    open_kinds = {f.kind for f in u.findings.values() if f.status == "open"}
    assert FINDING_KINDS <= open_kinds, f"missing {FINDING_KINDS - open_kinds}"

    subs = {s.merchant: s for s in u.subscriptions.values()}
    assert "iCloud+" in subs, f"iCloud+ not named: {sorted(subs)}"
    assert not any("unmatched" in m for m in subs)
    assert "overlap" in {f.kind for f in subs["iCloud+"].flags}
    assert "unused" in {f.kind for f in subs["Hulu"].flags}
    gym = subs["Orangetheory Fitness"]
    assert "unused" in {f.kind for f in gym.flags} and gym.usage.evidence[0].endswith("(Google Maps)")
    assert "membership_losing_money" in {f.kind for f in subs["DoorDash DashPass"].flags}
    assert any(s.kind == "bill" for s in subs.values())
