"""Persistence (store.py, db.py), encryption at rest (crypto.py) and saved connections in the database."""

import dataclasses
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import pytest
from conftest import TEST_KEY

from clawback import config, connect, connections, crypto, db, demo
from clawback.connections import EmailConnection, PlaidConnection, now
from clawback.models import Email
from clawback.store import SaveConflict, UserData, deserialize, serialize, store

TODAY = date(2026, 10, 22)


def db_bytes() -> bytes:
    path = config.settings.db_path
    return b"".join(p.read_bytes() for p in (path, path.with_name(path.name + "-wal")) if p.exists())


def make_row(user_id: str, kind: str = "visitor") -> None:
    stamp = db.iso(db.now())
    db.execute("INSERT INTO users (id, kind, created_at, last_seen) VALUES (?, ?, ?, ?)", (user_id, kind, stamp, stamp))


def demo_user() -> UserData:
    import copy

    return copy.deepcopy(demo.template(TODAY))


def real_mail(msg_id: str = "real-1", body: str = "Secret body: your plan renews at $9.99") -> Email:
    return Email(id=msg_id, received_at=datetime(2026, 10, 20, tzinfo=timezone.utc), sender="no-reply@spotify.com",
                 subject="Your receipt", body_text=body, source="google")


# --- Serialization: generic, every field ----------------------------------------------------------

def test_every_field_round_trips():
    u = demo_user()
    u.checkins["hulu"].append((TODAY, False))
    u.kept["netflix"] = TODAY
    u.cancel_pending["spotify"] = TODAY
    u.finding_status["x"] = "dismissed"
    u.got_back["x"] = 12.5
    u.plaid_cursor = "cursor-9"
    assert u.findings and any(f.details for f in u.findings.values())

    back = deserialize(json.loads(json.dumps(serialize(u))))
    for f in dataclasses.fields(UserData):
        assert getattr(back, f.name) == getattr(u, f.name), f.name
    # Finding.details is excluded from the API but must persist: the action builder needs it.
    assert {k: f.details for k, f in back.findings.items()} == {k: f.details for k, f in u.findings.items()}
    assert isinstance(back.checkins, defaultdict)  # main.py appends to unknown ids
    back.checkins["new-id"].append((TODAY, True))


def test_only_demo_emails_are_written():
    u = demo_user()
    u.emails.append(real_mail())
    data = serialize(u)
    assert len(data["emails"]) == len(u.emails) - 1 and {e["source"] for e in data["emails"]} == {"demo"}
    assert "Secret body" not in json.dumps(data)


def test_bad_or_unknown_fields_fall_back_to_defaults(caplog):
    data = serialize(demo_user())
    data["kept"] = {"netflix": "not a date"}
    data["field_from_the_future"] = [1, 2, 3]
    with caplog.at_level(logging.WARNING):
        back = deserialize(data)
    assert back.kept == {} and back.transactions  # one bad field doesn't lose the session
    assert "kept" in caplog.text


# --- Save and load ------------------------------------------------------------------------------------

def test_save_load_across_a_restart():
    make_row("u1")
    u = store.replace("u1", demo_user())
    u.kept["netflix"] = TODAY
    assert store.save("u1") is True
    assert store.save("u1") is False  # unchanged: no write
    version = store.version("u1")

    store.clear()  # what a restart does to memory
    db.close()
    back = store.user("u1")
    assert back.kept == {"netflix": TODAY} and len(back.subscriptions) == len(u.subscriptions)
    assert store.version("u1") == version and not store.is_cold("u1")  # demo mode: nothing to re-read


def test_saves_only_existing_rows():
    store.user("nobody").kept["x"] = TODAY
    assert store.save("nobody") is False
    assert db.one("SELECT COUNT(*) AS n FROM users")["n"] == 0


def test_data_is_encrypted_at_rest():
    make_row("u1")
    store.replace("u1", demo_user())
    store.save("u1")
    raw = db_bytes()
    assert b"Netflix" not in raw and b"DoorDash" not in raw and b"Duolingo" not in raw


