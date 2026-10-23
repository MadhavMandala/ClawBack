"""Shared test setup: no network, no backend/.env, no model or Tavily calls, and never the real backend/.local
(each test gets its own database file and key). Single-user mode by default, so the older tests keep using the
user "demo" with no session header; test_sessions.py switches to visitor sessions.
Live checks (tests/test_live.py, CLAWBACK_LIVE=1) read backend/.env."""

import os

if os.environ.get("CLAWBACK_LIVE") != "1":
    os.environ["CLAWBACK_DOTENV"] = "0"  # must happen before clawback.config is imported

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from cryptography.fernet import Fernet

from clawback import config, crypto, db, demo, llm, sessions
from clawback.sources import net, nylas, plaid
from clawback.store import store
from clawback.tools import tavily

from fakes import FakeLLM

TEST_KEY = Fernet.generate_key().decode()


def _no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unexpected network call: {request.method} {request.url}")


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    s = config.settings
    for name in ("nebius_api_key", "tavily_api_key", "nylas_client_id", "nylas_api_key",
                 "plaid_client_id", "plaid_secret"):
        monkeypatch.setattr(s, name, None)
    monkeypatch.setattr(s, "nylas_api_uri", "https://api.us.nylas.com")
    monkeypatch.setattr(s, "email_redirect_uri", "http://localhost:8000/api/connect/email/callback")
    monkeypatch.setattr(s, "email_max_messages", 150)
    monkeypatch.setattr(s, "plaid_env", "sandbox")
    monkeypatch.setattr(s, "frontend_origin", "http://localhost:3000")
    monkeypatch.setattr(s, "connections_path", tmp_path / "connections.json")
    # Storage, sessions and caps: a fresh database and key per test, single-user mode, default limits.
    monkeypatch.setattr(s, "db_path", tmp_path / "clawback.db")
    monkeypatch.setattr(s, "secret_key", TEST_KEY)
    monkeypatch.setattr(s, "secret_key_path", tmp_path / "secret.key")
    monkeypatch.setattr(s, "sessions", "single")
    monkeypatch.setattr(s, "session_idle_days", 14)
    monkeypatch.setattr(s, "sessions_per_ip_hour", 20)
    monkeypatch.setattr(s, "session_daily_usd", 0.25)
    monkeypatch.setattr(s, "global_daily_usd", 5.0)
    monkeypatch.setattr(s, "autoseed_demo", True)
    monkeypatch.setattr(s, "nylas_webhook_secret", None)
    monkeypatch.setattr(s, "public_api_url", None)
    monkeypatch.setattr(net, "transport", httpx.MockTransport(_no_network))
    monkeypatch.setattr(nylas, "_sleep", lambda seconds: None)
    nylas._states.clear()
    plaid._keys.clear()
    plaid._failed_keys.clear()
    _forget_process_state()
    # Tests never reach Token Factory or Tavily, even when backend/.env has real keys.
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(tavily, "available", lambda: False)
    yield
    _forget_process_state()


def _forget_process_state() -> None:
    db.close()
    crypto.reset()
    store.clear()
    demo.clear()
    sessions.reset()


@pytest.fixture()
def fake_llm(monkeypatch) -> FakeLLM:
    fake = FakeLLM()
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_client", lambda: fake)
    return fake


@pytest.fixture()
def configured(monkeypatch):
    s = config.settings
    monkeypatch.setattr(s, "nylas_client_id", "nylas-client")
    monkeypatch.setattr(s, "nylas_api_key", "nylas-key")
    monkeypatch.setattr(s, "plaid_client_id", "plaid-id")
    monkeypatch.setattr(s, "plaid_secret", "plaid-secret")


@pytest.fixture()
def client():
    from clawback.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def visitor(monkeypatch):
    """Hosted mode: each visitor gets a session (X-ClawBack-Session)."""
    monkeypatch.setattr(config.settings, "sessions", "visitor")


@pytest.fixture()
def api(visitor):
    """A test client in visitor mode. Use new_session(api) for a session's headers."""
    from clawback.main import app

    with TestClient(app) as c:
        yield c


