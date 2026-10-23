"""The nightly job (python -m clawback.nightly), against the fake Nylas and Plaid."""

from datetime import timedelta

import pytest
from conftest import connect_both, new_session, nylas_message, plaid_tx, sync_page, user_of

from clawback import connect, connections, db, nightly
from clawback.findings import rulebook
from clawback.store import store


@pytest.fixture()
def connected(api, fake):
    h = new_session(api)
    connect_both(api, h)
    return h, user_of(h)


def news(fake) -> None:
    """Overnight: a new trial email and a bank fee."""
    fake.nylas.messages.insert(0, nylas_message("s1", "no-reply@spotify.com", "Your Spotify Premium free trial ends in 5 days",
                                                "Your free trial ends in 5 days. After that you'll be charged $11.99/month.",
                                                days_ago=0.2))
    fake.plaid.sync_pages = [sync_page(added=[plaid_tx("od1", 1, 35.0, "OVERDRAFT ITEM FEE")], cursor="cursor-2")]


def test_refreshes_connected_users_and_alerts_once(api, fake, connected):
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    h, uid = connected
    demo_only = new_session(api)
    news(fake)

    code, line = nightly.run()
    assert code == 0, line
    assert line.startswith("nightly: 1 users refreshed, 0 failed, 2 new alerts, 0 need a new email sign-in")
    assert ("GET", "/v3/grants/grant-1", {}) in fake.nylas.calls  # the grant check
    assert fake.plaid.calls[-1][1]["cursor"] == "cursor-1"  # incremental bank pull
    kinds = sorted(a["kind"] for a in api.get("/api/alerts", headers=h).json()["alerts"])
    assert kinds == ["finding", "flag"]
    assert api.get("/api/alerts", headers=demo_only).json()["alerts"] == []

    code, line = nightly.run()  # twice is safe
    assert code == 0 and " 0 new alerts" in line
    assert len(api.get("/api/alerts", headers=h).json()["alerts"]) == 2
    subs = {s["merchant"] for s in api.get("/api/subscriptions", headers=h).json()}
    assert {"Spotify", "Netflix", "Super Duolingo"} <= subs  # the API sees what the job saved
    assert db.get_meta("nightly_last_run")
    assert api.post("/api/alerts/seen", headers=h).json() == {"ok": True, "marked": 2, "unseen": 0}  # no body: all


def test_lost_grant_is_flagged_and_results_are_kept(api, fake, connected):
    h, uid = connected
    before = {s["merchant"] for s in api.get("/api/subscriptions", headers=h).json()}
    fake.nylas.grant_status = "gone"
    fake.nylas.messages_status = 401
    code, line = nightly.run()
    assert code == 0 and "1 need a new email sign-in" in line and "1 not re-run (mail unreadable)" in line
    email = api.get("/api/connections", headers=h).json()["email"]
    assert email["needs_reconnect"]
    # The mail couldn't be read, so the pipeline wasn't re-run: yesterday's results stay.
    assert {s["merchant"] for s in api.get("/api/subscriptions", headers=h).json()} == before


def test_invalid_grant_counts_too(api, fake, connected):
    fake.nylas.grant_status = "invalid"
    assert "1 need a new email sign-in" in nightly.run()[1]
    assert connections.get(connected[1]).email.needs_reconnect


def test_one_failing_user_does_not_stop_the_others(api, fake, monkeypatch):
    first, second = new_session(api), new_session(api)
    connect_both(api, first)
    api.post("/api/connect/plaid/exchange", headers=second, json={"public_token": "p", "institution": "Bank"})
    bad = user_of(first)
    real = connect.nightly_refresh

    def flaky(user_id):
        if user_id == bad:
            raise RuntimeError("boom")
        return real(user_id)

    monkeypatch.setattr(connect, "nightly_refresh", flaky)
    code, line = nightly.run()
    assert code == 1 and "1 users refreshed, 1 failed" in line and "boom" not in line


def test_demo_mode_users_get_a_grant_check_only(api, fake, connected):
    h, uid = connected
    api.post("/api/demo/seed", headers=h)  # back to the demo; connections stay saved
    syncs = fake.plaid.paths().count("/transactions/sync")
    assert nightly.run()[0] == 0
    assert fake.plaid.paths().count("/transactions/sync") == syncs
    assert store.user(uid).mode == "demo"


def test_redoes_a_user_the_api_saved_meanwhile(api, fake, connected, monkeypatch):
    _, uid = connected
    real, runs = connect.nightly_refresh, []

    def racing(user_id):
        runs.append(user_id)
        result = real(user_id)
        if len(runs) == 1:  # the API saves this user while the job works on it
            db.execute("UPDATE users SET version = version + 1 WHERE id = ?", (user_id,))
        return result

    monkeypatch.setattr(connect, "nightly_refresh", racing)
    news(fake)
    code, line = nightly.run()
    assert code == 0 and runs == [uid, uid]


def test_prunes_idle_sessions(api, fake, connected):
    h, uid = connected
    db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (db.iso(db.now() - timedelta(days=20)), uid))
    code, line = nightly.run()
    assert "1 idle sessions deleted" in line
    assert fake.nylas.deleted == ["grant-1"] and connections.users_with_connections() == []
    assert nightly.run(prune=False)[1].startswith("nightly: 0 users refreshed")


def test_cli_prints_one_line(api, fake, connected, capsys):
    assert nightly.main(["--no-prune"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and out[0].startswith("nightly: 1 users refreshed")


def test_cli_reports_a_broken_job(monkeypatch, capsys):
    def broken():
        raise OSError("disk gone")

    monkeypatch.setattr(db, "connection", broken)
    assert nightly.main([]) == 2
    assert capsys.readouterr().out.startswith("nightly: could not run (OSError")
