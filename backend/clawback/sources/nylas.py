"""Email from any provider (Gmail, Outlook / Hotmail / Microsoft 365, Yahoo, iCloud, other IMAP) through Nylas v3.

Built (checked against developer.nylas.com on 2026-10-22), plain REST over httpx:
  - Hosted OAuth with an API key. start_url() points at {NYLAS_API_URI}/v3/connect/auth without `provider`, so Nylas
    shows its provider picker. The user signs in on the provider's own page and Nylas redirects to our callback.
    finish_connect() swaps the code at /v3/connect/token for a grant_id. The email address and provider come from
    that response, or from GET /v3/grants/{id} when it leaves them out. A random `state` (single use, 10 minutes)
    protects the callback against CSRF. Nylas keeps the provider tokens; we keep only the grant id.
  - fetch_emails(): GET /v3/grants/{id}/messages, newest first, paged with page_token / next_cursor, up to
    EMAIL_MAX_MESSAGES from the last 180 days. Nylas allows only in / limit / page_token next to
    search_query_native for Google and Microsoft, so:
      google: search_query_native in Gmail syntax, with the 180-day limit inside the query;
      microsoft: search_query_native as KQL keywords; the 180-day cut is made here from each message's `date`;
      yahoo, icloud, imap, ews, or a native search the provider refuses: received_after + the triage keyword rules.
  - Bodies: Nylas returns HTML when the message has an HTML part. It is stripped to text (sources/text.py) and cut
    to 5,000 characters, falling back to `snippet`. Bodies stay in memory only, never on disk or in the trace.
  - A 401 / 404 on the grant means it expired or was removed: the connection needs a reconnect. A 429 waits for
    Retry-After (or backs off) and retries. Requests to one grant run one at a time, as Nylas advises.
  - delete_grant(): disconnect deletes the grant at Nylas (best effort).
  - Webhooks (checked against developer.nylas.com on 2026-10-23): Nylas checks the URL once with
    GET ?challenge=<value>, which must echo the value as plain text within 10 seconds. Each notification is a
    CloudEvents-style JSON body {specversion, type, source, id, time, webhook_delivery_attempt,
    data: {application_id, object}}, signed in X-Nylas-Signature: hex HMAC-SHA256 of the raw body, keyed with
    the webhook_secret Nylas returned when the webhook was created (NYLAS_WEBHOOK_SECRET). For message.created
    (and message.created.truncated, sent without the body when over 1 MB) data.object has id and grant_id; for
    grant.expired / grant.deleted data.object has grant_id. Delivery is at least once, up to 3 tries.
    fetch_message() then reads that one message (GET /v3/grants/{id}/messages/{message_id}); the body in the
    notification itself is never used or stored.
  - grant_status(): GET /v3/grants/{id}, for the nightly grant check.
  - create_draft(): POST /v3/grants/{id}/drafts (checked 2026-10-23) with subject, body, is_plaintext=true and
    `to` only when we have a real address. It saves a draft in the user's own mailbox and never sends. Drafts need
    a write scope: Google gmail.compose (Gmail's own API also accepts gmail.modify), Microsoft Mail.ReadWrite,
    Yahoo mail-w. A refusal for missing permission raises DraftNotAllowed, which marks the connection as needing
    re-consent; reading mail keeps working.
MISSING [nylas-production]: the free Sandbox allows 5 connected accounts, and mail passes through Nylas.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Callable
from urllib.parse import quote, urlencode

import httpx

from .. import config
from ..connections import EmailConnection, now
from ..missing import Missing, missing
from ..models import Attachment, Email
from ..pipeline import guard
from ..pipeline.triage import is_candidate
from ..trace import timed
from . import net, text
from .net import SourceError

ENGINE = "nylas"
# Email.source values for mail from this connection (the Nylas provider name, or "email" if it's unknown).
SOURCES = frozenset({"google", "microsoft", "yahoo", "icloud", "imap", "ews", "email"})

DAYS = 180
PAGE_SIZE = 50  # Nylas allows up to 200; smaller pages are gentler on provider rate limits
SCAN_LIMIT = 500  # messages looked at when the provider has no native search
BODY_LIMIT = 5000  # characters
STATE_TTL = 600  # seconds
EXPIRED = "Email connection expired or was revoked. Connect email again."

NATIVE_QUERIES = {
    "google": (
        'newer_than:180d (subscription OR receipt OR invoice OR renewal OR renew OR "free trial" OR trial '
        'OR membership OR "your plan" OR billing OR "payment received" OR "miss you" OR "price change" '
        'OR "price increase" OR "order confirmed" OR "top songs")'
    ),
    # Graph $search (KQL) over from / subject / body. Single words only: phrase quotes would clash with the
    # quotes Graph puts around the whole query.
    "microsoft": "subscription OR receipt OR invoice OR renewal OR renew OR trial OR membership OR billing OR payment",
}

_sleep = time.sleep  # tests replace this


class EmailError(SourceError):
    pass


class EmailExpired(EmailError):
    pass


def require_config() -> None:
    s = config.settings
    if not s.email_configured():
        raise Missing(
            "MISSING [email-keys]: Email isn't configured on this server. Set NYLAS_CLIENT_ID and NYLAS_API_KEY in "
            "backend/.env (Nylas Dashboard: the API key from API Keys, the client ID from the app overview; "
            f"register {s.email_redirect_uri} under Hosted authentication > Callback URIs; EU apps also set "
            "NYLAS_API_URI=https://api.eu.nylas.com), then restart the backend."
        )


# --- Hosted OAuth -----------------------------------------------------------------------------------

_states: dict[str, tuple[str, float]] = {}  # state -> (user id, expiry)
_states_lock = threading.Lock()


def start_url(user_id: str, login_hint: str | None = None) -> str:
    require_config()
    s = config.settings
    state = secrets.token_urlsafe(32)  # Nylas returns it unchanged (max 256 characters)
    with _states_lock:
        _purge_states()
        _states[state] = (user_id, time.time() + STATE_TTL)
    params = {
        "client_id": s.nylas_client_id,
        "redirect_uri": s.email_redirect_uri,
        "response_type": "code",
        "access_type": "online",  # no refresh token for us: Nylas keeps the provider tokens
        "state": state,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{s.nylas_api_uri}/v3/connect/auth?{urlencode(params)}"


def check_state(state: str | None) -> str:
    """Return the user who started this sign-in. Each state works once and expires after 10 minutes."""
    with _states_lock:
        _purge_states()
        entry = _states.pop(state or "", None)
    if entry is None:
        raise EmailError("That sign-in link expired or didn't come from ClawBack. Try connecting again.", status=400)
    return entry[0]


def _purge_states() -> None:
    t = time.time()
    for k in [k for k, (_, exp) in _states.items() if exp < t]:
        del _states[k]


def finish_connect(user_id: str, code: str) -> EmailConnection:
    """Swap the authorization code for a grant and look up its address and provider. The caller saves it."""
    require_config()
    s = config.settings
    with net.client() as c:
        with timed(user_id, "email: sign-in", ENGINE) as info:
            r = _call(c, "POST", "/v3/connect/token", auth=False, json={
                "client_id": s.nylas_client_id,
                "client_secret": s.nylas_api_key,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": s.email_redirect_uri,
            })
            data = net.json_or_empty(r)
            if not r.is_success or not data.get("grant_id"):
                raise EmailError(f"Email sign-in failed: {_reason(r, data)}", status=400)
            info["note"] = "authorization code exchanged for a Nylas grant"
        conn = EmailConnection(grant_id=str(data["grant_id"]), account=data.get("email"),
                               provider=data.get("provider"), connected_at=now())
        if not conn.account or not conn.provider:  # the token response doesn't always carry them
            with timed(user_id, "email: grant details", ENGINE) as info:
                r = _call(c, "GET", f"/v3/grants/{quote(conn.grant_id, safe='')}")
                grant = net.json_or_empty(r).get("data") or {}
                conn.account = conn.account or grant.get("email")
                conn.provider = conn.provider or grant.get("provider")
                info["note"] = f"provider: {conn.provider or 'unknown'}" if r.is_success else f"HTTP {r.status_code}"
    return conn


def delete_grant(user_id: str, grant_id: str) -> bool:
    """Best effort: delete the grant at Nylas. Our saved copy is forgotten either way.

    True when Nylas confirmed, or answered that the grant was already gone."""
    try:
        with net.client() as c, timed(user_id, "email: delete grant", ENGINE) as info:
            r = _call(c, "DELETE", f"/v3/grants/{quote(grant_id, safe='')}")
            info["note"] = "grant deleted at Nylas" if r.is_success else f"delete answered HTTP {r.status_code}"
            return r.is_success or r.status_code == 404
    except Exception:
        return False


def state_user(state: str | None) -> str | None:
    """The user a sign-in state belongs to, without using it up (the callback route locks that user first)."""
    with _states_lock:
        entry = _states.get(state or "")
    return entry[0] if entry and entry[1] >= time.time() else None


def forget_states(user_id: str) -> None:
    """Drop this user's unfinished sign-ins (on delete)."""
    with _states_lock:
        for k in [k for k, (uid, _) in _states.items() if uid == user_id]:
            del _states[k]


