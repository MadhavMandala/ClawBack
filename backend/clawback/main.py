"""ClawBack API (prototype). Run with:  uvicorn clawback.main:app --reload --port 8000"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import connect, demo_data, llm
from .config import settings
from .findings import actions, rulebook
from .findings.detect import sort_key
from .models import ActionPrep, Finding
from .missing import REGISTRY, Missing, missing
from .pipeline.cancel import cancel_prep
from .pipeline.recommend import alternatives
from .pipeline.run import best_saving, run, summary
from .sources import nylas, plaid
from .sources.net import SourceError
from .sources.statements import parse_csv
from .store import store
from .trace import view

# MISSING [auth]: one hard-coded user. Replace with Supabase Auth and a demo login for judges.
USER = "demo"


def seed(today: date | None = None) -> dict:
    """Switch to demo mode and load the fake data. Saved connections stay saved but unused."""
    today = today or date.today()
    u = store.reset(USER)
    u.transactions = demo_data.transactions(today)
    u.emails = demo_data.emails(today)
    book = rulebook.current()
    if book:
        u.emails += demo_data.settlement_story(today, u.transactions, u.emails, book)
    return run(USER, today)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Saved email / bank connections mean real mode: sync them (failures only add trace rows).
    if not connect.restore(USER) and settings.autoseed_demo:
        seed()
    yield


app = FastAPI(title="ClawBack (prototype)", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Missing)
async def missing_handler(request: Request, exc: Missing):
    return JSONResponse(status_code=501, content={"missing": str(exc)})


@app.exception_handler(SourceError)
async def source_error_handler(request: Request, exc: SourceError):
    # Email / Plaid failures: a short message, never a stack trace.
    return JSONResponse(status_code=exc.status, content={"detail": exc.safe_message})


def _sub(sub_id: str):
    sub = store.user(USER).subscriptions.get(sub_id)
    if sub is None:
        raise HTTPException(404, f"no subscription {sub_id!r}")
    return sub


# --- Status ---------------------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "integrations": settings.integrations(), "models": llm.MODELS}


@app.get("/api/missing")
def missing_list():
    return REGISTRY


@app.get("/api/trace")
def trace():
    return view(USER)


# --- Dashboard ------------------------------------------------------------------------------------

@app.post("/api/demo/seed")
def demo_seed():
    return seed()


@app.post("/api/sync")
def sync():
    """Real mode: pull from every connected source, then re-run. Demo mode: just re-run.

    MISSING [email-webhooks]/[plaid-webhook]: new data arrives only when this is called.
    """
    return connect.sync_now(USER)


@app.get("/api/summary")
def get_summary():
    return summary(USER)


@app.get("/api/subscriptions")
def subscriptions():
    subs = list(store.user(USER).subscriptions.values())
    return sorted(subs, key=lambda s: (-best_saving(s), -s.monthly_cost))


class Checkin(BaseModel):
    used: bool


@app.post("/api/subscriptions/{sub_id}/checkin")
def checkin(sub_id: str, body: Checkin):
    _sub(sub_id)
    store.user(USER).checkins[sub_id].append((date.today(), body.used))
    run(USER)
    return _sub(sub_id)


@app.post("/api/subscriptions/{sub_id}/keep")
def keep(sub_id: str):
    _sub(sub_id)
    store.user(USER).kept[sub_id] = date.today()
    store.user(USER).cancel_pending.pop(sub_id, None)
    run(USER)
    return _sub(sub_id)


@app.post("/api/subscriptions/{sub_id}/cancel-prep")
def prepare_cancel(sub_id: str):
    """Gather the cancel link, steps and email. Never cancels or sends anything."""
    prep = cancel_prep(USER, _sub(sub_id), date.today())
    store.user(USER).cancel_pending[sub_id] = date.today()
    store.user(USER).kept.pop(sub_id, None)
    run(USER)
    return prep


@app.get("/api/subscriptions/{sub_id}/alternatives")
def find_cheaper(sub_id: str):
    return alternatives(USER, _sub(sub_id), date.today())


@app.post("/api/subscriptions/{sub_id}/negotiate", response_model=ActionPrep)
def negotiate(sub_id: str):
    """Talking points and a chat message to ask a bill (or subscription) provider for a lower price."""
    sub = _sub(sub_id)
    info = store.user(USER).bill_info.get(sub_id, {})
    return actions.negotiate(USER, sub, info.get("rule"), info.get("amounts", []), date.today())


# --- One-time money: findings ---------------------------------------------------------------------

def _finding(finding_id: str) -> Finding:
    f = store.user(USER).findings.get(finding_id)
    if f is None:
        raise HTTPException(404, f"no finding {finding_id!r}")
    return f


@app.get("/api/findings", response_model=list[Finding])
def findings():
    """Open first, then by deadline (soonest first, none last), then by amount."""
    return sorted(store.user(USER).findings.values(), key=sort_key)


@app.post("/api/findings/{finding_id}/prepare", response_model=ActionPrep)
def prepare_finding(finding_id: str):
    """The request, letter or script for one finding. ClawBack never sends or files anything."""
    return actions.prepare(_finding(finding_id), date.today())


@app.post("/api/findings/{finding_id}/dismiss", response_model=Finding)
def dismiss_finding(finding_id: str):
    f = _finding(finding_id)
    u = store.user(USER)
    u.finding_status[f.id] = f.status = "dismissed"
    u.got_back.pop(f.id, None)
    return f


class Done(BaseModel):
    got_back: float = Field(0.0, ge=0)


@app.post("/api/findings/{finding_id}/done", response_model=Finding)
def finding_done(finding_id: str, body: Done | None = None):
    """Mark it done. `got_back` is what the user says they recovered (self-reported, not checked)."""
    f = _finding(finding_id)
    u = store.user(USER)
    u.finding_status[f.id] = f.status = "done"
    u.got_back[f.id] = round(body.got_back if body else 0.0, 2)
    return f


# --- Data in --------------------------------------------------------------------------------------

@app.post("/api/ingest/statement")
async def upload_statement(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        txs = parse_csv(content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    store.user(USER).transactions.extend(txs)
    result = run(USER)
    return {"added_transactions": len(txs), **result}


# --- Connections ----------------------------------------------------------------------------------

@app.get("/api/connections")
def connections_status():
    return connect.status(USER)


@app.get("/api/connect/email")
def email_start(login_hint: str | None = None):
    """Where to send the browser: the Nylas provider picker, then the provider's sign-in. Not configured -> 501."""
    return {"auth_url": nylas.start_url(USER, login_hint)}


