"""Email (Nylas) and bank (Plaid) connections, all against fakes (see conftest.py). No network, no real file."""

import json
import os
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from conftest import nylas_message, plaid_tx, sync_page

from clawback import config, connect, connections
from clawback.connections import EmailConnection, now
from clawback.sources import net, nylas, plaid, text
from clawback.sources.nylas import EmailError, EmailExpired
from clawback.store import store

USER = "demo"


def state_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


def connect_email(client, code: str = "good-code") -> httpx.Response:
    state = state_of(client.get("/api/connect/email").json()["auth_url"])
    return client.get("/api/connect/email/callback", params={"code": code, "state": state}, follow_redirects=False)


def connect_error(resp: httpx.Response) -> str:
    return parse_qs(urlparse(resp.headers["location"]).query)["connect_error"][0]


def saved_email(provider: str = "google") -> EmailConnection:
    conn = EmailConnection(grant_id="grant-1", account="me@example.com", provider=provider, connected_at=now())
    connections.set_email(USER, conn)
    return conn


# --- Message mapping ---------------------------------------------------------------------------------

def test_message_mapping():
    html = nylas.to_email(nylas_message("a1", "Info@Account.Netflix.com", "  Price change ",
                                        "<div>Your price will change from $15.49&nbsp;to $17.99.</div>"
                                        "<script>track()</script>", days_ago=2), "microsoft")
    assert html.id == "a1" and html.source == "microsoft"
    assert html.sender == "info@account.netflix.com" and html.subject == "Price change"
    assert html.body_text == "Your price will change from $15.49 to $17.99."
    assert abs((now() - html.received_at) - timedelta(days=2)) < timedelta(minutes=1)  # `date` is unix seconds

    plain = nylas.to_email(nylas_message("a2", "x@y.com", "Hi", "Line one\r\n\r\n\r\nLine   two"), "yahoo")
    assert plain.body_text == "Line one\n\nLine two" and plain.source == "yahoo"

    no_body = nylas.to_email(nylas_message("a3", "x@y.com", "Hi", None, snippet="Thanks &amp; welcome"), "some-new-provider")
    assert no_body.body_text == "Thanks & welcome" and no_body.source == "email"

    long = nylas.to_email(nylas_message("a4", "x@y.com", "Long", "word " * 3000), "imap")
    assert len(long.body_text) == nylas.BODY_LIMIT
    assert nylas.to_email({"subject": "no id"}, "google") is None


def test_html_to_text():
    page = ("<html><head><title>Receipt</title><style>.x{color:red}</style></head><body>"
            "<p>Your plan renews&nbsp;on Nov&nbsp;1.</p><div>Total:&nbsp;<b>$9.99</b></div>"
            "<script>track()</script><table><tr><td>Plan</td><td>Premium</td></tr></table></body></html>")
    out = text.html_to_text(page)
    assert "Your plan renews on Nov 1." in out and "Total: $9.99" in out and "Plan Premium" in out
    assert "track()" not in out and "color:red" not in out and "Receipt" not in out and "<" not in out


# --- Hosted OAuth ------------------------------------------------------------------------------------

def test_auth_url_and_state_checks(configured):
    url = nylas.start_url(USER, login_hint="me@example.com")
    parsed = urlparse(url)
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://api.us.nylas.com/v3/connect/auth"
    assert q["client_id"] == "nylas-client" and q["redirect_uri"] == config.settings.email_redirect_uri
    assert (q["response_type"], q["access_type"], q["login_hint"]) == ("code", "online", "me@example.com")
    assert "provider" not in q  # Nylas shows its provider picker
    assert "login_hint" not in parse_qs(urlparse(nylas.start_url(USER)).query)

    with pytest.raises(EmailError):
        nylas.check_state("not-a-state-we-issued")
    with pytest.raises(EmailError):
        nylas.check_state(None)
    assert nylas.check_state(q["state"]) == USER
    with pytest.raises(EmailError):  # single use
        nylas.check_state(q["state"])

    expired = state_of(nylas.start_url(USER))
    nylas._states[expired] = (USER, 0.0)
    with pytest.raises(EmailError):
        nylas.check_state(expired)


def test_eu_region(configured, monkeypatch):
    monkeypatch.setattr(config.settings, "nylas_api_uri", "https://api.eu.nylas.com")
    assert nylas.start_url(USER).startswith("https://api.eu.nylas.com/v3/connect/auth?")


# --- Unconfigured ------------------------------------------------------------------------------------