def grant_status(user_id: str, grant_id: str) -> str:
    """The nightly grant check: valid | invalid (needs a new sign-in) | gone (deleted at Nylas) | unknown."""
    require_config()
    try:
        with net.client() as c, timed(user_id, "email: grant check", ENGINE) as info:
            r = _call(c, "GET", f"/v3/grants/{quote(grant_id, safe='')}")
            if r.status_code in (401, 403, 404):
                status = "gone"
            elif r.is_success:
                state = str((net.json_or_empty(r).get("data") or {}).get("grant_status") or "valid").lower()
                status = "valid" if state == "valid" else "invalid"
            else:
                status = "unknown"
            info["note"] = f"grant {status}" + ("" if r.is_success else f" (HTTP {r.status_code})")
    except EmailError:  # couldn't reach Nylas: say nothing about the grant
        return "unknown"
    return status


# --- Reading mail -----------------------------------------------------------------------------------

def fetch_emails(user_id: str, conn: EmailConnection) -> list[Email]:
    """Newest subscription-like mail from the last 180 days, up to EMAIL_MAX_MESSAGES."""
    require_config()
    if conn.needs_reconnect:
        raise EmailExpired(conn.error or EXPIRED, status=401)
    limit = max(1, config.settings.email_max_messages)
    cutoff = int((now() - timedelta(days=DAYS)).timestamp())
    with net.client() as c, timed(user_id, "email: read messages", ENGINE) as info:
        how, emails, scanned = _read(c, conn, limit, cutoff)
        info["note"] = (f"read {len(emails)} messages from {conn.provider or 'unknown provider'} "
                        f"({how}; {scanned} looked at, max {limit})")
    return emails