def test_real_mail_stays_in_memory_and_is_read_again(fake):
    make_row("u1")
    connections.set_email("u1", EmailConnection(grant_id="grant-1", account="me@example.com", provider="google",
                                                connected_at=now()))
    store.use_real_data("u1")
    connect.sync_now("u1")  # reads the fake inbox
    u = store.user("u1")
    assert u.emails and u.subscriptions and u.mode == "real"
    store.save("u1")
    assert b"charged $12.99" not in db_bytes()

    store.clear()
    cold = store.user("u1")
    assert cold.emails == [] and cold.subscriptions and store.is_cold("u1")  # results kept, mail gone
    calls = len(fake.nylas.message_calls())
    connect.ensure_fresh("u1")
    assert len(fake.nylas.message_calls()) == calls + 1 and not store.is_cold("u1")
    assert [e.id for e in store.user("u1").emails] == ["m1", "m2", "m3", "m4"]
    connect.ensure_fresh("u1")
    assert len(fake.nylas.message_calls()) == calls + 1  # once per load


def test_refresh_reloads_what_another_process_saved():
    make_row("u1")
    store.replace("u1", demo_user())
    store.save("u1")
    store.user("u1")  # the API's copy

    # "Another process": load its own copy, change it, save.
    other = deserialize(json.loads(crypto.decrypt(db.one("SELECT data FROM users WHERE id='u1'")["data"])))
    other.kept["from-nightly"] = TODAY
    text = json.dumps(serialize(other))
    db.execute("UPDATE users SET data = ?, version = version + 1 WHERE id = 'u1'", (crypto.encrypt(text.encode()),))

    assert "from-nightly" not in store.user("u1").kept
    store.refresh("u1")
    assert "from-nightly" in store.user("u1").kept


def test_careful_save_refuses_to_overwrite():
    make_row("u1")
    store.replace("u1", demo_user())
    store.save("u1")
    store.forget("u1")
    store.user("u1").kept["a"] = TODAY  # the nightly job's copy
    db.execute("UPDATE users SET version = version + 1 WHERE id = 'u1'")  # the API saved meanwhile
    with pytest.raises(SaveConflict):
        store.save("u1", careful=True)


def test_api_save_never_overwrites_a_newer_row(caplog):
    make_row("u1")
    store.replace("u1", demo_user())
    store.save("u1")
    other = deserialize(json.loads(crypto.decrypt(db.one("SELECT data FROM users WHERE id='u1'")["data"])))
    other.kept["from-nightly"] = TODAY
    db.execute("UPDATE users SET data = ?, version = version + 1 WHERE id = 'u1'",
               (crypto.encrypt(json.dumps(serialize(other)).encode()),))

    store.user("u1").kept["from-request"] = TODAY  # a request that started before the job saved
    with caplog.at_level(logging.WARNING):
        assert store.save("u1") is False
    assert "changed on disk" in caplog.text
    assert set(store.user("u1").kept) == {"from-nightly"}  # the newer copy on disk won and is loaded


def test_idle_users_are_saved_and_dropped_from_memory(monkeypatch):
    import clawback.store as store_module

    monkeypatch.setattr(store_module, "MAX_IN_MEMORY", 2)
    for uid in ("u1", "u2"):
        make_row(uid)
        store.replace(uid, demo_user())
    store.user("u1").kept["netflix"] = TODAY  # changed, not saved yet
    store._users["u1"].used -= 3600  # idle for an hour
    store.user("u3")  # a third user loads: u1 is saved, then dropped
    assert "u1" not in store._users and {"u2", "u3"} <= set(store._users)
    assert store.user("u1").kept == {"netflix": TODAY}  # loads again from disk, change included
    store.user("u4")  # nobody else is idle: nothing is dropped
    assert {"u1", "u2", "u4"} <= set(store._users)


def test_cors_origins(monkeypatch):
    s = config.settings
    monkeypatch.setattr(s, "frontend_origin", "https://clawback.vercel.app/, http://localhost:3000")
    assert s.frontend_origins == ["https://clawback.vercel.app", "http://localhost:3000"]
    assert s.return_origin == "https://clawback.vercel.app"


# --- Connections in the database ---------------------------------------------------------------------

