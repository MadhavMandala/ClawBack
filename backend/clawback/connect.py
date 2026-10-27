"""Connect, sync and disconnect the user's own email (any provider, via Nylas) and bank (Plaid), and switch between
demo and real data.

The first time a real source connects while the user is looking at demo data, the demo data is dropped
(store.use_real_data), so real and fake data never mix. POST /api/demo/seed switches back to demo; saved
connections stay saved but unused until the next connect or a restart.

Single-user mode: on startup, saved connections put the user straight into real mode and are synced again
(restore()). Visitor sessions load lazily: a real-mode user loaded from disk has no mail in memory (bodies are
never saved, see store.py), so ensure_fresh() reads it again before the first request uses it.

Webhooks (on_new_message, on_plaid_update) and the nightly job pull in the background, re-run the pipeline,
and record an in-app alert for each flag or finding that is new (alerts.py).
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from . import alerts, config, connections
from .connections import now
from .missing import Missing
from .pipeline.run import run
from .pipeline.triage import is_candidate
from .sources import nylas, plaid
from .sources.net import SourceError
from .sources.nylas import EmailError, EmailExpired
from .sources.plaid import PlaidError
from .store import store
from .trace import drop, record

SOURCES = ("email", "plaid")


def status(user_id: str) -> dict:
    c, s = connections.get(user_id), config.settings
    e, p = c.email, c.plaid
    return {
        "mode": store.user(user_id).mode,
        "email": {
            "configured": s.email_configured(),
            "connected": e is not None,
            "account": e.account if e else None,
            "provider": e.provider if e else None,
            "last_sync": _iso(e.last_sync) if e else None,
            "error": e.error if e else None,
            "needs_reconnect": bool(e and e.needs_reconnect),
            # Connected only: reading works, but saving drafts was refused, so connect again to allow drafts.
            **({"needs_reconsent": e.needs_reconsent, "reconsent_reason": e.reconsent_reason} if e else {}),
        },
        "plaid": {
            "configured": s.plaid_configured(),
            "connected": p is not None,
            "institution": p.institution if p else None,
            "last_sync": _iso(p.last_sync) if p else None,
            "error": p.error if p else None,
            "needs_reconnect": bool(p and p.needs_reconnect),
        },
    }


def _iso(d) -> str | None:
    return d.isoformat(timespec="seconds") if d else None


# --- Email (Nylas) ----------------------------------------------------------------------------------

def finish_email(state: str | None, code: str | None, error: str | None, error_description: str | None = None) -> str:
    """Handle the redirect back from Nylas. Returns where to send the browser: the dashboard, with a short result."""
    origin = config.settings.return_origin
    user_id = None
    purpose = nylas.state_purpose(state)  # read before check_state uses the state up
    try:
        user_id = nylas.check_state(state)  # CSRF check first, even when an error came back
        if error:
            raise EmailError("Email sign-in was cancelled." if error == "access_denied"
                             else f"Email sign-in failed ({error_description or error}).", status=400)
        if not code:
            raise EmailError("No authorization code came back. Try connecting again.", status=400)
        drop(user_id, (nylas.ENGINE,))
        new = nylas.finish_connect(user_id, code)
        old = connections.get(user_id).email
        if old and old.grant_id != new.grant_id:
            release_grant(user_id, old.grant_id)  # one inbox at a time; the Sandbox counts every grant
        if purpose == "send" and store.user(user_id).mode != "real":
            # From a Send button in the demo: keep the demo month, read nothing, use the inbox only to send.
            new.send_only = True
            connections.set_email(user_id, new)
            return f"{origin}/dashboard?connected=email-send"
        connections.set_email(user_id, new)
        was_demo = _enter_real_mode(user_id)
        _pull_email(user_id)
        if was_demo:
            _pull_others(user_id, "email")
        run(user_id)
        return f"{origin}/dashboard?connected=email"
    except SourceError as exc:
        message = exc.safe_message
    except Missing as exc:
        message = ("Email isn't configured on the server. See backend/.env.example."
                   if "[email-keys]" in str(exc) else str(exc))
    except Exception as exc:
        if user_id:
            record(user_id, "email: connect", nylas.ENGINE, status="error", note=f"unexpected {type(exc).__name__}")
        message = "Email connect failed unexpectedly. The trace has details."
    if user_id and store.user(user_id).mode == "real":
        _rerun_quietly(user_id)  # show the error rows and whatever data there is
    return f"{origin}/dashboard?{urlencode({'connect_error': message[:200]})}"


def release_grant(user_id: str, grant_id: str) -> bool:
    """Delete a grant at Nylas when this user lets go of it, unless another session still uses the same grant
    (the same inbox connected in two browsers). True when it is gone at Nylas or still needed elsewhere."""
    if connections.shared("email", grant_id, user_id):
        record(user_id, "email: delete grant", nylas.ENGINE, note="kept at Nylas: another session uses this inbox")
        return True
    return nylas.delete_grant(user_id, grant_id)


def _pull_email(user_id: str) -> int:
    conn = connections.get(user_id).email
    if conn is None:
        raise EmailError("No email account is connected.", status=400)
    if conn.send_only:
        store.mark_warm(user_id)  # nothing to read, so nothing to wait for
        return 0  # connected only to send: its mail is never read
    try:
        emails = nylas.fetch_emails(user_id, conn)
    except SourceError as exc:
        conn.error = exc.safe_message
        conn.needs_reconnect = conn.needs_reconnect or isinstance(exc, EmailExpired)
        connections.update_email(user_id, conn)
        raise
    if connections.get(user_id).email is None:  # disconnected while we were reading
        return 0
    u = store.user(user_id)
    u.emails = [e for e in u.emails if e.source not in nylas.SOURCES] + emails
    store.mark_warm(user_id)
    conn.last_sync, conn.error, conn.needs_reconnect = now(), None, False
    connections.update_email(user_id, conn)
    return len(emails)


# --- Plaid ------------------------------------------------------------------------------------------

def connect_plaid(user_id: str, public_token: str, institution: str | None) -> dict:
    drop(user_id, (plaid.ENGINE,))
    new = plaid.exchange(user_id, public_token, institution)
    old = connections.get(user_id).plaid
    if old and old.item_id != new.item_id:
        plaid.remove_item(user_id, old.access_token)  # one bank at a time for now
    connections.set_plaid(user_id, new)
    was_demo = _enter_real_mode(user_id)
    u = store.user(user_id)
    u.transactions = [t for t in u.transactions if t.source != "plaid"]
    u.plaid_cursor, u.bank_accounts = None, {}
    try:
        added, pending = _pull_plaid(user_id, wait=True)
        if was_demo:
            _pull_others(user_id, "plaid")
    finally:
        _rerun_quietly(user_id)
    return {"added_transactions": added, "institution": new.institution, "pending": pending}


def _pull_plaid(user_id: str, wait: bool) -> tuple[int, bool]:
    conn = connections.get(user_id).plaid
    if conn is None:
        raise PlaidError("No bank is connected.", status=400)
    u = store.user(user_id)
    # Card statement dates first (best effort, never raises): they set the real dispute deadlines.
    accounts = plaid.fetch_accounts(user_id, conn.access_token, date.today())
    if accounts is not None:
        u.bank_accounts = accounts
    try:
        changes = plaid.fetch_changes(user_id, conn.access_token, u.plaid_cursor, wait=wait)
    except SourceError as exc:
        conn.error, conn.needs_reconnect = exc.safe_message, exc.code in plaid.RECONNECT_CODES
        connections.update_plaid(user_id, conn)
        raise
    if connections.get(user_id).plaid is None:  # disconnected while we were syncing
        return 0, False
    held = {t.id: t for t in u.transactions if t.source == "plaid"}
    for t in changes.added + changes.modified:
        held[t.id] = t
    for tx_id in changes.removed:
        held.pop(tx_id, None)
    u.transactions = [t for t in u.transactions if t.source != "plaid"] + sorted(held.values(), key=lambda t: t.date)
    u.plaid_cursor = changes.cursor
    conn.cursor, conn.last_sync, conn.error, conn.needs_reconnect = changes.cursor, now(), None, False
    connections.update_plaid(user_id, conn)
    return len(changes.added), changes.pending


def _enter_real_mode(user_id: str) -> bool:
    """Switch to real data. True when this dropped the demo data (the user was in demo mode)."""
    was_demo = store.user(user_id).mode != "real"
    store.use_real_data(user_id)
    return was_demo


def _pull_others(user_id: str, just_connected: str) -> None:
    """Coming back from demo mode: also pull the other source that is still saved, so its data shows too."""
    c = connections.get(user_id)
    if just_connected != "email" and c.email:
        _attempt(user_id, nylas.ENGINE, lambda: {"emails": _pull_email(user_id)})
    if just_connected != "plaid" and c.plaid:
        _attempt(user_id, plaid.ENGINE, lambda: dict(zip(("added_transactions", "pending"), _pull_plaid(user_id, wait=False))))


# --- Sync, startup, disconnect ----------------------------------------------------------------------

def sync_now(user_id: str) -> dict:
    """POST /api/sync. Demo mode: re-run the pipeline. Real mode: pull every connected source first."""
    u = store.user(user_id)
    if u.mode != "real":
        return {**run(user_id), "mode": u.mode, "synced": {}}
    return sync_sources(user_id, wait_for_plaid=True)


def sync_sources(user_id: str, wait_for_plaid: bool) -> dict:
    """Pull each connected source (one failing doesn't stop the others), then run the pipeline."""
    c = connections.get(user_id)
    synced: dict[str, dict] = {}
    if c.email:
        synced["email"] = _attempt(user_id, nylas.ENGINE, lambda: {"emails": _pull_email(user_id)})
    if c.plaid:
        wait = wait_for_plaid and store.user(user_id).plaid_cursor is None

        def pull() -> dict:
            added, pending = _pull_plaid(user_id, wait=wait)
            return {"added_transactions": added, "pending": pending}

        synced["plaid"] = _attempt(user_id, plaid.ENGINE, pull)
    return {**run(user_id), "mode": "real", "synced": synced}


def _attempt(user_id: str, engine: str, pull) -> dict:
    drop(user_id, (engine,))
    try:
        return {"ok": True, **pull(), "error": None}
    except SourceError as exc:
        return {"ok": False, "error": exc.safe_message}
    except Missing as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        record(user_id, "sync", engine, status="error", note=f"unexpected {type(exc).__name__}")
        return {"ok": False, "error": "Unexpected error. The trace has details."}


def restore(user_id: str) -> bool:
    """Startup (single-user mode): if connections were saved, switch to real data and pull it again. Never raises.

    What was saved (decisions, check-ins, statements, bank history and its cursor) is kept; mail is read again.
    Returns True when the user ended up in real mode (so the demo shouldn't be seeded).
    """
    try:
        c = connections.get(user_id)
        if not (c.plaid or (c.email and not c.email.send_only)):  # a send-only inbox never leaves the demo
            return False
        store.use_real_data(user_id)
        sync_sources(user_id, wait_for_plaid=False)  # reads the mail again; if it can't, the saved results stay
    except Exception as exc:
        reason = getattr(exc, "safe_message", None) or type(exc).__name__
        record(user_id, "startup sync", "code", status="error", note=f"restoring saved connections failed: {reason}")
    return store.user(user_id).mode == "real"


MAIL_RETRY_S = 300


def ensure_fresh(user_id: str) -> dict | None:
    """A real-mode user loaded from disk has no mail in memory (bodies are never saved): read it again before
    anything re-runs the pipeline on it. Never raises.

    While the mail can't be read (Nylas unreachable, say), the user stays "cold": pipeline runs keep the saved
    results (pipeline/run.py), and the read is tried again after MAIL_RETRY_S (Sync tries at once). An inbox
    that needs a new sign-in can't be read until the user reconnects, so the pipeline then runs without its mail.
    Returns the email pull's result when it tried to read, None when nothing was needed.
    """
    store.user(user_id)  # load it, if this process hasn't yet
    if not store.is_cold(user_id):
        return None
    conn = connections.get(user_id).email
    if store.user(user_id).mode != "real" or conn is None or conn.needs_reconnect or conn.send_only:
        store.mark_warm(user_id)  # a send-only inbox is never read, so there's no mail to wait for
        return None
    if not store.retry_due(user_id):
        return {"ok": False, "error": "The mail will be read again in a few minutes."}
    result = _attempt(user_id, nylas.ENGINE, lambda: {"emails": _pull_email(user_id)})
    if not result["ok"]:
        conn = connections.get(user_id).email
        if conn is None or conn.needs_reconnect:
            store.mark_warm(user_id)
        else:
            store.retry_later(user_id, MAIL_RETRY_S)
    return result


# --- Background updates: webhooks and the nightly job -------------------------------------------------

def _rerun_and_alert(user_id: str, before: set[str]) -> int:
    _rerun_quietly(user_id)
    return alerts.record_new(user_id, before, store.user(user_id))


def on_new_message(user_id: str, grant_id: str, message_id: str | None) -> str:
    """Nylas says a message arrived: read it and, if it may be about money, re-run the pipeline. Never raises."""
    conn = connections.get(user_id).email
    if conn is None or conn.grant_id != grant_id or store.user(user_id).mode != "real" or conn.send_only:
        return "ignored"  # a send-only inbox is never read, webhooks included
    before = set(alerts.keys(store.user(user_id)))
    if store.is_cold(user_id):
        ensure_fresh(user_id)  # reads every recent message, this one included
        if store.is_cold(user_id):
            return "error"
    elif not message_id:
        if not _attempt(user_id, nylas.ENGINE, lambda: {"emails": _pull_email(user_id)})["ok"]:
            return "error"
    else:
        try:
            email = nylas.fetch_message(user_id, conn, message_id)
        except SourceError as exc:
            conn.error = exc.safe_message
            conn.needs_reconnect = conn.needs_reconnect or isinstance(exc, EmailExpired)
            connections.update_email(user_id, conn)
            return "error"
        except Exception as exc:
            record(user_id, "email: read new message", nylas.ENGINE, status="error",
                   note=f"unexpected {type(exc).__name__}")
            return "error"
        if email is None or not is_candidate(email):
            return "not subscription mail"
        u = store.user(user_id)
        kept = [e for e in u.emails if e.id != email.id] + [email]
        mail = sorted((e for e in kept if e.source in nylas.SOURCES), key=lambda e: e.received_at, reverse=True)
        u.emails = [e for e in kept if e.source not in nylas.SOURCES] + mail[:max(1, config.settings.email_max_messages)]
    _rerun_and_alert(user_id, before)
    return "processed"


def on_plaid_update(user_id: str, item_id: str) -> str:
    """Plaid says new transactions are ready for this item: pull them and re-run the pipeline. Never raises."""
    conn = connections.get(user_id).plaid
    if conn is None or conn.item_id != item_id or store.user(user_id).mode != "real":
        return "ignored"
    before = set(alerts.keys(store.user(user_id)))
    ensure_fresh(user_id)
    result = _attempt(user_id, plaid.ENGINE,
                      lambda: dict(zip(("added_transactions", "pending"), _pull_plaid(user_id, wait=False))))
    if not store.is_cold(user_id):  # otherwise the run would drop every email finding: wait for the mail
        _rerun_and_alert(user_id, before)
    return "processed" if result.get("ok") else "error"


def check_grant(user_id: str) -> str | None:
    """The nightly grant check. Marks the connection for a new sign-in when Nylas says the grant is gone or invalid.
    Returns the grant status (valid | invalid | gone | unknown), or None when no email is connected."""
    conn = connections.get(user_id).email
    if conn is None or not config.settings.email_configured():
        return None
    status = nylas.grant_status(user_id, conn.grant_id)
    if status in ("gone", "invalid"):
        connections.mark_reconnect(user_id, "email", nylas.EXPIRED)
    return status


def nightly_refresh(user_id: str) -> dict:
    """The nightly job for one user: check the grant, pull every source, re-run the pipeline (price checks
    included) and alert on what is new. A user in demo mode keeps their saved connections unused: grant check only.

    When the mail can't be read for now, the pipeline isn't re-run (it would drop every email finding); the bank
    data is still pulled and the error shows on the connection. See ensure_fresh()."""
    grant = check_grant(user_id)
    u = store.user(user_id)
    if u.mode != "real":
        return {"grant": grant, "synced": {}, "alerts": 0, "mode": u.mode, "rerun": False}
    before = set(alerts.keys(u))
    c = connections.get(user_id)
    synced: dict[str, dict] = {}
    if c.email:
        synced["email"] = ensure_fresh(user_id) or _attempt(user_id, nylas.ENGINE,
                                                            lambda: {"emails": _pull_email(user_id)})
    else:
        store.mark_warm(user_id)
    if c.plaid:
        synced["plaid"] = _attempt(user_id, plaid.ENGINE,
                                   lambda: dict(zip(("added_transactions", "pending"), _pull_plaid(user_id, wait=False))))
    rerun = not store.is_cold(user_id)
    added = _rerun_and_alert(user_id, before) if rerun else 0
    return {"grant": grant, "synced": synced, "alerts": added, "mode": "real", "rerun": rerun}


def disconnect(user_id: str, source: str) -> dict:
    """Forget the connection (and tell Nylas / Plaid, best effort) and drop that source's data from memory."""
    u, c = store.user(user_id), connections.get(user_id)
    if source == "email":
        store.mark_warm(user_id)  # no mail left to read again
        drop(user_id, (nylas.ENGINE,))
        if c.email:
            release_grant(user_id, c.email.grant_id)
        connections.set_email(user_id, None)
        u.emails = [e for e in u.emails if e.source not in nylas.SOURCES]
    elif source == "plaid":
        drop(user_id, (plaid.ENGINE,))
        if c.plaid:
            plaid.remove_item(user_id, c.plaid.access_token)
        connections.set_plaid(user_id, None)
        u.transactions = [t for t in u.transactions if t.source != "plaid"]
        u.plaid_cursor, u.bank_accounts = None, {}
    else:
        raise ValueError(f"unknown source {source!r}")
    if u.mode == "real":
        _rerun_quietly(user_id)
    return status(user_id)


def _rerun_quietly(user_id: str) -> None:
    try:
        run(user_id)
    except Exception as exc:
        record(user_id, "pipeline", "code", status="error", note=f"pipeline failed: {type(exc).__name__}")
