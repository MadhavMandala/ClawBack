"""Per-visitor sessions (sessions.py), GET / DELETE /api/me, and the daily model spend caps (budget.py)."""

import json
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
from conftest import new_session, user_of
from fastapi.testclient import TestClient

from clawback import budget, config, connections, db, demo, llm, sessions
from clawback.sources import net
from clawback.store import store

EXPIRED = {"detail": "session expired"}


def db_bytes() -> bytes:
    path = config.settings.db_path
    return b"".join(p.read_bytes() for p in (path, path.with_name(path.name + "-wal")) if p.exists())


# --- Sessions -------------------------------------------------------------------------------------------

def test_each_visitor_gets_their_own_demo(api):
    a, b = new_session(api), new_session(api)
    assert a != b and len(a[sessions.HEADER]) >= 40
    subs_a = api.get("/api/subscriptions", headers=a).json()
    assert len(subs_a) >= 9 and len(api.get("/api/subscriptions", headers=b).json()) == len(subs_a)

    hulu = next(s for s in subs_a if s["merchant"] == "Hulu")
    assert api.post(f"/api/subscriptions/{hulu['id']}/keep", headers=a).json()["status"] == "kept"
    statuses = {s["merchant"]: s["status"] for s in api.get("/api/subscriptions", headers=b).json()}
    assert statuses["Hulu"] != "kept"  # b's demo is untouched
    assert api.get("/api/trace", headers=a).json() and api.get("/api/findings", headers=b).json()


def test_missing_unknown_or_malformed_sessions_get_401(api):
    for headers in ({}, {sessions.HEADER: "nope"}, {sessions.HEADER: "x" * 43}, {sessions.HEADER: "y" * 500}):
        r = api.get("/api/summary", headers=headers)
        assert r.status_code == 401 and r.json() == EXPIRED
    # Routes with no personal data need no session.
    assert api.get("/api/health").json()["sessions"] == "visitor"
    assert api.get("/api/features").status_code == 200 and api.get("/api/missing").status_code == 200


def test_session_id_is_only_stored_as_a_hash(api):
    h = new_session(api)
    token = h[sessions.HEADER]
    user = user_of(h)
    assert user.startswith("u_") and token not in user
    assert token.encode() not in db_bytes()
    assert db.one("SELECT COUNT(*) AS n FROM sessions")["n"] == 1


def test_sessions_and_choices_survive_a_restart(visitor):
    from clawback.main import app

    with TestClient(app) as c:
        h = new_session(c)
        hulu = next(s for s in c.get("/api/subscriptions", headers=h).json() if s["merchant"] == "Hulu")
        c.post(f"/api/subscriptions/{hulu['id']}/checkin", headers=h, json={"used": True})
        c.post(f"/api/subscriptions/{hulu['id']}/keep", headers=h)
    store.clear()  # a restart: memory is gone, the file stays
    demo.clear()
    db.close()
    with TestClient(app) as c:
        subs = {s["merchant"]: s for s in c.get("/api/subscriptions", headers=h).json()}
        assert subs["Hulu"]["status"] == "kept"
        assert store.user(user_of(h)).checkins[hulu["id"]]


def test_new_sessions_are_limited_per_address(api, monkeypatch):
    monkeypatch.setattr(config.settings, "sessions_per_ip_hour", 2)
    new_session(api), new_session(api)
    r = api.post("/api/session")
    assert r.status_code == 429 and "Try again in an hour" in r.json()["detail"]
    assert "testclient" not in db_bytes().decode("latin-1")  # addresses are stored as keyed hashes only


def test_idle_sessions_expire_and_are_pruned(api, fake):
    old, fresh = new_session(api), new_session(api)
    api.post("/api/connect/plaid/exchange", headers=old, json={"public_token": "p", "institution": "Bank"})
    stale = db.iso(db.now() - timedelta(days=15))
    db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (stale, _uid(old)))
    assert api.get("/api/summary", headers=old).json() == EXPIRED

    result = sessions.prune()
    assert result["sessions"] == 1 and result["with_connections"] == 1
    assert fake.plaid.paths()[-1] == "/item/remove"  # its bank connection was ended at Plaid
    assert connections.users_with_connections() == []
    assert api.get("/api/summary", headers=fresh).status_code == 200
    assert db.one("SELECT COUNT(*) AS n FROM users")["n"] == 1


def _uid(headers: dict) -> str:
    h = sessions._hash(headers[sessions.HEADER])
    return db.one("SELECT user_id FROM sessions WHERE token_hash = ?", (h,))["user_id"]