def plaid_conn(item: str = "item-1") -> PlaidConnection:
    return PlaidConnection(access_token="access-sandbox-secret", item_id=item, institution="Bank", connected_at=now())


def test_connections_are_encrypted_and_found_by_id():
    connections.set_email("u1", EmailConnection(grant_id="grant-abc", account="me@example.com", connected_at=now()))
    connections.set_plaid("u1", plaid_conn())
    connections.set_plaid("u2", plaid_conn("item-2"))
    raw = db_bytes()
    for secret in (b"grant-abc", b"access-sandbox-secret", b"item-1", b"me@example.com"):
        assert secret not in raw
    assert connections.get("u1").email.grant_id == "grant-abc"
    assert connections.find_user("email", "grant-abc") == "u1"
    assert connections.find_user("plaid", "item-2") == "u2"
    assert connections.find_user("plaid", "item-9") is None and connections.find_user("email", "") is None
    assert connections.users_with_connections() == ["u1", "u2"]
    rows = db.query("EXPLAIN QUERY PLAN SELECT user_id FROM connections WHERE source = 'email' AND lookup = 'x'")
    assert any("connections_lookup" in r["detail"] for r in rows)  # webhooks use the index

    assert connections.mark_reconnect("u2", "plaid", "Sign in again.")
    assert connections.get("u2").plaid.needs_reconnect and connections.get("u2").plaid.error == "Sign in again."
    assert connections.mark_reconnect("u2", "plaid", "", needs=False)
    assert not connections.get("u2").plaid.needs_reconnect
    assert connections.mark_reconnect("u3", "plaid", "x") is False


def test_a_changed_key_means_no_connection(monkeypatch, caplog):
    connections.set_plaid("u1", plaid_conn())
    monkeypatch.setattr(config.settings, "secret_key", "a different key entirely")
    crypto.reset()
    with caplog.at_level(logging.WARNING):
        assert connections.get("u1").plaid is None
    assert "could not be read" in caplog.text and "access-sandbox-secret" not in caplog.text


def test_local_key_is_generated_once(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(config.settings, "secret_key", None)
    crypto.reset()
    path = config.settings.secret_key_path
    with caplog.at_level(logging.WARNING):
        token = crypto.encrypt(b"hello")
    key = path.read_bytes()
    assert "generated a local key" in caplog.text and key.decode() not in caplog.text
    crypto.reset()
    assert crypto.decrypt(token) == b"hello" and path.read_bytes() == key


def test_legacy_connections_file_is_moved_and_deleted(caplog):
    db.close()
    legacy = config.settings.connections_path
    legacy.write_text(json.dumps({"version": 1, "users": {"demo": {
        "email": {"grant_id": "grant-old", "account": "me@example.com", "provider": "google",
                  "connected_at": "2026-10-20T10:00:00+00:00"},
        "plaid": {"access_token": "access-old", "item_id": "item-old", "cursor": "c1",
                  "connected_at": "2026-10-20T10:00:00+00:00"}}}}), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        conns = connections.get("demo")  # opening the database moves the file
    assert conns.email.grant_id == "grant-old" and conns.plaid.access_token == "access-old"
    assert not legacy.exists() and "moved 2 saved connections" in caplog.text
    assert connections.find_user("plaid", "item-old") == "demo"
    assert db.one("SELECT kind FROM users WHERE id = 'demo'")["kind"] == "single"
    assert b"access-old" not in db_bytes()


def test_unreadable_legacy_file_is_set_aside():
    db.close()
    legacy = config.settings.connections_path
    legacy.write_text("{not json", encoding="utf-8")
    assert connections.get("demo").any() is False
    assert legacy.with_name(legacy.name + ".bad").exists()


def test_non_fernet_secret_is_stretched(monkeypatch):
    monkeypatch.setattr(config.settings, "secret_key", "correct horse battery staple")
    crypto.reset()
    token = crypto.encrypt(b"x")
    crypto.reset()
    assert crypto.decrypt(token) == b"x"
    monkeypatch.setattr(config.settings, "secret_key", TEST_KEY)
    crypto.reset()
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(token)