def test_unconfigured_routes_say_which_env_vars(client):
    r = client.get("/api/connect/email")
    assert r.status_code == 501
    msg = r.json()["missing"]
    assert "MISSING" in msg and "NYLAS_CLIENT_ID" in msg and "NYLAS_API_KEY" in msg and "backend/.env" in msg

    for r in (client.post("/api/connect/plaid/link-token"),
              client.post("/api/connect/plaid/exchange", json={"public_token": "public-sandbox-x"})):
        assert r.status_code == 501
        assert "PLAID_CLIENT_ID" in r.json()["missing"] and "PLAID_SECRET" in r.json()["missing"]

    assert client.get("/api/connect/gmail").status_code == 404  # the direct Gmail route is gone
    assert client.get("/api/connect/plaid").status_code in (404, 405)
    assert client.post("/api/ingest/email/webhook", json={}).status_code == 501
    assert client.post("/api/ingest/plaid/webhook", json={}).status_code == 501
    integrations = client.get("/api/health").json()["integrations"]
    assert integrations["email"] is False and "gmail" not in integrations

    assert client.get("/api/connections").json() == {
        "mode": "demo",
        "email": {"configured": False, "connected": False, "account": None, "provider": None, "last_sync": None,
                  "error": None, "needs_reconnect": False},
        "plaid": {"configured": False, "connected": False, "institution": None, "last_sync": None, "error": None,
                  "needs_reconnect": False},
    }


def test_bad_plaid_env_is_reported(client, configured, monkeypatch):
    monkeypatch.setattr(config.settings, "plaid_env", "development")
    r = client.post("/api/connect/plaid/link-token")
    assert r.status_code == 501 and "PLAID_ENV" in r.json()["missing"]


# --- Email end to end --------------------------------------------------------------------------------

def test_email_connect_switches_to_real_data(client, fake):
    assert len(client.get("/api/subscriptions").json()) >= 9 and client.get("/api/connections").json()["mode"] == "demo"
    assert client.get("/api/health").json()["integrations"]["email"] is True

    r = connect_email(client)
    assert r.status_code == 302 and r.headers["location"] == "http://localhost:3000/dashboard?connected=email"

    status = client.get("/api/connections").json()
    assert status["mode"] == "real"
    e = status["email"]
    assert e["connected"] and e["account"] == "me@example.com" and e["provider"] == "google"
    assert e["last_sync"] and e["error"] is None and not e["needs_reconnect"]

    # Google: one native Gmail search with the 180-day limit inside it, and nothing Nylas would reject.
    calls = fake.nylas.message_calls()
    assert len(calls) == 1 and calls[0]["search_query_native"].startswith("newer_than:180d")

    u = store.user(USER)
    assert u.transactions == [] and not u.checkins and not u.kept  # demo data is gone
    assert [e.id for e in u.emails] == ["m1", "m2", "m3", "m4"]  # the 200-day-old one is cut
    assert {e.source for e in u.emails} == {"google"}
    subs = {s["merchant"]: s for s in client.get("/api/subscriptions").json()}
    assert set(subs) == {"Super Duolingo"} and subs["Super Duolingo"]["status"] == "trial"

    saved = json.loads(config.settings.connections_path.read_text())["users"][USER]["email"]
    assert saved["grant_id"] == "grant-1" and saved["provider"] == "google"
    assert "nylas-key" not in config.settings.connections_path.read_text()

    trace = client.get("/api/trace").json()
    assert any(t["engine"] == "nylas" and "read 4 messages" in t["note"] for t in trace)
    dumped = json.dumps(trace)
    assert "nylas-key" not in dumped and "nylas-access-token" not in dumped and "charged $12.99" not in dumped

    # The state was used up: replaying the callback fails cleanly.
    state = state_of(client.get("/api/connect/email").json()["auth_url"])
    client.get("/api/connect/email/callback", params={"code": "good-code", "state": state}, follow_redirects=False)
    replay = client.get("/api/connect/email/callback", params={"code": "good-code", "state": state},
                        follow_redirects=False)
    assert replay.status_code == 302 and "expired" in connect_error(replay)


def test_grant_lookup_when_token_response_is_bare_and_microsoft_search(client, fake):
    fake.nylas.token_has_identity = False
    fake.nylas.provider = "microsoft"
    assert connect_email(client).headers["location"].endswith("?connected=email")
    assert ("GET", "/v3/grants/grant-1", {}) in fake.nylas.calls
    status = client.get("/api/connections").json()["email"]
    assert status["account"] == "me@example.com" and status["provider"] == "microsoft"
    query = fake.nylas.message_calls()[0]["search_query_native"]
    assert "receipt" in query and '"' not in query  # KQL keywords
    assert "old" not in [e.id for e in store.user(USER).emails]  # date cut made here for Microsoft