def test_last_seen_is_touched_but_not_on_every_request(api):
    h = new_session(api)
    uid = _uid(h)
    db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (db.iso(db.now() - timedelta(hours=1)), uid))
    api.get("/api/summary", headers=h)
    first = db.one("SELECT last_seen FROM users WHERE id = ?", (uid,))["last_seen"]
    assert db.now() - sessions._parse(first) < timedelta(minutes=1)
    api.get("/api/summary", headers=h)
    assert db.one("SELECT last_seen FROM users WHERE id = ?", (uid,))["last_seen"] == first


def test_single_user_mode_needs_no_session(client):
    assert client.post("/api/session").json() == {"session_id": "single-user"}
    assert client.get("/api/summary").status_code == 200
    assert client.get("/api/summary", headers={sessions.HEADER: "anything"}).status_code == 200
    assert client.get("/api/me").json()["session"]["kind"] == "single"


def test_demo_is_built_once_and_copied(api, fake_llm):
    a = new_session(api)
    calls = len(fake_llm.calls)
    assert calls > 0  # the demo emails went to the (fake) model once
    b = new_session(api)
    assert len(fake_llm.calls) == calls  # the second visitor got a copy
    trace_b = api.get("/api/trace", headers=b).json()
    assert any(t["tier"] == "fast" for t in trace_b)  # and still sees which model did what
    assert api.get("/api/summary", headers=a).json() == api.get("/api/summary", headers=b).json()
    assert budget.spent(demo.TEMPLATE_USER) > 0 and budget.spent(user_of(b)) == 0


# --- The email sign-in returns to the right session --------------------------------------------------

def test_email_callback_lands_on_the_session_that_started_it(api, fake):
    a, b = new_session(api), new_session(api)
    url = api.get("/api/connect/email", headers=b).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = api.get("/api/connect/email/callback", params={"code": "good-code", "state": state}, follow_redirects=False)
    assert r.headers["location"] == "http://localhost:3000/dashboard?connected=email"

    assert api.get("/api/connections", headers=b).json()["email"]["connected"] is True
    assert api.get("/api/connections", headers=b).json()["mode"] == "real"
    status_a = api.get("/api/connections", headers=a).json()
    assert status_a["mode"] == "demo" and status_a["email"]["connected"] is False
    assert connections.find_user("email", "grant-1") == _uid(b)
    # The pull happened inside b's request scope, so it was saved.
    store.clear()
    assert store.user(_uid(b)).mode == "real" and store.user(_uid(b)).subscriptions


# --- GET and DELETE /api/me -------------------------------------------------------------------------

def connect_both(api, h) -> None:
    api.post("/api/connect/plaid/exchange", headers=h, json={"public_token": "p", "institution": "First Platypus Bank"})
    url = api.get("/api/connect/email", headers=h).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    api.get("/api/connect/email/callback", params={"code": "good-code", "state": state}, follow_redirects=False)


def test_me_shows_the_session_without_secrets(api, fake):
    h = new_session(api)
    me = api.get("/api/me", headers=h).json()
    assert me["session"]["kind"] == "visitor" and me["session"]["created_at"] and me["mode"] == "demo"
    assert me["counts"]["subscriptions"] >= 9 and me["counts"]["emails"] > 0 and me["counts"]["findings"] > 0
    assert me["session"]["deleted_after_idle_days"] == 14 and me["model_daily_limit_usd"] == 0.25

    connect_both(api, h)
    me = api.get("/api/me", headers=h).json()
    assert me["mode"] == "real"
    assert me["connections"]["email"] == {"connected": True, "account": "me@example.com", "provider": "google",
                                          "needs_reconnect": False}
    assert me["connections"]["plaid"]["institution"] == "First Platypus Bank"
    dumped = json.dumps(me)
    for secret in ("grant-1", "access-sandbox-1", "item-1", h[sessions.HEADER], _uid(h)):
        assert secret not in dumped


