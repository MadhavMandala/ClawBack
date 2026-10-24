"""The one-button cancel panel: one verified link, a reminder date, an email only when the merchant takes one, and
"I cancelled it" as the step that starts watching the bank."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from clawback.main import app
from clawback.pipeline import cancel, cancel_lookup
from clawback.pipeline.cancel import primary_link, reminder_on


@pytest.mark.parametrize("next_charge, trial, expected", [
    (date(2026, 11, 19), False, date(2026, 11, 17)),
    (date(2026, 10, 24), True, date(2026, 10, 23)),
    (date(2026, 10, 24), False, date(2026, 10, 23)),  # charge tomorrow -> remind today
    (date(2026, 10, 20), False, None),  # already passed
    (None, False, None),
])
def test_reminder_on(next_charge, trial, expected):
    assert reminder_on(next_charge, trial, date(2026, 10, 23)) == expected


def test_primary_link_prefers_verified_link_and_skips_law():
    links = [{"label": "The law: ROSCA", "url": "https://www.ftc.gov/x", "verified": True},
             {"label": "Apple subscriptions page", "url": "https://apps.apple.com/account/subscriptions", "verified": True}]
    link = primary_link(links, {}, "iCloud+")
    assert link["host"] == "apps.apple.com" and link["label"] == "Cancel on iCloud+"


def test_primary_link_uses_lookup_steps_page():
    links = [{"label": "Cancel Hulu", "url": "https://help.hulu.com/article/hulu-cancel", "verified": True}]
    lookup = {"steps_url": "https://help.hulu.com/article/hulu-how-to-cancel", "verified": True}
    assert primary_link(links, lookup, "Hulu")["url"] == "https://help.hulu.com/article/hulu-cancel"
    assert primary_link([], lookup, "Hulu")["url"] == "https://help.hulu.com/article/hulu-how-to-cancel"


def test_primary_link_falls_back_to_help_page():
    link = primary_link([{"label": "x", "url": "https://evil.example/hulu", "verified": False}], {}, "Hulu")
    assert link["url"] == "https://help.hulu.com/" and link["label"] == "Open Hulu's help page"


def test_primary_link_ignores_unverified_steps_page():
    assert primary_link([], {"steps_url": "https://evil.example/hulu", "verified": False}, "Acme Unknown Co") is None


def test_primary_link_none_when_nothing_verified():
    assert primary_link([], {}, "Acme Unknown Co") is None


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/api/demo/seed")
        yield c


def _hulu(client):
    return next(s for s in client.get("/api/subscriptions").json() if s["merchant"] == "Hulu")


def test_cancel_prep_does_not_mark_cancelling(client):
    hulu = _hulu(client)
    prep = client.post(f"/api/subscriptions/{hulu['id']}/cancel-prep").json()
    assert _hulu(client)["status"] == hulu["status"] != "cancel_pending"
    assert prep["primary_link"]["url"].startswith("https://") and "how_to" in prep and "reminder_on" in prep


def test_cancelled_endpoint_marks_cancelling(client):
    hulu = _hulu(client)
    client.post(f"/api/subscriptions/{hulu['id']}/keep")
    out = client.post(f"/api/subscriptions/{hulu['id']}/cancelled").json()
    assert out["status"] == "cancel_pending"
    assert _hulu(client)["status"] == "cancel_pending"


def _page(support_email):
    return {"merchant": "Hulu", "links": [{"label": "Cancel Hulu", "url": "https://help.hulu.com/article/hulu-cancel",
                                           "verified": True}],
            "steps": ["Sign in.", "Open Account and choose Cancel."],
            "steps_url": "https://help.hulu.com/article/hulu-cancel", "support_email": support_email,
            "checked_on": "2026-10-23", "verified": True, "from_cache": False}


def test_no_email_without_support_address(client, monkeypatch):
    monkeypatch.setattr(cancel_lookup, "lookup", lambda *a, **k: _page(None))
    called = []
    monkeypatch.setattr(cancel, "write_email", lambda *a, **k: called.append(1) or {})
    prep = client.post(f"/api/subscriptions/{_hulu(client)['id']}/cancel-prep").json()
    assert prep["email"] is None and called == []
    assert prep["how_to"][:2] == ["Sign in.", "Open Account and choose Cancel."]
    assert not any("ClawBack checks your bank" in step or "law" in step.lower() for step in prep["how_to"])


def test_email_when_merchant_takes_one(client, monkeypatch):
    monkeypatch.setattr(cancel_lookup, "lookup", lambda *a, **k: _page("cancel@hulu.com"))
    prep = client.post(f"/api/subscriptions/{_hulu(client)['id']}/cancel-prep").json()
    assert prep["email"]["to"] == "cancel@hulu.com" and prep["email"]["subject"]
