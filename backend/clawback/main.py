"""ClawBack API (prototype). Run with:  uvicorn clawback.main:app --reload --port 8000

Every route that reads or changes a person's data takes `user_id: UserId` (sessions.current_user): the visitor
behind the X-ClawBack-Session header, or "demo" with CLAWBACK_SESSIONS=single. The user is saved after each
request. Business functions take that user_id; nothing here may use a fixed user.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import alerts, connect, connections, demo, drafts, llm, sessions
from .config import settings
from .features import features_payload
from .findings import actions
from .findings.detect import sort_key
from .models import ActionPrep, Finding
from .missing import REGISTRY, Missing, missing
from .pipeline import rights
from .pipeline.cancel import cancel_prep
from .pipeline.confirm import mark_done
from .pipeline.recommend import alternatives
from .pipeline.recovered import history
from .pipeline.run import best_saving, run, summary
from .sessions import AddonUserId, UserId, user_scope
from .sources import nylas, plaid
from .sources.net import SourceError
from .sources.statements import parse_upload
from .store import store
from .trace import view

log = logging.getLogger("clawback.api")


def seed(user_id: str, today: date | None = None) -> dict:
    """Switch to demo mode and load the fake data. Saved connections stay saved but unused."""
    return demo.seed(user_id, today)


@asynccontextmanager
async def lifespan(app: FastAPI):
    warm = None
    if settings.single_user:
        # The one local user: saved email / bank connections mean real mode, so sync them (failures only add
        # trace rows); otherwise a fresh demo, as before persistence.
        user_id = sessions.ensure_single()
        if not connect.restore(user_id) and settings.autoseed_demo:
            seed(user_id)
        store.save(user_id)
    elif settings.autoseed_demo and llm.available():
        # Build today's demo now, so the first visitor doesn't wait for its model calls.
        warm = asyncio.create_task(run_in_threadpool(demo.template, date.today()))
    yield
    if warm is not None:
        with contextlib.suppress(Exception):
            await warm


app = FastAPI(title="ClawBack (prototype)", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_origin_regex=settings.frontend_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],  # includes X-ClawBack-Session; the session id only ever comes back in a JSON body
)


@app.exception_handler(Missing)
async def missing_handler(request: Request, exc: Missing):
    return JSONResponse(status_code=501, content={"missing": str(exc)})


@app.exception_handler(SourceError)
async def source_error_handler(request: Request, exc: SourceError):
    # Email / Plaid failures: a short message, never a stack trace.
    return JSONResponse(status_code=exc.status, content={"detail": exc.safe_message})


def _sub(user_id: str, sub_id: str):
    sub = store.user(user_id).subscriptions.get(sub_id)
    if sub is None:
        raise HTTPException(404, f"no subscription {sub_id!r}")
    return sub


# --- Status ---------------------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "integrations": settings.integrations(), "models": llm.MODELS,
            "sessions": settings.sessions}


@app.get("/api/missing")
def missing_list():
    return REGISTRY


@app.get("/api/features")
def feature_board():
    """Every planned feature and its phase (planned, started, built, live), for the build-status board."""
    return features_payload()


@app.get("/api/trace")
def trace(user_id: UserId):
    return view(user_id)


# --- Session --------------------------------------------------------------------------------------

@app.post("/api/session")
def new_session(request: Request):
    """A new visitor session with its own demo data. The id comes back once; send it as X-ClawBack-Session."""
    if settings.single_user:
        return {"session_id": "single-user"}
    try:
        return {"session_id": sessions.create(request.client.host if request.client else None)}
    except sessions.TooManySessions:
        raise HTTPException(429, "Too many new sessions from this address. Try again in an hour.")


@app.get("/api/me")
def me(user_id: UserId):
    """Session details for a settings page. Never tokens or ids."""
    return sessions.info(user_id)


@app.delete("/api/me")
def delete_me(user_id: UserId):
    """Delete everything ClawBack holds for this session, and end its email and bank connections."""
    return sessions.delete(user_id)


# --- Gmail add-on -----------------------------------------------------------------------------------------

@app.post("/api/addon-token")
def addon_token(user_id: UserId):
    """A read-only token for the Gmail add-on (settings hands it to the extension). It opens /api/email-flags only.
    Asking again replaces the old one."""
    return {"token": sessions.create_addon_token(user_id)}


@app.delete("/api/addon-token")
def addon_token_revoke(user_id: UserId):
    sessions.revoke_addon(user_id)
    return {"ok": True}


@app.get("/api/email-flags")
def email_flags(user_id: AddonUserId):
    """Flags for Gmail rows, keyed by Gmail ids. MISSING [gmail-addon]: the flags themselves come in the next step
    (docs/superpowers/plans/2026-10-23-gmail-extension.md, Task 1); for now the list is empty."""
    return {"flags": [], "generated_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/alerts")
def get_alerts(user_id: UserId):
    """In-app alerts: new flags and findings that background updates (nightly job, webhooks) found."""
    return alerts.list_for(user_id)


class Seen(BaseModel):
    ids: list[int] | None = None  # None: mark every alert seen


@app.post("/api/alerts/seen")
def alerts_seen(user_id: UserId, body: Seen | None = None):
    changed = alerts.mark_seen(user_id, body.ids if body else None)
    return {"ok": True, "marked": changed, "unseen": alerts.unseen(user_id)}


# --- Dashboard ------------------------------------------------------------------------------------

@app.post("/api/demo/seed")
def demo_seed(user_id: UserId):
    return seed(user_id)


@app.post("/api/sync")
def sync(user_id: UserId):
    """Real mode: pull from every connected source, then re-run. Demo mode: just re-run.

    With webhooks set up, new mail and bank data also arrive on their own (see /api/ingest/*/webhook).
    """
    return connect.sync_now(user_id)


@app.get("/api/summary")
def get_summary(user_id: UserId):
    return summary(user_id)


@app.get("/api/subscriptions")
def subscriptions(user_id: UserId):
    subs = list(store.user(user_id).subscriptions.values())
    return sorted(subs, key=lambda s: (-best_saving(s), -s.monthly_cost))


class Checkin(BaseModel):
    used: bool


@app.post("/api/subscriptions/{sub_id}/checkin")
def checkin(user_id: UserId, sub_id: str, body: Checkin):
    _sub(user_id, sub_id)
    store.user(user_id).checkins[sub_id].append((date.today(), body.used))
    run(user_id)
    return _sub(user_id, sub_id)


@app.post("/api/subscriptions/{sub_id}/keep")
def keep(user_id: UserId, sub_id: str):
    _sub(user_id, sub_id)
    store.user(user_id).kept[sub_id] = date.today()
    store.user(user_id).cancel_pending.pop(sub_id, None)
    run(user_id)
    return _sub(user_id, sub_id)


@app.post("/api/subscriptions/{sub_id}/cancel-prep")
def prepare_cancel(user_id: UserId, sub_id: str):
    """Gather the cancel link, steps and (when the merchant takes one) email. Never cancels or sends anything.
    Opening the panel doesn't mark it as cancelling: the user says so with POST .../cancelled."""
    return cancel_prep(user_id, _sub(user_id, sub_id), date.today())


@app.post("/api/subscriptions/{sub_id}/cancelled")
def mark_cancelled(user_id: UserId, sub_id: str):
    """The user says they cancelled it. ClawBack then watches the bank for the next charge."""
    _sub(user_id, sub_id)
    store.user(user_id).cancel_pending[sub_id] = date.today()
    store.user(user_id).kept.pop(sub_id, None)
    run(user_id)
    return _sub(user_id, sub_id)


@app.get("/api/subscriptions/{sub_id}/alternatives")
def find_cheaper(user_id: UserId, sub_id: str):
    return alternatives(user_id, _sub(user_id, sub_id), date.today())


@app.post("/api/subscriptions/{sub_id}/negotiate", response_model=ActionPrep)
def negotiate(user_id: UserId, sub_id: str):
    """Talking points and a chat message to ask a bill (or subscription) provider for a lower price."""
    sub = _sub(user_id, sub_id)
    info = store.user(user_id).bill_info.get(sub_id, {})
    return actions.negotiate(user_id, sub, info.get("rule"), info.get("amounts", []), date.today())


# --- One-time money: findings ---------------------------------------------------------------------

def _finding(user_id: str, finding_id: str) -> Finding:
    f = store.user(user_id).findings.get(finding_id)
    if f is None:
        raise HTTPException(404, f"no finding {finding_id!r}")
    return f


@app.get("/api/findings", response_model=list[Finding])
def findings(user_id: UserId):
    """Open first, then by deadline (soonest first, none last), then by amount."""
    return sorted(store.user(user_id).findings.values(), key=sort_key)


@app.post("/api/findings/{finding_id}/prepare", response_model=ActionPrep)
def prepare_finding(user_id: UserId, finding_id: str):
    """The request, letter or script for one finding. ClawBack never sends or files anything."""
    return actions.prepare(_finding(user_id, finding_id), date.today(), user_id)


@app.post("/api/findings/{finding_id}/dismiss", response_model=Finding)
def dismiss_finding(user_id: UserId, finding_id: str):
    f = _finding(user_id, finding_id)
    u = store.user(user_id)
    u.finding_status[f.id] = f.status = "dismissed"
    u.got_back.pop(f.id, None)
    u.done_on.pop(f.id, None)
    return f


class Done(BaseModel):
    got_back: float = Field(0.0, ge=0)


@app.post("/api/findings/{finding_id}/done", response_model=Finding)
def finding_done(user_id: UserId, finding_id: str, body: Done | None = None):
    """Mark it done. `got_back` is what the user says they recovered (self-reported). The next sync looks for the
    matching bank credit and, when it finds one, counts the money as confirmed (pipeline/confirm.py)."""
    f = _finding(user_id, finding_id)
    mark_done(store.user(user_id), f, body.got_back if body else 0.0, date.today())
    return f


@app.get("/api/recovered")
def recovered_history(user_id: UserId):
    """Money recovered: totals (confirmed from bank data, self-reported, cancellations per month) and dated events."""
    return history(user_id)


# --- Data in --------------------------------------------------------------------------------------

@app.post("/api/ingest/statement")
async def upload_statement(user_id: UserId, file: UploadFile = File(...)):
    """A CSV, OFX or QFX statement file (picked by extension or content)."""
    try:
        kind, txs = parse_upload(await file.read(), file.filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Your own statement replaces the made-up demo month (uploaded statements already held stay).
    u = store.use_real_data(user_id)
    # Ids come from FITID (OFX) or the row's content (CSV), so the same file uploaded twice adds nothing new.
    held = {t.id for t in u.transactions}
    txs = [t for t in txs if t.id not in held]
    u.transactions.extend(txs)
    result = await run_in_threadpool(run, user_id)
    return {"added_transactions": len(txs), "format": kind, **result}


# --- Connections ----------------------------------------------------------------------------------

@app.get("/api/connections")
def connections_status(user_id: UserId):
    return connect.status(user_id)


@app.get("/api/connect/email")
def email_start(user_id: UserId, login_hint: str | None = None):
    """Where to send the browser: the Nylas provider picker, then the provider's sign-in. Not configured -> 501."""
    return {"auth_url": nylas.start_url(user_id, login_hint)}


@app.get("/api/connect/email/callback")
async def email_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                         error_description: str | None = None):
    """Nylas redirects here (no session header: the sign-in `state` says whose session it is).

    Always answers with a redirect back to the app (?connected= or ?connect_error=)."""
    user_id = nylas.state_user(state)

    def finish() -> str:
        return connect.finish_email(state, code, error, error_description)

    if user_id is None:  # finish_email turns a bad or expired state into a clean error redirect
        return RedirectResponse(await run_in_threadpool(finish), status_code=302)
    async with user_scope(user_id):
        url = await run_in_threadpool(finish)
    return RedirectResponse(url, status_code=302)


@app.post("/api/connect/plaid/link-token")
def plaid_link_token(user_id: UserId):
    """Token for Plaid Link in the browser. Not configured -> 501."""
    return {"link_token": plaid.create_link_token(user_id)}


class PlaidExchange(BaseModel):
    public_token: str
    institution: str | None = None


@app.post("/api/connect/plaid/exchange")
def plaid_exchange(user_id: UserId, body: PlaidExchange):
    """Link's public_token -> saved connection -> first transactions pull -> pipeline."""
    return connect.connect_plaid(user_id, body.public_token, body.institution)


@app.post("/api/connect/{source}/disconnect")
def source_disconnect(user_id: UserId, source: str):
    if source not in connect.SOURCES:
        raise HTTPException(404, f"unknown source {source!r}")
    return connect.disconnect(user_id, source)


# --- Webhooks (no session: each is verified by its signature, then mapped to a user) ----------------

async def _in_background(user_id: str, work, *args) -> None:
    try:
        async with user_scope(user_id):
            await run_in_threadpool(work, user_id, *args)
    except Exception:  # never let one bad delivery take the worker down
        log.exception("webhook work failed")


@app.get("/api/ingest/email/webhook")
def email_webhook_challenge(challenge: str = ""):
    """Nylas checks the address once: echo `challenge` as plain text."""
    return PlainTextResponse(challenge)


@app.post("/api/ingest/email/webhook")
async def email_webhook(request: Request, background: BackgroundTasks):
    """Nylas notifications. message.created: read that message and re-run in the background.
    grant.expired / grant.deleted: the connection needs a new sign-in. Unsigned or badly signed: 401."""
    raw = await request.body()
    if not nylas.verify_webhook(raw, request.headers.get("x-nylas-signature")):
        raise HTTPException(401, "bad signature")
    try:
        event = nylas.parse_webhook(json.loads(raw))
    except (ValueError, AttributeError):
        raise HTTPException(400, "not a JSON object")
    # Usually one user; the same inbox connected in two sessions shares a grant.
    users = await run_in_threadpool(connections.find_users, "email", event.grant_id or "")
    if not users:
        return {"ok": True, "handled": "unknown grant"}
    if event.type in nylas.MESSAGE_EVENTS:
        for user_id in users:
            background.add_task(_in_background, user_id, connect.on_new_message, event.grant_id, event.message_id)
        return {"ok": True, "handled": "queued"}
    if event.type in nylas.GRANT_LOST_EVENTS:
        for user_id in users:
            await run_in_threadpool(connections.mark_reconnect, user_id, "email", nylas.EXPIRED)
        return {"ok": True, "handled": "needs reconnect"}
    return {"ok": True, "handled": "ignored"}


@app.post("/api/ingest/plaid/webhook")
async def plaid_webhook(request: Request, background: BackgroundTasks):
    """Plaid webhooks, checked with the Plaid-Verification JWT. SYNC_UPDATES_AVAILABLE: pull in the background.
    ITEM ERROR / PENDING_EXPIRATION / ...: the bank needs a new sign-in. Unsigned or badly signed: 401."""
    raw = await request.body()
    try:
        await run_in_threadpool(plaid.verify_webhook, raw, request.headers.get("plaid-verification"))
    except plaid.WebhookInvalid as exc:
        log.info("plaid webhook refused: %s", exc)
        raise HTTPException(401, "bad signature")
    try:
        payload = json.loads(raw)
        kind, code, item_id = (str(payload.get(k) or "") for k in ("webhook_type", "webhook_code", "item_id"))
    except (ValueError, AttributeError):
        raise HTTPException(400, "not a JSON object")
    user_id = await run_in_threadpool(connections.find_user, "plaid", item_id)
    if user_id is None:
        return {"ok": True, "handled": "unknown item"}
    if kind == "TRANSACTIONS" and code == "SYNC_UPDATES_AVAILABLE":
        background.add_task(_in_background, user_id, connect.on_plaid_update, item_id)
        return {"ok": True, "handled": "queued"}
    if kind == "ITEM" and code in plaid.RECONNECT_ITEM_CODES:
        message = "Your bank connection needs you to sign in again. Connect the bank again."
        await run_in_threadpool(connections.mark_reconnect, user_id, "plaid", message)
        return {"ok": True, "handled": "needs reconnect"}
    if kind == "ITEM" and code == "LOGIN_REPAIRED":
        await run_in_threadpool(connections.mark_reconnect, user_id, "plaid", "", False)
        return {"ok": True, "handled": "repaired"}
    return {"ok": True, "handled": "ignored"}


# --- Settings -------------------------------------------------------------------------------------

class StateSetting(BaseModel):
    state: str | None = None  # two-letter US state code, e.g. "CA"; null clears it


@app.get("/api/settings")
def get_settings(user_id: UserId):
    """The user's state (for state auto-renewal rules), its rule if we have one, and every state to pick from."""
    return rights.settings_view(store.user(user_id).state)


@app.post("/api/settings/state")
def set_state(user_id: UserId, body: StateSetting):
    try:
        code = rights.normalize_state(body.state)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    store.user(user_id).state = code
    return rights.settings_view(code)


# --- Drafts in the user's own mailbox (never sent) ------------------------------------------------

class DraftText(BaseModel):
    """The email as the app showed it (the user may have edited it). Leave it out to prepare it again."""
    subject: str | None = None
    body: str | None = None
    to: str | None = None  # one email address, or nothing


@app.post("/api/subscriptions/{sub_id}/email-draft")
def save_email_draft(user_id: UserId, sub_id: str, text: DraftText | None = None):
    """Save the cancellation email as a draft in the connected mailbox. 409 when no email is connected,
    403 when the connection can only read. Never sends."""
    t = text or DraftText()
    return drafts.save_cancel_email(user_id, _sub(user_id, sub_id), date.today(), t.subject, t.body, t.to)


@app.post("/api/findings/{finding_id}/email-draft")
def save_finding_draft(user_id: UserId, finding_id: str, text: DraftText | None = None):
    """Save a finding's prepared letter or request as a draft in the connected mailbox. Never sends."""
    t = text or DraftText()
    prep = prepare_finding(user_id, finding_id) if not (t.subject and t.body) else None
    if prep is None:
        _finding(user_id, finding_id)
        return drafts.save(user_id, t.subject, t.body, t.to)
    return drafts.save_finding_letter(user_id, prep, t.subject, t.body, t.to)