@app.get("/api/connect/email/callback")
def email_callback(code: str | None = None, state: str | None = None, error: str | None = None,
                   error_description: str | None = None):
    """Nylas redirects here. Always answers with a redirect back to the app (?connected= or ?connect_error=)."""
    return RedirectResponse(connect.finish_email(state, code, error, error_description), status_code=302)


@app.post("/api/connect/plaid/link-token")
def plaid_link_token():
    """Token for Plaid Link in the browser. Not configured -> 501."""
    return {"link_token": plaid.create_link_token(USER)}


class PlaidExchange(BaseModel):
    public_token: str
    institution: str | None = None


@app.post("/api/connect/plaid/exchange")
def plaid_exchange(body: PlaidExchange):
    """Link's public_token -> saved connection -> first transactions pull -> pipeline."""
    return connect.connect_plaid(USER, body.public_token, body.institution)


@app.post("/api/connect/{source}/disconnect")
def source_disconnect(source: str):
    if source not in connect.SOURCES:
        raise HTTPException(404, f"unknown source {source!r}")
    return connect.disconnect(USER, source)


@app.post("/api/ingest/email/webhook")
def email_webhook(payload: dict):
    nylas.handle_webhook(payload)  # raises Missing -> 501


@app.post("/api/ingest/plaid/webhook")
def plaid_webhook(payload: dict):
    plaid.handle_webhook(payload)  # raises Missing -> 501


@app.post("/api/subscriptions/{sub_id}/email-draft")
def save_email_draft(sub_id: str):
    _sub(sub_id)
    missing("email-drafts")
