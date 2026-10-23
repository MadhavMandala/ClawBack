"""Saving prepared emails as drafts in the user's own mailbox through Nylas (fake Nylas over httpx.MockTransport).
ClawBack never sends: the only call is POST /v3/grants/{id}/drafts."""

import json

import httpx
import pytest

from clawback import connections
from clawback.connections import EmailConnection, now
from clawback.sources import net, nylas

USER = "demo"


class FakeDrafts:
    """POST /v3/grants/{id}/drafts in the shape developer.nylas.com documents (checked 2026-10-23)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.replies: list[tuple[int, dict]] = []  # queued (status, body); default is success

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.us.nylas.com", request.url
        assert request.headers.get("authorization") == "Bearer nylas-key"
        assert request.method == "POST" and request.url.path == "/v3/grants/grant-1/drafts", request.url.path
        assert "send" not in request.url.path  # never the send endpoint
        body = json.loads(request.content)
        self.calls.append(body)
        if self.replies:
            status, data = self.replies.pop(0)
            return httpx.Response(status, json=data)
        return httpx.Response(200, json={"request_id": "r", "data": {
            "id": f"draft-{len(self.calls)}", "object": "draft", "grant_id": "grant-1", "subject": body["subject"]}})


def error(kind: str, message: str, provider_error: dict | None = None) -> dict:
    err = {"type": kind, "message": message}
    if provider_error:
        err["provider_error"] = provider_error
    return {"request_id": "r", "error": err}


@pytest.fixture()
def nylas_drafts(monkeypatch, configured) -> FakeDrafts:
    fake = FakeDrafts()
    monkeypatch.setattr(net, "transport", httpx.MockTransport(fake))
    return fake


def connect(provider: str = "google") -> EmailConnection:
    conn = EmailConnection(grant_id="grant-1", account="me@example.com", provider=provider, connected_at=now())
    connections.set_email(USER, conn)
    return conn


def sub_id(client, merchant: str = "Hulu") -> str:
    client.post("/api/demo/seed")
    return next(s["id"] for s in client.get("/api/subscriptions").json() if s["merchant"] == merchant)


# --- The Nylas call -----------------------------------------------------------------------------------

def test_create_draft_payload(nylas_drafts):
    conn = connect()
    assert nylas.create_draft(USER, conn, " Cancel please ", "Line one\nLine two") == "draft-1"
    assert nylas_drafts.calls[-1] == {"subject": "Cancel please", "body": "Line one\nLine two", "is_plaintext": True}
    nylas.create_draft(USER, conn, "s", "b", to="help@hulu.com")
    assert nylas_drafts.calls[-1]["to"] == [{"email": "help@hulu.com"}]
    nylas.create_draft(USER, conn, "s", "b", to="Your card issuer's billing-error address")
    assert "to" not in nylas_drafts.calls[-1]  # a description is not an address


def test_rate_limit_is_retried_but_server_errors_are_not(nylas_drafts):
    conn = connect()
    nylas_drafts.replies = [(429, error("rate_limit_error", "Too many requests"))]
    assert nylas.create_draft(USER, conn, "s", "b") == "draft-2"
    nylas_drafts.replies = [(503, error("provider_error", "Provider unavailable"))]
    with pytest.raises(nylas.EmailError, match="Check your Drafts folder"):
        nylas.create_draft(USER, conn, "s", "b")
    assert len(nylas_drafts.calls) == 3  # the 503 wasn't retried, so no second copy of the draft


# --- Subscription cancel email ------------------------------------------------------------------------

def test_no_email_connected_is_a_plain_409(client, nylas_drafts):
    r = client.post(f"/api/subscriptions/{sub_id(client)}/email-draft")
    assert r.status_code == 409
    assert r.json()["detail"] == ("Connect your email first. ClawBack saves the draft in your own mailbox, and you "
                                  "send it from there.")
    assert nylas_drafts.calls == []


def test_cancel_email_saved_as_draft(client, nylas_drafts):
    sid = sub_id(client)
    connect()
    r = client.post(f"/api/subscriptions/{sid}/email-draft")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["saved"] is True and out["provider"] == "google" and out["draft_id"] == "draft-1" and out["to"] is None
    assert out["message"] == ("Saved to your Drafts in Gmail. Add the recipient: Hulu's support address. "
                              "Fill in the parts in [brackets]. Then send it from there.")
    sent = nylas_drafts.calls[0]
    assert sent["subject"] == "Please cancel my Hulu subscription" and "[your account email]" in sent["body"]
    assert sent["is_plaintext"] is True
    assert "email: save draft" in [s["stage"] for s in client.get("/api/trace").json()]
    assert all("cancel my Hulu" not in s["note"] for s in client.get("/api/trace").json())  # no email text in the trace


def test_edited_text_and_recipient_are_used(client, nylas_drafts):
    sid = sub_id(client)
    connect("microsoft")
    r = client.post(f"/api/subscriptions/{sid}/email-draft",
                    json={"subject": "Cancel my plan", "body": "Please cancel it today.", "to": "help@hulu.com"})
    assert r.json()["message"] == "Saved to your Drafts in Outlook. Open it there to send."
    assert nylas_drafts.calls[0] == {"subject": "Cancel my plan", "body": "Please cancel it today.",
                                     "is_plaintext": True, "to": [{"email": "help@hulu.com"}]}

    bad = client.post(f"/api/subscriptions/{sid}/email-draft", json={"subject": "s", "body": "b", "to": "Hulu support"})
    assert bad.status_code == 400 and bad.json()["detail"] == "The recipient must be one email address."
    long = client.post(f"/api/subscriptions/{sid}/email-draft", json={"subject": "s", "body": "x" * 30_000})
    assert long.status_code == 400
    assert client.post("/api/subscriptions/nope/email-draft").status_code == 404


@pytest.mark.parametrize("status, data", [
    (403, error("forbidden", "Forbidden")),
    (400, error("invalid_request_error", "Request had insufficient authentication scopes.")),
    (401, error("provider_error", "Insufficient Permission",
                {"error": {"code": 403, "message": "Request had insufficient authentication scopes."}})),
])
def test_read_only_connection_asks_for_reconsent(client, nylas_drafts, status, data):
    sid = sub_id(client)
    connect()
    nylas_drafts.replies = [(status, data)]
    r = client.post(f"/api/subscriptions/{sid}/email-draft")
    assert r.status_code == 403
    assert r.json()["detail"] == "Your email connection can only read. Reconnect to allow drafts."
    email = client.get("/api/connections").json()["email"]
    assert email["needs_reconsent"] is True and email["reconsent_reason"] == nylas.NEEDS_DRAFT_PERMISSION
    assert email["needs_reconnect"] is False  # reading mail still works

    assert client.post(f"/api/subscriptions/{sid}/email-draft").status_code == 200  # e.g. after reconnecting
    assert client.get("/api/connections").json()["email"]["needs_reconsent"] is False


def test_expired_grant_needs_reconnect(client, nylas_drafts):
    sid = sub_id(client)
    connect()
    nylas_drafts.replies = [(401, error("token.unauthorized_access", "Grant is invalid"))]
    r = client.post(f"/api/subscriptions/{sid}/email-draft")
    assert r.status_code == 401 and r.json()["detail"].startswith(nylas.EXPIRED)
    assert client.get("/api/connections").json()["email"]["needs_reconnect"] is True
    again = client.post(f"/api/subscriptions/{sid}/email-draft")
    assert again.status_code == 409 and len(nylas_drafts.calls) == 1  # no call on a grant we know is dead


# --- Finding letters ----------------------------------------------------------------------------------

def test_finding_letter_saved_as_draft(client, nylas_drafts):
    client.post("/api/demo/seed")
    findings = client.get("/api/findings").json()
    dup = next(f for f in findings if f["kind"] == "duplicate_charge")
    connect()
    r = client.post(f"/api/findings/{dup['id']}/email-draft")
    assert r.status_code == 200, r.text
    assert r.json()["message"] == ("Saved to your Drafts in Gmail. Add the recipient: your card issuer's "
                                   "billing-error address (on your statement). Fill in the parts in [brackets]. "
                                   "Then send it from there.")
    letter = client.post(f"/api/findings/{dup['id']}/prepare").json()["message"]
    assert nylas_drafts.calls[0]["subject"] == letter["subject"] and nylas_drafts.calls[0]["body"] == letter["body"]
    assert "to" not in nylas_drafts.calls[0]

    settlement = next(f for f in findings if f["kind"] == "settlement")
    r = client.post(f"/api/findings/{settlement['id']}/email-draft")
    assert r.status_code == 400 and "no email to save" in r.json()["detail"]
    edited = client.post(f"/api/findings/{settlement['id']}/email-draft", json={"subject": "Notes", "body": "My notes"})
    assert edited.status_code == 200  # the user's own text can always be saved
    assert client.post("/api/findings/nope/email-draft").status_code == 404