def test_delete_my_data_removes_everything(api, fake):
    h, other = new_session(api), new_session(api)
    connect_both(api, h)
    uid = _uid(h)
    r = api.delete("/api/me", headers=h).json()
    assert r["ok"] is True
    assert r["removed"]["email_connection"] == "deleted at Nylas" and r["removed"]["bank_connection"] == "removed at Plaid"
    assert r["removed"]["emails"] == 4 and r["removed"]["transactions"] == 7
    assert fake.nylas.deleted == ["grant-1"] and "/item/remove" in fake.plaid.paths()

    for table, column in (("users", "id"), ("sessions", "user_id"), ("connections", "user_id"),
                          ("alerts", "user_id"), ("spend", "user_id")):
        assert db.one(f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?", (uid,))["n"] == 0, table
    assert api.get("/api/summary", headers=h).json() == EXPIRED  # the frontend then starts a new session
    assert api.get("/api/summary", headers=other).status_code == 200


def test_delete_still_works_when_the_providers_fail(api, fake, monkeypatch):
    h = new_session(api)
    connect_both(api, h)

    def offline(request):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(net, "transport", httpx.MockTransport(offline))
    r = api.delete("/api/me", headers=h).json()
    assert r["ok"] and "didn't confirm" in r["removed"]["email_connection"]
    assert "didn't confirm" in r["removed"]["bank_connection"]
    assert connections.users_with_connections() == []


def test_single_user_delete_starts_over(client):
    client.post("/api/demo/seed")
    assert client.delete("/api/me").json()["ok"] is True
    assert client.get("/api/subscriptions").json() == []  # empty until "Reset demo"
    assert client.post("/api/demo/seed").json()["subscriptions"] >= 9


# --- Daily model spend caps ----------------------------------------------------------------------------

SCHEMA = {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"],
          "additionalProperties": False}
MESSAGES = [{"role": "user", "content": "hi"}]
ONE_CALL = 100 / 1e6 * 0.06 + 20 / 1e6 * 0.24  # what a FakeLLM reply costs on the fast tier


def test_session_cap_skips_the_call_and_says_so(fake_llm, monkeypatch):
    monkeypatch.setattr(config.settings, "session_daily_usd", ONE_CALL / 2)
    fake_llm.default = '{"kind": "trial"}'
    assert llm.chat_json("u1", "extract", "fast", MESSAGES, SCHEMA)[0] == {"kind": "trial"}
    assert budget.spent("u1") > 0

    calls = len(fake_llm.calls)
    assert llm.chat_json("u1", "extract", "fast", MESSAGES, SCHEMA) == (None, None)  # callers use their rules
    assert llm.chat_json("u1", "extract", "fast", MESSAGES, SCHEMA) == (None, None)
    assert len(fake_llm.calls) == calls  # refused before calling, backups included
    skipped = [t for t in store.user("u1").trace if t.status == "skipped"]
    assert len(skipped) == 1 and skipped[0].note.startswith("daily model limit reached") and skipped[0].note.endswith("(x2)")
    assert not [t for t in store.user("u1").trace if t.status == "fallback"]

    assert llm.chat_json("u2", "extract", "fast", MESSAGES, SCHEMA)[0]  # other sessions aren't affected
    assert llm.chat_json(demo.TEMPLATE_USER, "extract", "fast", MESSAGES, SCHEMA)[0]  # system users are exempt


def test_global_cap_stops_everyone(fake_llm, monkeypatch):
    monkeypatch.setattr(config.settings, "global_daily_usd", ONE_CALL * 1.5)
    fake_llm.default = '{"kind": "trial"}'
    llm.chat_json("u1", "extract", "fast", MESSAGES, SCHEMA)
    llm.chat_json("u2", "extract", "fast", MESSAGES, SCHEMA)
    for user in ("u3", demo.TEMPLATE_USER):
        assert llm.chat_json(user, "extract", "fast", MESSAGES, SCHEMA) == (None, None)
    assert "all users" in [t for t in store.user("u3").trace if t.status == "skipped"][0].note


def test_caps_can_be_turned_off(fake_llm, monkeypatch):
    monkeypatch.setattr(config.settings, "session_daily_usd", 0)
    monkeypatch.setattr(config.settings, "global_daily_usd", 0)
    budget.add("u1", 100.0)
    assert budget.blocked("u1") is None


def test_capped_demo_falls_back_to_rules(api, fake_llm, monkeypatch):
    monkeypatch.setattr(config.settings, "global_daily_usd", 0.000001)
    budget.add("someone", 1.0)  # today's budget is already spent
    h = new_session(api)
    assert fake_llm.calls == []
    assert len(api.get("/api/subscriptions", headers=h).json()) >= 9  # the rules still find the demo story
    trace = api.get("/api/trace", headers=h).json()
    assert any(t["status"] == "skipped" and "daily model limit" in t["note"] for t in trace)


def test_deleted_users_spend_still_counts_globally(api):
    h = new_session(api)
    uid = _uid(h)
    budget.add(uid, 0.10)
    total = budget.spent_all()
    api.delete("/api/me", headers=h)
    assert budget.spent(uid) == 0 and budget.spent_all() == total