def _read(c: httpx.Client, conn: EmailConnection, limit: int, cutoff: int) -> tuple[str, list[Email], int]:
    query = NATIVE_QUERIES.get(conn.provider or "")
    if query:
        try:
            emails, scanned = _pages(c, conn, {"search_query_native": query}, limit, cutoff)
            return "provider search", emails, scanned
        except EmailError as exc:
            if exc.code != "bad_request":
                raise
            # The provider refused the native query: fall back to a plain scan below.
    emails, scanned = _pages(c, conn, {"received_after": cutoff}, limit, cutoff, keep=is_candidate,
                             scan_limit=SCAN_LIMIT)
    return "recent mail + keyword rules", emails, scanned


def _pages(c: httpx.Client, conn: EmailConnection, params: dict, limit: int, cutoff: int,
           keep: Callable[[Email], bool] = lambda e: True, scan_limit: int | None = None) -> tuple[list[Email], int]:
    path = f"/v3/grants/{quote(conn.grant_id, safe='')}/messages"
    out: list[Email] = []
    scanned, token = 0, None
    while len(out) < limit and (scan_limit is None or scanned < scan_limit):
        query = {**params, "limit": PAGE_SIZE}
        if token:
            query["page_token"] = token
        data = _get_json(c, path, query)
        messages = [m for m in data.get("data") or [] if isinstance(m, dict)]
        scanned += len(messages)
        reached_cutoff = False
        for m in messages:
            email = to_email(m, conn.provider)
            if email is None:
                continue
            if email.received_at.timestamp() < cutoff:  # newest first, so everything after is older too
                reached_cutoff = True
                continue
            if keep(email):
                out.append(email)
        token = data.get("next_cursor")
        if not token or not messages or reached_cutoff:
            break
    return out[:limit], scanned


