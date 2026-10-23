"""Nylas and Plaid webhooks, offline: signatures made here with local keys, services faked (conftest.py)."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from conftest import connect_both, new_session, nylas_message, plaid_tx, sync_page, user_of
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from clawback import config, connections
from clawback.findings import rulebook
from clawback.sources import plaid
from clawback.store import store

SECRET = "nylas-webhook-secret"
EMAIL_HOOK = "/api/ingest/email/webhook"
PLAID_HOOK = "/api/ingest/plaid/webhook"


@pytest.fixture()
def hooks(monkeypatch):
    monkeypatch.setattr(config.settings, "nylas_webhook_secret", SECRET)


@pytest.fixture()
def connected(api, fake, hooks):
    """A visitor session with the fake inbox and bank connected. Returns (headers, user id)."""
    h = new_session(api)
    connect_both(api, h)
    return h, user_of(h)


# --- Nylas -------------------------------------------------------------------------------------------

def nylas_event(kind: str, grant: str = "grant-1", obj: dict | None = None) -> bytes:
    """A notification in the CloudEvents shape Nylas sends (developer.nylas.com, 2026-10-23)."""
    return json.dumps({
        "specversion": "1.0", "type": kind, "source": "/google/emails/realtime", "id": "wh-1",
        "time": int(time.time()), "webhook_delivery_attempt": 1,
        "data": {"application_id": "app-1", "object": {"grant_id": grant, **(obj or {})}},
    }).encode()


def post_nylas(api, body: bytes, secret: str = SECRET):
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return api.post(EMAIL_HOOK, content=body, headers={"X-Nylas-Signature": sig, "Content-Type": "application/json"})


def spotify_trial(msg_id: str = "s1") -> dict:
    return nylas_message(msg_id, "no-reply@spotify.com", "Your Spotify Premium free trial ends in 5 days",
                         "Your free trial ends in 5 days. After that you'll be charged $11.99/month.", days_ago=0.1)


def test_challenge_is_echoed_as_plain_text(api):
    r = api.get(EMAIL_HOOK, params={"challenge": "abc123XYZ"})
    assert r.status_code == 200 and r.text == "abc123XYZ" and r.headers["content-type"].startswith("text/plain")


def test_unsigned_or_badly_signed_is_refused(api, hooks):
    body = nylas_event("message.created", obj={"id": "s1", "object": "message"})
    assert api.post(EMAIL_HOOK, content=body).status_code == 401
    assert post_nylas(api, body, secret="wrong").status_code == 401
    assert post_nylas(api, b"not json").status_code == 400


def test_unconfigured_webhook_says_what_to_set(api):
    r = api.post(EMAIL_HOOK, content=b"{}")
    assert r.status_code == 501 and "NYLAS_WEBHOOK_SECRET" in r.json()["missing"]


def test_new_message_is_read_and_alerts_once(api, fake, connected):
    h, uid = connected
    assert api.get("/api/alerts", headers=h).json() == {"alerts": [], "unseen": 0}  # connecting isn't news
    fake.nylas.messages.insert(0, spotify_trial())
    body = nylas_event("message.created", obj={"id": "s1", "object": "message", "subject": "trial"})
    r = post_nylas(api, body)
    assert r.json() == {"ok": True, "handled": "queued"}

    assert ("GET", "/v3/grants/grant-1/messages/s1", {}) in fake.nylas.calls
    assert "s1" in [e.id for e in store.user(uid).emails]
    subs = {s["merchant"]: s for s in api.get("/api/subscriptions", headers=h).json()}
    assert subs["Spotify"]["status"] == "trial"
    got = api.get("/api/alerts", headers=h).json()
    assert got["unseen"] == 1 and got["alerts"][0]["kind"] == "flag" and got["alerts"][0]["title"] == "Spotify"
    assert "Free trial ends" in got["alerts"][0]["message"]

    post_nylas(api, body)  # Nylas delivers at least once
    assert [e.id for e in store.user(uid).emails].count("s1") == 1
    assert api.get("/api/alerts", headers=h).json()["unseen"] == 1

    seen = api.post("/api/alerts/seen", headers=h, json={"ids": [got["alerts"][0]["id"]]}).json()
    assert seen == {"ok": True, "marked": 1, "unseen": 0}
    assert api.get("/api/alerts", headers=h).json()["alerts"][0]["seen"] is True
    store.clear()  # the webhook's work was saved
    assert "spotify" in store.user(uid).subscriptions


def test_mail_that_is_not_about_money_is_skipped(api, fake, connected):
    h, uid = connected
    fake.nylas.messages.insert(0, nylas_message("p1", "friend@example.com", "Dinner?", "See you at 7.", days_ago=0.1))
    post_nylas(api, nylas_event("message.created", obj={"id": "p1"}))
    assert "p1" not in [e.id for e in store.user(uid).emails]
    post_nylas(api, nylas_event("message.created", obj={"id": "deleted-already"}))  # 404: nothing happens
    assert api.get("/api/alerts", headers=h).json()["unseen"] == 0


def test_truncated_notification_and_a_cold_start(api, fake, connected):
    h, uid = connected
    fake.nylas.messages.insert(0, spotify_trial("s2"))
    store.clear()  # a restart: the mail isn't in memory any more
    reads = len(fake.nylas.message_calls())
    post_nylas(api, nylas_event("message.created.truncated", obj={"id": "s2"}))
    assert len(fake.nylas.message_calls()) == reads + 1  # read everything again, this message included
    assert "s2" in [e.id for e in store.user(uid).emails]
    assert api.get("/api/alerts", headers=h).json()["unseen"] == 1


def test_unknown_grant_and_other_events(api, connected):
    assert post_nylas(api, nylas_event("message.created", grant="grant-x", obj={"id": "s1"})).json()["handled"] == "unknown grant"
    assert post_nylas(api, nylas_event("calendar.created")).json()["handled"] == "ignored"


@pytest.mark.parametrize("kind", ["grant.expired", "grant.deleted"])
def test_lost_grant_needs_a_reconnect(api, connected, kind):
    h, _ = connected
    assert post_nylas(api, nylas_event(kind, obj={"code": 25009, "provider": "google"})).json()["handled"] == "needs reconnect"
    email = api.get("/api/connections", headers=h).json()["email"]
    assert email["connected"] and email["needs_reconnect"] and "Connect email again" in email["error"]


# --- Plaid -------------------------------------------------------------------------------------------

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Signer:
    """Plays Plaid: an ES256 key, its JWK, and Plaid-Verification tokens for a body."""

    def __init__(self, kid: str = "kid-1") -> None:
        self.kid, self.key = kid, ec.generate_private_key(ec.SECP256R1())
        n = self.key.public_key().public_numbers()
        self.jwk = {"alg": "ES256", "crv": "P-256", "kid": kid, "kty": "EC", "use": "sig",
                    "x": b64url(n.x.to_bytes(32, "big")), "y": b64url(n.y.to_bytes(32, "big")),
                    "created_at": 1560466150, "expired_at": None}

    def token(self, body: bytes, iat: float | None = None, alg: str = "ES256", kid: str | None = None,
              body_hash: str | None = None) -> str:
        head = b64url(json.dumps({"alg": alg, "kid": kid or self.kid, "typ": "JWT"}).encode())
        claims = b64url(json.dumps({"iat": int(iat or time.time()),
                                    "request_body_sha256": body_hash or hashlib.sha256(body).hexdigest()}).encode())
        r, s = decode_dss_signature(self.key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
        return f"{head}.{claims}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def plaid_event(kind: str, code: str, item: str = "item-1", **extra) -> bytes:
    # Plaid sends pretty-printed JSON; the hash covers the bytes exactly as sent.
    return json.dumps({"webhook_type": kind, "webhook_code": code, "item_id": item, "environment": "sandbox",
                       **extra}, indent=2).encode()


def post_plaid(api, body: bytes, token: str | None):
    headers = {"Content-Type": "application/json"} | ({"Plaid-Verification": token} if token else {})
    return api.post(PLAID_HOOK, content=body, headers=headers)


@pytest.fixture()
def signer(fake) -> Signer:
    s = Signer()
    fake.plaid.verification_keys[s.kid] = s.jwk
    return s


def test_sync_updates_pull_new_transactions_and_alert(api, fake, connected, signer):
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    h, uid = connected
    fake.plaid.sync_pages = [sync_page(added=[plaid_tx("od1", 1, 35.0, "OVERDRAFT ITEM FEE")], cursor="cursor-2")]
    body = plaid_event("TRANSACTIONS", "SYNC_UPDATES_AVAILABLE", initial_update_complete=True,
                       historical_update_complete=True)
    r = post_plaid(api, body, signer.token(body))
    assert r.json() == {"ok": True, "handled": "queued"}
    assert fake.plaid.calls[-1][0] == "/transactions/sync" and fake.plaid.calls[-1][1]["cursor"] == "cursor-1"
    assert "od1" in {t.id for t in store.user(uid).transactions}
    alerts = api.get("/api/alerts", headers=h).json()["alerts"]
    assert [a["kind"] for a in alerts] == ["finding"] and alerts[0]["amount"] == 35.0
    assert "First Platypus Bank" in alerts[0]["message"]

    post_plaid(api, body, signer.token(body))  # once more: nothing new
    assert len(api.get("/api/alerts", headers=h).json()["alerts"]) == 1


def test_bad_plaid_tokens_are_refused(api, fake, connected, signer):
    body = plaid_event("TRANSACTIONS", "SYNC_UPDATES_AVAILABLE")
    stranger = Signer()  # same kid, different key
    cases = [
        None,
        "not-a-jwt",
        stranger.token(body),
        signer.token(body + b" "),  # signed for other bytes
        signer.token(body, body_hash="0" * 64),
        signer.token(body, iat=time.time() - 6 * 60),  # older than 5 minutes
        signer.token(body, alg="HS256"),
        signer.token(body, kid="kid-unknown"),
    ]
    syncs = fake.plaid.paths().count("/transactions/sync")
    for token in cases:
        assert post_plaid(api, body, token).status_code == 401, token
    assert fake.plaid.paths().count("/transactions/sync") == syncs

    lookups = fake.plaid.paths().count("/webhook_verification_key/get")
    post_plaid(api, body, signer.token(body, kid="kid-unknown"))
    assert fake.plaid.paths().count("/webhook_verification_key/get") == lookups  # failed lookups are remembered

    fake.plaid.verification_keys["kid-2"] = {**Signer("kid-2").jwk, "expired_at": 1700000000}
    assert post_plaid(api, body, Signer("kid-2").token(body)).status_code == 401  # Plaid retired that key


def test_verification_key_is_cached(api, fake, connected, signer):
    body = plaid_event("ITEM", "WEBHOOK_UPDATE_ACKNOWLEDGED")
    for _ in range(3):
        assert post_plaid(api, body, signer.token(body)).json()["handled"] == "ignored"
    assert fake.plaid.paths().count("/webhook_verification_key/get") == 1


def test_item_errors_need_a_reconnect_and_repairs_clear_it(api, connected, signer):
    h, _ = connected
    body = plaid_event("ITEM", "ERROR", error={"error_code": "ITEM_LOGIN_REQUIRED"})
    assert post_plaid(api, body, signer.token(body)).json()["handled"] == "needs reconnect"
    bank = api.get("/api/connections", headers=h).json()["plaid"]
    assert bank["needs_reconnect"] and "sign in again" in bank["error"]
    body = plaid_event("ITEM", "LOGIN_REPAIRED")
    assert post_plaid(api, body, signer.token(body)).json()["handled"] == "repaired"
    assert not api.get("/api/connections", headers=h).json()["plaid"]["needs_reconnect"]
    body = plaid_event("ITEM", "PENDING_EXPIRATION", item="item-9")
    assert post_plaid(api, body, signer.token(body)).json()["handled"] == "unknown item"


def test_link_token_carries_the_webhook_url_when_public(api, fake, monkeypatch):
    h = new_session(api)
    api.post("/api/connect/plaid/link-token", headers=h)
    assert "webhook" not in fake.plaid.calls[-1][1]
    monkeypatch.setattr(config.settings, "public_api_url", "https://api.clawback.example")
    api.post("/api/connect/plaid/link-token", headers=h)
    assert fake.plaid.calls[-1][1]["webhook"] == "https://api.clawback.example/api/ingest/plaid/webhook"
    assert plaid.webhook_url() == "https://api.clawback.example" + plaid.WEBHOOK_PATH
    assert config.settings.integrations()["plaid_webhooks"] is True


def test_connection_lookup_survives_restart(api, connected):
    _, uid = connected
    store.clear()
    assert connections.find_user("plaid", "item-1") == uid and connections.find_user("email", "grant-1") == uid
