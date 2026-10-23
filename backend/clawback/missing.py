"""Single list of everything the prototype does not do yet.

The API serves this at GET /api/missing so the dashboard can show it, and STATUS.md is generated from it:

    python -m clawback.missing > ../STATUS_TABLE.md

Priority: P0 = needed for the hackathon demo, P1 = needed for a convincing submission, P2 = roadmap.
"""

from __future__ import annotations

from typing import NoReturn


class Missing(NotImplementedError):
    """Raised when code reaches a piece that isn't built yet."""


def missing(item_id: str, detail: str = "") -> NoReturn:
    item = next((m for m in REGISTRY if m["id"] == item_id), None)
    what = item["what"] if item else item_id
    raise Missing(f"MISSING [{item_id}]: {what}" + (f" ({detail})" if detail else ""))


REGISTRY: list[dict[str, str]] = [
    # --- Data sources -------------------------------------------------------------------------
    {
        "id": "email-webhooks",
        "area": "Data sources",
        "priority": "P1",
        "what": "Nylas message.created webhooks, so new mail arrives without pressing Sync",
        "where": "backend/clawback/sources/nylas.py, POST /api/ingest/email/webhook",
        "note": "Needs a public URL and Nylas webhook signature checks. Until then, Sync re-reads the newest 150 subscription-like messages from 180 days.",
    },
    {
        "id": "email-drafts",
        "area": "Actions",
        "priority": "P0",
        "what": "Save cancellation emails as drafts in the user's mailbox (Nylas drafts API). The user always presses send.",
        "where": "backend/clawback/sources/nylas.py, POST /api/subscriptions/{id}/email-draft",
        "note": "Needs the connectors' compose / draft scopes. Until then the draft text is only shown in the app.",
    },
    {
        "id": "nylas-production",
        "area": "Data sources",
        "priority": "P1",
        "what": "A paid Nylas plan for real users: the free Sandbox allows 5 connected accounts and isn't meant for production",
        "where": "Nylas Dashboard, privacy policy",
        "note": "Mail passes through Nylas, a third-party processor, so the privacy policy must say so. Gmail in production also needs either your own Google project with Google verification + CASA (restricted scopes) or Nylas's verified shared Google app (paid add-on).",
    },
    {
        "id": "plaid-webhook",
        "area": "Data sources",
        "priority": "P1",
        "what": "Plaid SYNC_UPDATES_AVAILABLE webhook, so new transactions arrive without pressing Sync",
        "where": "backend/clawback/sources/plaid.py, POST /api/ingest/plaid/webhook",
        "note": "Link + /transactions/sync are built. The webhook also needs a public URL and Plaid's webhook signature check.",
    },
    {
        "id": "plaid-production",
        "area": "Data sources",
        "priority": "P0",
        "what": "Plaid Production access for real banks, plus OAuth-bank support (redirect URI in /link/token/create and a return page in the frontend)",
        "where": "Plaid Dashboard, backend/clawback/sources/plaid.py, frontend",
        "note": "Sandbox works with test logins (user_good / pass_good). Big banks such as Chase and Capital One only connect through OAuth.",
    },
    # --- Storage --------------------------------------------------------------------------------
    {
        "id": "database",
        "area": "Storage",
        "priority": "P0",
        "what": "Real database (Supabase Postgres) with per-user row-level security; currently an in-memory dict that resets on restart",
        "where": "backend/clawback/store.py",
        "note": "Store extracted facts only, never raw email bodies.",
    },
    {
        "id": "auth",
        "area": "Storage",
        "priority": "P0",
        "what": "User accounts / login (Supabase Auth). Everything is one hard-coded 'demo' user right now",
        "where": "backend/clawback/main.py",
        "note": "Judges need a demo login that does not require connecting their own Gmail or bank.",
    },
    {
        "id": "token-encryption",
        "area": "Storage",
        "priority": "P1",
        "what": "Encrypted storage of Plaid access tokens and Nylas grant ids (today they sit in plaintext in backend/.local/connections.json)",
        "where": "backend/clawback/connections.py",
        "note": "Saved in plaintext in backend/.local/connections.json (git-ignored, this machine only). A grant id only works with NYLAS_API_KEY, which stays in backend/.env. Encrypt them, or move them into the database, before any shared deploy.",
    },
    # --- Pipeline ------------------------------------------------------------------------------
    {
        "id": "email-classifier",
        "area": "Pipeline",
        "priority": "P2",
        "what": "Fine-tuned ModernBERT email filter (labels from Nemotron, int8 ONNX on CPU)",
        "where": "backend/clawback/pipeline/triage.py",
        "note": "Keyword rules stand in for it. At a few users, Nemotron 3.5 Lightning on every email is cheaper than hosting it.",
    },
    {
        "id": "pdf-receipts",
        "area": "Pipeline",
        "priority": "P2",
        "what": "Receipts sent as PDFs or images (render pages to PNG -> Nemotron 3.5 Super-VL)",
        "where": "backend/clawback/pipeline/extract.py",
        "note": "Nemotron 3 Nano Omni was removed from Token Factory on 2026-08-31.",
    },
    {
        "id": "app-store-resolution",
        "area": "Pipeline",
        "priority": "P1",
        "what": "Work out which app an 'APPLE.COM/BILL' or 'GOOGLE *' charge is, by matching Apple / Google Play receipt emails",
        "where": "backend/clawback/pipeline/recurring.py",
        "note": "Bank data alone shows only 'Apple'.",
    },
    {
        "id": "usage-learning",
        "area": "Pipeline",
        "priority": "P1",
        "what": "Learn usage patterns over time (adjust check-in frequency, trust per signal type, per-user thresholds)",
        "where": "backend/clawback/pipeline/usage.py",
        "note": "Today it just remembers check-in answers and 'keep' decisions.",
    },
    {
        "id": "usage-apis",
        "area": "Pipeline",
        "priority": "P2",
        "what": "Optional usage connections for services with APIs (e.g. Spotify listening history)",
        "where": "not started",
        "note": "",
    },
    {
        "id": "browser-extension",
        "area": "Pipeline",
        "priority": "P2",
        "what": "Browser extension that notices which subscribed sites you actually visit",
        "where": "not started",
        "note": "Most accurate usage signal, most privacy cost. Deferred.",
    },
    # --- Agent actions -----------------------------------------------------------------------------
    {
        "id": "alternatives",
        "area": "Actions",
        "priority": "P0",
        "what": "'Find something cheaper': Tavily pulls current plans and prices, Nemotron Ultra matches them to your usage",
        "where": "backend/clawback/pipeline/recommend.py",
        "note": "Live: Tavily → Nemotron 3 Super (reads plans) → Nemotron 3 Ultra (fits usage). Without keys it returns code hints.",
    },
    {
        "id": "cancel-lookup",
        "area": "Actions",
        "priority": "P0",
        "what": "Find the merchant's real cancel page / support email with Tavily and cite it",
        "where": "backend/clawback/pipeline/cancel.py",
        "note": "Only the Apple and Google Play subscription pages are known so far.",
    },
    {
        "id": "cancel-confirmation",
        "area": "Actions",
        "priority": "P1",
        "what": "Confirm money actually came back: a cancelled charge missing from the next statement, a refund or reversal credit, a settlement payment",
        "where": "backend/clawback/pipeline/run.py, POST /api/findings/{id}/done",
        "note": "Today 'recovered' is self-reported: the amount the user types when marking a finding done. Nothing checks it against the bank.",
    },
    # --- Findings: one-time money ---------------------------------------------------------------
    {
        "id": "live-price-check",
        "area": "Findings",
        "priority": "P1",
        "what": "Live current-price checks for price drops (Tavily search + extract, Nemotron reads the price)",
        "where": "backend/clawback/tools/prices.py",
        "note": "Needs TAVILY_API_KEY and NEBIUS_API_KEY; untested live. Demo mode uses simulated prices (demo_data.PRICE_CHECKS); real mode without keys checks nothing.",
    },
    {
        "id": "purchase-extraction",
        "area": "Findings",
        "priority": "P1",
        "what": "Read purchases and flight details from real receipt and airline emails with Nemotron",
        "where": "backend/clawback/findings/purchases.py, findings/refunds.py",
        "note": "Without NEBIUS_API_KEY only regex rules run, and they only read simple receipts like the demo ones.",
    },
    {
        "id": "statement-dates",
        "area": "Findings",
        "priority": "P1",
        "what": "Real card statement dates for dispute deadlines (Plaid Statements or Liabilities)",
        "where": "backend/clawback/findings/charges.py",
        "note": "Deadlines assume the statement closed at the end of the charge's month, plus 60 days, and say 'estimated'. Credit vs debit card isn't known either.",
    },
    {
        "id": "settlements-refresh",
        "area": "Findings",
        "priority": "P1",
        "what": "Keep the class-action settlement list current (new settlements, passed deadlines)",
        "where": "backend/clawback/rules/settlements.json",
        "note": "A curated list checked on 2026-10-22, with no live feed. The other rules files also need re-checking every ~3 months; nothing warns when a row goes stale.",
    },
    {
        "id": "flight-status-check",
        "area": "Findings",
        "priority": "P2",
        "what": "Check what actually happened to a flight (arrival delay, cancellation cause) with a flight-data API",
        "where": "backend/clawback/findings/refunds.py",
        "note": "We trust the airline's emails. EU261 / UK261 are only checked for departures from the EU / UK, not EU-airline arrivals; arrival delays aren't known.",
    },
    {
        "id": "bill-market-rates",
        "area": "Findings",
        "priority": "P1",
        "what": "Current competitor offers for bill negotiation scripts",
        "where": "backend/clawback/findings/actions.py",
        "note": "Needs TAVILY_API_KEY (untested live). Without it the script uses only the user's own price history.",
    },
    {
        "id": "legal-rules",
        "area": "Actions",
        "priority": "P2",
        "what": "State auto-renewal rules in the claim text (e.g. NY pro-rata refund after an unconsented price increase)",
        "where": "not started",
        "note": "Research notes exist locally; needs the user's state.",
    },
    {
        "id": "prompt-injection",
        "area": "Safety",
        "priority": "P1",
        "what": "Prompt-injection guard on email content before it reaches a model (required by Google's Workspace data policy for Gmail data)",
        "where": "backend/clawback/pipeline/extract.py",
        "note": "",
    },
    # --- Product / submission --------------------------------------------------------------------
    {
        "id": "notifications",
        "area": "Product",
        "priority": "P2",
        "what": "Notify the user when something is flagged (email digest or push)",
        "where": "not started",
        "note": "",
    },
    {
        "id": "eval-set",
        "area": "Submission",
        "priority": "P1",
        "what": "Labelled test set + metrics (subscriptions found, false flags, cost per 1,000 emails)",
        "where": "not started",
        "note": "Judges read measured results and documented failure cases as rigour.",
    },
    {
        "id": "deploy",
        "area": "Submission",
        "priority": "P0",
        "what": "Public demo URL (frontend on Vercel, backend somewhere reachable) that works until Dec 15",
        "where": "not started",
        "note": "",
    },
    {
        "id": "license-public",
        "area": "Submission",
        "priority": "P0",
        "what": "Open-source LICENSE file and making the repo public (both required to submit)",
        "where": "repo root",
        "note": "Repo is private on purpose for now.",
    },
    {
        "id": "zdr",
        "area": "Safety",
        "priority": "P0",
        "what": "Turn on Zero Data Retention in Token Factory before any real user email is processed",
        "where": "Token Factory profile settings",
        "note": "Otherwise prompts are retained and logged.",
    },
]


def as_markdown() -> str:
    rows = ["| Priority | Area | What is missing | Where |", "|---|---|---|---|"]
    for item in sorted(REGISTRY, key=lambda m: (m["priority"], m["area"])):
        rows.append(f"| {item['priority']} | {item['area']} | {item['what']} | `{item['where']}` |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(as_markdown())