def test_other_providers_scan_recent_mail_with_keyword_rules(client, fake):
    fake.nylas.provider = "yahoo"
    connect_email(client)
    params = fake.nylas.message_calls()[0]
    assert "search_query_native" not in params and int(params["received_after"]) < now().timestamp()
    ids = [e.id for e in store.user(USER).emails]
    assert ids == ["m1", "m3", "m4"]  # "Lunch on Friday?" isn't subscription mail
    assert {e.source for e in store.user(USER).emails} == {"yahoo"}


def test_refused_native_search_falls_back_to_scan(client, fake):
    fake.nylas.provider = "microsoft"
    fake.nylas.reject_search = True
    assert connect_email(client).headers["location"].endswith("?connected=email")
    calls = fake.nylas.message_calls()
    assert "search_query_native" in calls[0] and "received_after" in calls[1]
    assert any("keyword rules" in t["note"] for t in client.get("/api/trace").json() if t["engine"] == "nylas")


def test_paging_stops_at_the_limit(fake, monkeypatch):
    monkeypatch.setattr(nylas, "PAGE_SIZE", 2)
    monkeypatch.setattr(config.settings, "email_max_messages", 3)
    emails = nylas.fetch_emails(USER, saved_email())
    assert [e.id for e in emails] == ["m1", "m2", "m3"]
    assert [c.get("page_token") for c in fake.nylas.message_calls()] == [None, "2"]


def test_rate_limit_is_retried(fake):
    fake.nylas.rate_limit_once = True
    assert len(nylas.fetch_emails(USER, saved_email())) == 4
    assert len(fake.nylas.message_calls()) == 2