def to_email(m: dict, provider: str | None) -> Email | None:
    if not m.get("id"):
        return None
    sender = next((str(f["email"]) for f in m.get("from") or [] if isinstance(f, dict) and f.get("email")), "")
    try:
        received = datetime.fromtimestamp(int(m["date"]), tz=timezone.utc)  # unix seconds
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        received = now()
    visible, hidden = text.to_parts(str(m.get("body") or ""))
    body = visible or text.tidy(unescape(str(m.get("snippet") or "")))
    # Hidden HTML stays out of the body. If it carries instructions, the prompt-injection screen is told (labels only).
    strong = guard.signals(hidden)[0] if hidden else []
    return Email(
        id=str(m["id"]),
        received_at=received,
        sender=sender.strip().lower(),
        subject=str(m.get("subject") or "").strip(),
        body_text=body[:BODY_LIMIT],
        source=provider if provider in SOURCES else "email",
        attachments=_attachments(m),
        screen=[f"hidden-text:{s}" for s in strong],
    )


def _attachments(m: dict) -> list[Attachment]:
    """Attachment metadata from a message ({id, filename, content_type, size, is_inline}). No file contents."""
    out: list[Attachment] = []
    for a in m.get("attachments") or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        try:
            size = int(a.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        out.append(Attachment(id=str(a["id"]), filename=str(a.get("filename") or "")[:200],
                              content_type=str(a.get("content_type") or "").split(";")[0].strip().lower()[:100],
                              size=size, inline=bool(a.get("is_inline"))))
    return out


# --- Attachments ------------------------------------------------------------------------------------

ATTACHMENT_LIMIT = 5 * 1024 * 1024  # bytes; receipts are small, and anything bigger isn't read


def download_attachment(user_id: str, conn: EmailConnection, message_id: str, attachment_id: str,
                        limit: int = ATTACHMENT_LIMIT) -> bytes | None:
    """One attachment's bytes, in memory only (never written to disk or the trace). None when it is too big or the
    download fails. GET /v3/grants/{grant_id}/attachments/{attachment_id}/download?message_id=... answers with the
    raw file (application/octet-stream). Checked against developer.nylas.com on 2026-10-23."""
    require_config()
    if conn.needs_reconnect:
        return None
    s = config.settings
    path = f"/v3/grants/{quote(conn.grant_id, safe='')}/attachments/{quote(attachment_id, safe='')}/download"
    with net.client() as c, timed(user_id, "email: attachment", ENGINE) as info:
        for attempt in range(3):
            chunks: list[bytes] = []
            total = 0
            try:
                with c.stream("GET", s.nylas_api_uri + path, params={"message_id": message_id},
                              headers={"Authorization": f"Bearer {s.nylas_api_key}"}) as r:
                    if r.status_code in (429, 502, 503, 504) and attempt < 2:
                        _sleep(_backoff(r, attempt))
                        continue
                    if not r.is_success:
                        info["note"] = f"attachment download answered HTTP {r.status_code}"
                        return None
                    for chunk in r.iter_bytes():
                        total += len(chunk)
                        if total > limit:
                            info["note"] = f"attachment skipped: over {limit // (1024 * 1024)} MB"
                            return None
                        chunks.append(chunk)
            except httpx.HTTPError:
                info["note"] = "attachment download failed: couldn't reach Nylas"
                return None
            info["note"] = f"attachment downloaded ({total:,} bytes, kept in memory only)"
            return b"".join(chunks)
        info["note"] = "attachment download rate limited"
        return None


# --- HTTP -------------------------------------------------------------------------------------------

def _call(c: httpx.Client, method: str, path: str, auth: bool = True, retry_server_errors: bool = True,
          **kw) -> httpx.Response:
    """One request, retried on 429 (honouring Retry-After) and on 502 / 503 / 504. retry_server_errors=False keeps
    the 429 retry only, for calls that create something (a retried draft could be saved twice)."""
    s = config.settings
    headers = {"Accept": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {s.nylas_api_key}"
    retry_on = (429, 502, 503, 504) if retry_server_errors else (429,)
    for attempt in range(5):
        try:
            r = c.request(method, s.nylas_api_uri + path, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise EmailError("Couldn't reach Nylas. Check the network and try again.") from exc
        if r.status_code in retry_on and attempt < 4:
            _sleep(_backoff(r, attempt))
            continue
        return r
    return r


def _get_json(c: httpx.Client, path: str, params: dict) -> dict:
    return _json_or_raise(_call(c, "GET", path, params=params))


def _json_or_raise(r: httpx.Response) -> dict:
    if r.is_success:
        return net.json_or_empty(r)
    data = net.json_or_empty(r)
    if r.status_code in (401, 404):  # grant expired, revoked or deleted
        reason = _reason(r, data)
        raise EmailExpired(f"{EXPIRED} (Nylas: {reason})" if reason else EXPIRED, status=401, code="grant_invalid")
    if r.status_code == 429:
        raise EmailError("The email provider is limiting requests right now. Try Sync again in a minute.")
    raise EmailError(f"Nylas error: {_reason(r, data) or f'HTTP {r.status_code}'}",
                     code="bad_request" if r.status_code == 400 else None)


def _reason(r: httpx.Response, data: dict) -> str:
    err = data.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("type") or "")
    return str(data.get("error_description") or err or f"HTTP {r.status_code}")


def _backoff(r: httpx.Response, attempt: int) -> float:
    try:
        return min(float(r.headers.get("retry-after", "")), 30.0)
    except ValueError:
        return float(min(2**attempt, 16))


# --- Webhooks ---------------------------------------------------------------------------------------

MESSAGE_EVENTS = frozenset({"message.created", "message.created.truncated", "message.created.transformed"})
GRANT_LOST_EVENTS = frozenset({"grant.expired", "grant.deleted"})


@dataclass
class WebhookEvent:
    type: str
    grant_id: str | None
    message_id: str | None  # for message.* events


def webhook_secret() -> str:
    secret = config.settings.nylas_webhook_secret
    if not secret:
        raise Missing("Email webhooks aren't set up on this server. Create the webhook in Nylas, put its "
                      "webhook_secret in NYLAS_WEBHOOK_SECRET in backend/.env, then restart the backend.")
    return secret


def verify_webhook(raw: bytes, signature: str | None) -> bool:
    """X-Nylas-Signature is the hex HMAC-SHA256 of the raw body, keyed with the webhook secret."""
    expected = hmac.new(webhook_secret().encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, (signature or "").strip().lower())


def parse_webhook(payload: dict) -> WebhookEvent:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    obj = data.get("object") if isinstance(data.get("object"), dict) else {}
    kind = str(payload.get("type") or "")
    grant = obj.get("grant_id") or data.get("grant_id")
    message = obj.get("id") if kind.startswith("message.") else None
    return WebhookEvent(kind, str(grant) if grant else None, str(message) if message else None)


def fetch_message(user_id: str, conn: EmailConnection, message_id: str) -> Email | None:
    """One message, for a webhook. None when it is gone or older than the 180-day window."""
    require_config()
    if conn.needs_reconnect:
        raise EmailExpired(conn.error or EXPIRED, status=401)
    path = f"/v3/grants/{quote(conn.grant_id, safe='')}/messages/{quote(message_id, safe='')}"
    with net.client() as c, timed(user_id, "email: read new message", ENGINE) as info:
        r = _call(c, "GET", path)
        if r.status_code == 404:  # deleted already (a lost grant shows up in the nightly grant check)
            info["note"] = "the new message is gone"
            return None
        email = to_email(_json_or_raise(r).get("data") or {}, conn.provider)
        if email and email.received_at < now() - timedelta(days=DAYS):
            email = None
        info["note"] = "read 1 new message" if email else "new message skipped"
    return email


# --- Drafts -----------------------------------------------------------------------------------------

NEEDS_DRAFT_PERMISSION = "Your email connection can only read. Reconnect to allow drafts."
PROVIDER_NAMES = {"google": "Gmail", "microsoft": "Outlook", "yahoo": "Yahoo Mail", "icloud": "iCloud Mail",
                  "ews": "Exchange", "imap": "your mailbox"}
ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")
_PERMISSION_WORDS = re.compile(r"scope|permission|insufficient|not allowed|forbidden|access denied|read-?only", re.I)


class DraftNotAllowed(EmailError):
    """The provider refused to save a draft because the grant can only read mail."""


def provider_name(provider: str | None) -> str:
    return PROVIDER_NAMES.get(provider or "", "your mailbox")


def is_address(text: str | None) -> bool:
    return bool(text and ADDRESS.fullmatch(text.strip()))


def create_draft(user_id: str, conn: EmailConnection, subject: str, body: str, to: str | None = None) -> str:
    """Save a plain-text draft in the user's own mailbox and return its id. It is never sent: the user opens it in
    their mail app and presses send. `to` is used only when it is a single email address."""
    require_config()
    if conn.needs_reconnect:
        raise EmailExpired(conn.error or EXPIRED, status=401)
    payload: dict = {"subject": subject.strip()[:300], "body": body, "is_plaintext": True}
    if is_address(to):
        payload["to"] = [{"email": to.strip()}]
    with net.client() as c, timed(user_id, "email: save draft", ENGINE) as info:
        r = _call(c, "POST", f"/v3/grants/{quote(conn.grant_id, safe='')}/drafts", retry_server_errors=False,
                  json=payload)
        data = net.json_or_empty(r)
        draft_id = (data.get("data") or {}).get("id") if isinstance(data.get("data"), dict) else None
        if r.is_success and draft_id:
            info["note"] = f"draft saved in {provider_name(conn.provider)} (not sent)"
            return str(draft_id)
        reason = _reason(r, data)
        provider_error = data.get("error", {}).get("provider_error") if isinstance(data.get("error"), dict) else None
        if r.status_code == 403 or (r.status_code in (400, 401) and _PERMISSION_WORDS.search(f"{reason} {provider_error or ''}")):
            raise DraftNotAllowed(NEEDS_DRAFT_PERMISSION, status=403, code="insufficient_scope")
        if r.status_code in (401, 404):
            raise EmailExpired(f"{EXPIRED} (Nylas: {reason})" if reason else EXPIRED, status=401, code="grant_invalid")
        if r.status_code == 429:
            raise EmailError("The email provider is limiting requests right now. Try again in a minute.")
        if r.is_success or r.status_code >= 500:
            raise EmailError("Your email provider didn't confirm the draft. Check your Drafts folder before you "
                             "try again.")
        raise EmailError(f"Couldn't save the draft: {reason or f'HTTP {r.status_code}'}")


# --- Still MISSING ----------------------------------------------------------------------------------

