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
        "id": "gmail-oauth",
        "area": "Data sources",
        "priority": "P0",
        "what": "Gmail connection (OAuth consent with gmail.readonly + gmail.compose)",
        "where": "backend/clawback/sources/gmail.py",
        "note": "Restricted scopes: Testing mode only (100 test users, tokens expire every 7 days). Needs a Google Cloud project.",
    },
    {
        "id": "gmail-push",
        "area": "Data sources",
        "priority": "P1",
        "what": "Gmail push notifications (users.watch -> Pub/Sub -> history.list), daily watch renewal, polling fallback",
        "where": "backend/clawback/sources/gmail.py, POST /api/ingest/gmail/push",
        "note": "Demo can run on a manual 'sync now' button until this exists.",
    },
    {
        "id": "gmail-drafts",
        "area": "Actions",
        "priority": "P0",
        "what": "Write cancellation emails as Gmail drafts (drafts.create). The user always presses send.",
        "where": "backend/clawback/sources/gmail.py",
        "note": "Until then the draft text is only shown in the app.",
    },
    {
        "id": "plaid-link",
        "area": "Data sources",
        "priority": "P0",
        "what": "Bank connection with Plaid Link (Sandbox first, then Trial for up to 10 real banks)",
        "where": "backend/clawback/sources/plaid.py, frontend",
        "note": "The recurring-transactions add-on is paid, so recurring detection is our own code (pipeline/recurring.py).",
    },
    {
        "id": "plaid-sync",
        "area": "Data sources",
        "priority": "P1",
        "what": "Transaction sync (/transactions/sync cursor loop + SYNC_UPDATES_AVAILABLE webhook)",
        "where": "backend/clawback/sources/plaid.py, POST /api/ingest/plaid/webhook",
        "note": "",
    },
    {
        "id": "outlook",
        "area": "Data sources",
        "priority": "P2",
        "what": "Outlook / Microsoft 365 via Microsoft Graph (Mail.Read + Mail.ReadWrite drafts)",
        "where": "not started",
        "note": "Mail.ReadWrite cannot send, so 'draft only' is enforced by the permission itself.",
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
        "what": "Encrypted storage of Google refresh tokens and Plaid access tokens",
        "where": "not started",
        "note": "",
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
        "what": "Confirm a cancellation worked (charge missing on the next statement / cancellation email) and add it to 'recovered'",
        "where": "backend/clawback/pipeline/run.py",
        "note": "The 'recovered' total is always $0 until this exists.",
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
        "what": "Prompt-injection guard on email content before it reaches a model (required by Google's Workspace data policy)",
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