def test_callback_errors_redirect_with_a_short_message(client, fake):
    r = client.get("/api/connect/email/callback", params={"code": "good-code", "state": "forged"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("http://localhost:3000/dashboard?connect_error=")

    state = state_of(client.get("/api/connect/email").json()["auth_url"])
    r = client.get("/api/connect/email/callback", params={"error": "access_denied", "state": state}, follow_redirects=False)
    assert "cancelled" in connect_error(r)

    r = connect_email(client, code="bad-code")
    assert "Invalid or expired authorization code" in connect_error(r)
    assert client.get("/api/connections").json()["mode"] == "demo"  # a failed connect leaves the demo alone


def test_expired_grant_asks_for_reconnect(fake):
    store.reset(USER)
    store.use_real_data(USER)
    saved_email()
    fake.nylas.messages_status = 401
    result = connect.sync_now(USER)  # sync reports it instead of crashing
    assert result["synced"]["email"]["ok"] is False
    assert result["synced"]["email"]["error"].startswith(nylas.EXPIRED)
    status = connect.status(USER)["email"]
    assert status["connected"] and status["needs_reconnect"] and status["error"].startswith(nylas.EXPIRED)

    calls = len(fake.nylas.calls)
    with pytest.raises(EmailExpired):
        nylas.fetch_emails(USER, connections.get(USER).email)
    assert len(fake.nylas.calls) == calls  # no more requests until the user reconnects


def test_email_disconnect_deletes_the_grant(client, fake):
    connect_email(client)
    status = client.post("/api/connect/email/disconnect").json()
    assert fake.nylas.deleted == ["grant-1"]
    assert status["email"]["connected"] is False and status["mode"] == "real"
    assert store.user(USER).emails == []
    assert "email" not in json.loads(config.settings.connections_path.read_text())["users"].get(USER, {})


def test_connecting_another_inbox_deletes_the_old_grant(client, fake):
    connect_email(client)
    fake.nylas.grant_id = "grant-2"
    assert connect_email(client).headers["location"].endswith("?connected=email")
    assert fake.nylas.deleted == ["grant-1"]  # the Sandbox counts every grant, so don't leave old ones behind
    assert connections.get(USER).email.grant_id == "grant-2"


def test_sync_after_disconnect_cannot_bring_the_connection_back(fake):
    conn = saved_email()
    connections.set_email(USER, None)
    connections.update_email(USER, conn)  # what an in-flight sync would do
    assert connections.get(USER).email is None


# --- Plaid -------------------------------------------------------------------------------------------

def test_plaid_mapping():
    netflix = plaid.to_transaction(plaid_tx("t1", 3, 17.99, "NETFLIX.COM 866-579-7172", "Netflix"))
    assert netflix.id == "t1" and netflix.amount == 17.99 and netflix.source == "plaid"
    assert plaid.to_transaction(plaid_tx("t2", 3, 6.33, "Uber 063015 SF**POOL**", "Uber")).description == "Uber"
    apple = plaid.to_transaction(plaid_tx("t3", 3, 2.99, "APPLE.COM/BILL 866-712-7753", "Apple"))
    assert apple.description == "APPLE.COM/BILL 866-712-7753"  # kept raw so app-store matching still works
    refund = plaid.to_transaction(plaid_tx("t4", 3, -4.22, "INTRST PYMNT"))
    assert refund.description == "INTRST PYMNT" and refund.amount == -4.22  # negative = money in, as in our model
    assert plaid.to_transaction({"amount": 1, "date": "2026-10-01"}) is None


def test_plaid_link_exchange_sync_disconnect(client, fake):
    r = client.post("/api/connect/plaid/link-token")
    assert r.json() == {"link_token": "link-sandbox-123"}
    _, body = fake.plaid.calls[-1]
    assert body["client_name"] == "ClawBack" and body["user"] == {"client_user_id": USER}
    assert body["products"] == ["transactions"] and body["transactions"] == {"days_requested": 180}
    assert body["country_codes"] == ["US"] and body["language"] == "en"

    r = client.post("/api/connect/plaid/exchange", json={"public_token": "public-sandbox-1", "institution": "First Platypus Bank"})
    assert r.status_code == 200
    assert r.json() == {"added_transactions": 7, "institution": "First Platypus Bank", "pending": False}

    status = client.get("/api/connections").json()
    assert status["mode"] == "real" and status["plaid"]["connected"] and status["plaid"]["institution"] == "First Platypus Bank"
    u = store.user(USER)
    assert {t.source for t in u.transactions} == {"plaid"} and u.emails == []
    assert [s["merchant"] for s in client.get("/api/subscriptions").json()] == ["Netflix"]
    saved = json.loads(config.settings.connections_path.read_text())["users"][USER]["plaid"]
    assert saved["access_token"] == "access-sandbox-1" and saved["cursor"] == "cursor-1"
    assert any(t["engine"] == "plaid" and "+7 new" in t["note"] for t in client.get("/api/trace").json())

    # Sync carries on from the cursor and applies changes and removals.
    fake.plaid.sync_pages = [sync_page(added=[plaid_tx("new1", 1, 4.5, "Starbucks", "Starbucks")],
                                       modified=[plaid_tx("climb", 12, 90.0, "Touchstone Climbing", "Touchstone Climbing")],
                                       removed=["nf5"], cursor="cursor-2")]
    r = client.post("/api/sync").json()
    assert r["mode"] == "real" and r["synced"]["plaid"] == {"ok": True, "added_transactions": 1, "pending": False, "error": None}
    assert fake.plaid.calls[-1][1]["cursor"] == "cursor-1"
    ids = {t.id: t for t in store.user(USER).transactions}
    assert "new1" in ids and "nf5" not in ids and ids["climb"].amount == 90.0

    # Statement upload still works in real mode.
    r = client.post("/api/ingest/statement", files={"file": ("s.csv", "Date,Description,Amount\n2026-10-01,GYM,-20.00\n")})
    assert r.json()["added_transactions"] == 1

    status = client.post("/api/connect/plaid/disconnect").json()
    assert fake.plaid.paths()[-1] == "/item/remove"
    assert status["plaid"]["connected"] is False and status["mode"] == "real"
    assert {t.source for t in store.user(USER).transactions} == {"statement"}
    assert client.post("/api/connect/bank/disconnect").status_code == 404


def test_plaid_waits_for_a_new_item_then_reports_pending(client, fake, monkeypatch):
    monkeypatch.setattr(plaid, "RETRY_WAITS", (0, 0, 0, 0))
    not_ready = sync_page(cursor="", status="NOT_READY")
    fake.plaid.sync_pages = [not_ready, not_ready, sync_page(added=[plaid_tx("a", 2, 9.99, "HULU", "Hulu")])]
    r = client.post("/api/connect/plaid/exchange", json={"public_token": "p", "institution": None}).json()
    assert r == {"added_transactions": 1, "institution": None, "pending": False}
    assert fake.plaid.paths().count("/transactions/sync") == 3

    fake.plaid.sync_pages = [not_ready]
    r = client.post("/api/connect/plaid/exchange", json={"public_token": "p2"}).json()
    assert r["added_transactions"] == 0 and r["pending"] is True


def test_plaid_errors_are_clean_json(client, fake):
    fake.plaid.errors["/item/public_token/exchange"] = (400, {
        "error_type": "INVALID_INPUT", "error_code": "INVALID_PUBLIC_TOKEN",
        "error_message": "provided public token is in an invalid format. expected format: public-<environment>-<identifier>"})
    r = client.post("/api/connect/plaid/exchange", json={"public_token": "nonsense"})
    assert r.status_code == 400 and r.json() == {"detail": fake.plaid.errors["/item/public_token/exchange"][1]["error_message"]}
    assert client.get("/api/connections").json()["mode"] == "demo"  # nothing was wiped

    fake.plaid.errors["/link/token/create"] = (500, {"error_type": "API_ERROR", "error_code": "INTERNAL_SERVER_ERROR",
                                                     "error_message": "an unexpected error occurred"})
    r = client.post("/api/connect/plaid/link-token")
    assert r.status_code == 502 and r.json() == {"detail": "an unexpected error occurred"}


# --- Demo vs real, startup ---------------------------------------------------------------------------

def test_demo_seed_switches_back_and_keeps_connections(client, fake):
    client.post("/api/connect/plaid/exchange", json={"public_token": "p", "institution": "Bank"})
    assert client.get("/api/connections").json()["mode"] == "real"

    summary = client.post("/api/demo/seed").json()
    assert summary["subscriptions"] >= 9
    status = client.get("/api/connections").json()
    assert status["mode"] == "demo" and status["plaid"]["connected"]  # saved, but unused
    assert {t.source for t in store.user(USER).transactions} == {"demo"}

    calls = len(fake.plaid.calls)
    r = client.post("/api/sync").json()
    assert r["mode"] == "demo" and r["synced"] == {} and len(fake.plaid.calls) == calls  # demo sync pulls nothing


def test_leaving_demo_again_pulls_every_saved_source(client, fake):
    client.post("/api/connect/plaid/exchange", json={"public_token": "p", "institution": "Bank"})
    client.post("/api/demo/seed")
    assert connect_email(client).headers["location"].endswith("?connected=email")
    u = store.user(USER)
    assert {t.source for t in u.transactions} == {"plaid"} and {e.source for e in u.emails} == {"google"}
    assert {"Netflix", "Super Duolingo"} <= {s["merchant"] for s in client.get("/api/subscriptions").json()}

    r = client.post("/api/sync").json()
    assert r["synced"]["email"] == {"ok": True, "emails": 4, "error": None} and r["synced"]["plaid"]["ok"]


def test_startup_restores_saved_connections(fake):
    from fastapi.testclient import TestClient

    from clawback.main import app

    saved_email()
    connections.set_plaid(USER, connections.PlaidConnection(access_token="access-sandbox-1", item_id="item-1",
                                                           institution="Bank", cursor="old", connected_at=now()))
    with TestClient(app) as c:
        status = c.get("/api/connections").json()
        assert status["mode"] == "real" and status["plaid"]["last_sync"] and status["email"]["last_sync"]
        assert {"Netflix", "Super Duolingo"} <= {s["merchant"] for s in c.get("/api/subscriptions").json()}
    assert "cursor" not in fake.plaid.calls[0][1]  # transactions live in memory, so a restart pulls from the start


def test_startup_survives_a_failing_source(monkeypatch, configured):
    from fastapi.testclient import TestClient

    from clawback.main import app

    def offline(request):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(net, "transport", httpx.MockTransport(offline))
    connections.set_plaid(USER, connections.PlaidConnection(access_token="a", item_id="i", connected_at=now()))
    saved_email()
    with TestClient(app) as c:
        status = c.get("/api/connections").json()
        assert status["mode"] == "real" and status["plaid"]["error"] == "Couldn't reach Plaid. Check the network and try again."
        assert status["email"]["error"] == "Couldn't reach Nylas. Check the network and try again."
        assert not status["email"]["needs_reconnect"]  # a network problem isn't an expired grant
        trace = c.get("/api/trace").json()
        assert {t["engine"] for t in trace if t["status"] == "error"} >= {"plaid", "nylas"}


# --- Settings ----------------------------------------------------------------------------------------

def test_dotenv_reader(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nCB_T_A=plain\nexport CB_T_B="quoted # not a comment"\nCB_T_C=value # note\n'
                   "CB_T_D=\nCB_T_E=kept\n", encoding="utf-8")
    for k in ("CB_T_A", "CB_T_B", "CB_T_C", "CB_T_D"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CB_T_E", "from-environment")
    config.load_env_file(env)
    try:
        assert os.environ["CB_T_A"] == "plain" and os.environ["CB_T_B"] == "quoted # not a comment"
        assert os.environ["CB_T_C"] == "value" and os.environ["CB_T_D"] == ""
        assert os.environ["CB_T_E"] == "from-environment"  # the real environment wins
    finally:
        for k in ("CB_T_A", "CB_T_B", "CB_T_C", "CB_T_D"):
            os.environ.pop(k, None)
