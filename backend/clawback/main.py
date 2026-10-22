"""ClawBack API (prototype). Run with:  uvicorn clawback.main:app --reload --port 8000"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import demo_data, llm
from .config import settings
from .missing import REGISTRY, Missing, missing
from .pipeline.cancel import cancel_prep
from .pipeline.recommend import alternatives
from .pipeline.run import best_saving, run, summary
from .sources import gmail, plaid
from .sources.statements import parse_csv
from .store import store

# MISSING [auth]: one hard-coded user. Replace with Supabase Auth and a demo login for judges.
USER = "demo"


def seed(today: date | None = None) -> dict:
    today = today or date.today()
    u = store.reset(USER)
    u.transactions = demo_data.transactions(today)
    u.emails = demo_data.emails(today)
    return run(USER, today)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.autoseed_demo:
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
    return store.user(USER).trace


# --- Dashboard ------------------------------------------------------------------------------------

@app.post("/api/demo/seed")
def demo_seed():
    return seed()


@app.post("/api/sync")
def sync():
    """Re-run the pipeline. MISSING [gmail-push]/[plaid-sync]: this should pull new data first."""
    return run(USER)


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


@app.get("/api/connect/gmail")
def connect_gmail():
    return {"url": gmail.oauth_start_url(USER)}  # raises Missing -> 501


@app.post("/api/ingest/gmail/push")
def gmail_push(payload: dict):
    gmail.handle_push(payload)  # raises Missing -> 501


@app.get("/api/connect/plaid")
def connect_plaid():
    return {"link_token": plaid.create_link_token(USER)}  # raises Missing -> 501


@app.post("/api/ingest/plaid/webhook")
def plaid_webhook(payload: dict):
    plaid.handle_webhook(payload)  # raises Missing -> 501


@app.post("/api/subscriptions/{sub_id}/gmail-draft")
def save_gmail_draft(sub_id: str):
    _sub(sub_id)
    missing("gmail-drafts")