def new_session(c: TestClient) -> dict[str, str]:
    r = c.post("/api/session")
    assert r.status_code == 200, r.text
    return {sessions.HEADER: r.json()["session_id"]}


def user_of(headers: dict[str, str]) -> str:
    """The user id behind a session (tests only; the API never reveals it)."""
    return sessions.resolve(headers[sessions.HEADER])


# --- Fake Nylas --------------------------------------------------------------------------------------

def nylas_message(msg_id: str, sender: str, subject: str, body: str | None, days_ago: float = 1,
                  snippet: str = "", name: str = "Sender") -> dict:
    """A message in the shape GET /v3/grants/{id}/messages returns (developer.nylas.com, 2026-10-22)."""
    received = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "id": msg_id, "grant_id": "grant-1", "object": "message", "thread_id": f"t-{msg_id}",
        "subject": subject, "from": [{"name": name, "email": sender}], "to": [{"name": "Me", "email": "me@example.com"}],
        "cc": [], "bcc": [], "reply_to": [], "date": int(received.timestamp()), "body": body, "snippet": snippet,
        "folders": ["INBOX"], "unread": False, "starred": False, "attachments": [],
    }


def inbox() -> list[dict]:
    """Newest first, like Nylas."""
    return [
        nylas_message("m1", "Hello@Duolingo.com", "Your Super Duolingo free trial ends in 3 days",
                      "<html><body><p>Your free trial ends in 3 days.</p><p>After that you'll be charged "
                      "$12.99/month.</p><style>.x{}</style></body></html>", days_ago=1, name="Duolingo"),
        nylas_message("m2", "friend@example.com", "Lunch on Friday?", "Are you free at noon?", days_ago=2),
        nylas_message("m3", "hello@hulumail.com", "We miss you!", "It's been a while since you watched.", days_ago=5),
        nylas_message("m4", "no-reply@spotify.com", "Your receipt", None, days_ago=9,
                      snippet="Spotify Premium $11.99 &amp; more"),
        nylas_message("old", "billing@example.com", "Your receipt from last year", "Total $5.00", days_ago=200),
    ]


class FakeNylas:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages
        self.grant_id = "grant-1"
        self.provider = "google"
        self.token_has_identity = True  # the token response carries email + provider
        self.messages_status = 200  # e.g. 401 for an expired grant
        self.reject_search = False  # 400 for search_query_native
        self.rate_limit_once = False
        self.calls: list[tuple[str, str, dict]] = []
        self.deleted: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response | None:
        if request.url.host != "api.us.nylas.com":
            return None
        path, params, method = request.url.path, dict(request.url.params), request.method
        self.calls.append((method, path, params))
        if path == "/v3/connect/token":
            assert "authorization" not in request.headers
            body = json.loads(request.content)
            assert (body["client_id"], body["client_secret"]) == ("nylas-client", "nylas-key")
            assert body["grant_type"] == "authorization_code"
            assert body["redirect_uri"] == config.settings.email_redirect_uri
            if body["code"] != "good-code":
                return httpx.Response(400, json={"request_id": "r", "error": {
                    "type": "invalid_request_error", "message": "Invalid or expired authorization code"}})
            token = {"access_token": "nylas-access-token", "token_type": "Bearer", "id_token": "id-token",
                     "grant_id": self.grant_id}
            if self.token_has_identity:
                token |= {"email": "me@example.com", "provider": self.provider}
            return httpx.Response(200, json=token)

        assert request.headers.get("authorization") == "Bearer nylas-key"
        if path == f"/v3/grants/{self.grant_id}" and method == "GET":
            return httpx.Response(200, json={"request_id": "r", "data": {
                "id": self.grant_id, "provider": self.provider, "grant_status": "valid", "email": "me@example.com"}})
        if path.startswith("/v3/grants/") and path.count("/") == 3 and method == "DELETE":
            self.deleted.append(path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={"request_id": "r"})
        if path == f"/v3/grants/{self.grant_id}/messages":
            if self.messages_status != 200:
                return httpx.Response(self.messages_status, json={"request_id": "r", "error": {
                    "type": "token.unauthorized_access", "message": "Grant is invalid"}})
            if self.rate_limit_once:
                self.rate_limit_once = False
                return httpx.Response(429, headers={"Retry-After": "1"}, json={"request_id": "r", "error": {
                    "type": "rate_limit_error", "message": "Too many requests"}})
            if "search_query_native" in params:
                # Nylas: for Google and Microsoft, only in / limit / page_token may go with search_query_native.
                assert set(params) <= {"search_query_native", "limit", "page_token", "in"}
                if self.reject_search:
                    return httpx.Response(400, json={"request_id": "r", "error": {
                        "type": "invalid_request_error", "message": "Search query is not supported"}})
            else:
                assert int(params["received_after"]) > 0
            size, start = int(params["limit"]), int(params.get("page_token") or 0)
            chunk = self.messages[start:start + size]
            more = start + size < len(self.messages)
            return httpx.Response(200, json={"request_id": "r", "data": chunk,
                                             "next_cursor": str(start + size) if more else None})
        return httpx.Response(404, json={"request_id": "r", "error": {"type": "not_found_error", "message": path}})

    def message_calls(self) -> list[dict]:
        return [p for m, path, p in self.calls if path.endswith("/messages")]


