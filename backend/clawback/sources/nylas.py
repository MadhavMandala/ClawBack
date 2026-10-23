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

MISSING [email-webhooks]: Nylas message.created webhooks. Each Sync re-reads the newest matching mail instead.
MISSING [email-drafts]: cancellation emails saved as drafts through Nylas's drafts API.
MISSING [nylas-production]: the free Sandbox allows 5 connected accounts, and mail passes through Nylas.
"""

from __future__ import annotations

import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Callable
from urllib.parse import quote, urlencode

import httpx

from .. import config
from ..connections import EmailConnection, now
from ..missing import Missing, missing
from ..models import Email
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


def delete_grant(user_id: str, grant_id: str) -> None:
    """Best effort: delete the grant at Nylas. Our saved copy is forgotten either way."""
    try:
        with net.client() as c, timed(user_id, "email: delete grant", ENGINE) as info:
            r = _call(c, "DELETE", f"/v3/grants/{quote(grant_id, safe='')}")
            info["note"] = "grant deleted at Nylas" if r.is_success else f"delete answered HTTP {r.status_code}"
    except Exception:
        pass


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
    body = text.to_text(str(m.get("body") or "")) or text.tidy(unescape(str(m.get("snippet") or "")))
    return Email(
        id=str(m["id"]),
        received_at=received,
        sender=sender.strip().lower(),
        subject=str(m.get("subject") or "").strip(),
        body_text=body[:BODY_LIMIT],
        source=provider if provider in SOURCES else "email",
    )


# --- HTTP -------------------------------------------------------------------------------------------

def _call(c: httpx.Client, method: str, path: str, auth: bool = True, **kw) -> httpx.Response:
    """One request, retried on 429 (honouring Retry-After) and on 502 / 503 / 504."""
    s = config.settings
    headers = {"Accept": "application/json"}
    if auth:
        headers["Authorization"] = f"Bearer {s.nylas_api_key}"
    for attempt in range(5):
        try:
            r = c.request(method, s.nylas_api_uri + path, headers=headers, **kw)
        except httpx.HTTPError as exc:
            raise EmailError("Couldn't reach Nylas. Check the network and try again.") from exc
        if r.status_code in (429, 502, 503, 504) and attempt < 4:
            _sleep(_backoff(r, attempt))
            continue
        return r
    return r


def _get_json(c: httpx.Client, path: str, params: dict) -> dict:
    r = _call(c, "GET", path, params=params)
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


# --- Still MISSING ----------------------------------------------------------------------------------

def handle_webhook(payload: dict) -> None:
    missing("email-webhooks")


def create_draft(user_id: str, to: str, subject: str, body: str) -> str:
    missing("email-drafts")