# --- Fake Plaid --------------------------------------------------------------------------------------

def plaid_tx(tx_id: str, days_ago: int, amount: float, name: str, merchant: str | None = None) -> dict:
    return {"transaction_id": tx_id, "account_id": "acc-1", "amount": amount, "iso_currency_code": "USD",
            "date": (date.today() - timedelta(days=days_ago)).isoformat(), "name": name, "merchant_name": merchant,
            "pending": False}


def netflix_history() -> list[dict]:
    txs = [plaid_tx(f"nf{k}", 3 + 30 * k, 17.99, "NETFLIX.COM", "Netflix") for k in range(6)]
    return txs + [plaid_tx("climb", 12, 85.0, "Touchstone Climbing", "Touchstone Climbing")]


def sync_page(added=(), modified=(), removed=(), cursor="cursor-1", has_more=False,
              status="HISTORICAL_UPDATE_COMPLETE") -> dict:
    return {"added": list(added), "modified": list(modified), "removed": [{"transaction_id": r} for r in removed],
            "next_cursor": cursor, "has_more": has_more, "transactions_update_status": status, "accounts": []}


class FakePlaid:
    def __init__(self) -> None:
        self.sync_pages: list[dict] = [sync_page(added=netflix_history())]
        self.errors: dict[str, tuple[int, dict]] = {}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response | None:
        if request.url.host != "sandbox.plaid.com":
            return None
        body = json.loads(request.content)
        assert body.pop("client_id") == "plaid-id" and body.pop("secret") == "plaid-secret"
        assert request.headers["plaid-version"]
        path = request.url.path
        self.calls.append((path, body))
        if path in self.errors:
            status, data = self.errors[path]
            return httpx.Response(status, json=data)
        if path == "/link/token/create":
            return httpx.Response(200, json={"link_token": "link-sandbox-123", "request_id": "r1"})
        if path == "/item/public_token/exchange":
            return httpx.Response(200, json={"access_token": "access-sandbox-1", "item_id": "item-1", "request_id": "r2"})
        if path == "/transactions/sync":
            page = self.sync_pages.pop(0) if len(self.sync_pages) > 1 else self.sync_pages[0]
            return httpx.Response(200, json=page)
        if path == "/item/remove":
            return httpx.Response(200, json={"request_id": "r3"})
        return httpx.Response(404, json={"error_message": "unknown path"})

    def paths(self) -> list[str]:
        return [p for p, _ in self.calls]


class FakeServices:
    def __init__(self) -> None:
        self.nylas = FakeNylas(inbox())
        self.plaid = FakePlaid()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        for service in (self.nylas, self.plaid):
            if (resp := service(request)) is not None:
                return resp
        raise AssertionError(f"unexpected network call: {request.method} {request.url}")


@pytest.fixture()
def fake(monkeypatch, configured):
    services = FakeServices()
    monkeypatch.setattr(net, "transport", httpx.MockTransport(services))
    return services
