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
        "id": "nylas-production",
        "area": "Data sources",
        "priority": "P1",
        "what": "A paid Nylas plan for real users: the free Sandbox allows 5 connected accounts and isn't meant for production",
        "where": "Nylas Dashboard, privacy policy",
        "note": "Mail passes through Nylas, a third-party processor; docs/PRIVACY.md says so. Gmail in production also needs either your own Google project with Google verification + CASA (restricted scopes) or Nylas's verified shared Google app (paid add-on). Drafts in Gmail may also need the gmail.compose scope on the Google connector.",
    },
    {
        "id": "plaid-production",
        "area": "Data sources",
        "priority": "P2",
        "what": "Plaid Production access for real banks, plus OAuth-bank support (redirect URI in /link/token/create and a return page in the frontend)",
        "where": "Plaid Dashboard, backend/clawback/sources/plaid.py, frontend",
        "note": "Not planned before Oct 30: on 2026-10-23 the team chose to demo on Plaid's test bank (user_good / pass_good). CSV and OFX upload cover real statements. Big banks such as Chase only connect through OAuth.",
    },
    {
        "id": "forwarding-address",
        "area": "Data sources",
        "priority": "P2",
        "what": "A forwarding address for receipts, for inboxes that can't be connected",
        "where": "not started",
        "note": "Needs a domain on Cloudflare with Email Routing and an Email Worker that posts each forwarded message to a new ingest route, which runs the same triage and extraction. Skipped for the hackathon.",
    },
    # --- Pipeline ------------------------------------------------------------------------------
    {
        "id": "email-classifier",
        "area": "Pipeline",
        "priority": "P2",
        "what": "Fine-tuned ModernBERT email filter (labels from Nemotron, int8 ONNX on CPU)",
        "where": "backend/clawback/pipeline/triage.py",
        "note": "Keyword rules plus a Lightning yes or no step stand in for it. It only beats Lightning above about 16,000 emails a day.",
    },
    {
        "id": "usage-apis",
        "area": "Pipeline",
        "priority": "P2",
        "what": "Optional usage connections for services with APIs (e.g. Spotify listening history)",
        "where": "not started",
        "note": "Needs an OAuth app registered with the service (for Spotify: developer.spotify.com, the user-read-recently-played scope and a callback URI). Development mode caps how many people can connect.",
    },
    {
        "id": "browser-extension",
        "area": "Pipeline",
        "priority": "P2",
        "what": "Browser extension that notices which subscribed sites you actually visit",
        "where": "not started",
        "note": "Most accurate usage signal, most privacy cost. Deferred on purpose.",
    },
    # --- Findings: one-time money ---------------------------------------------------------------
    {
        "id": "flight-status-check",
        "area": "Findings",
        "priority": "P2",
        "what": "Check what actually happened to a flight (arrival delay, cancellation cause) with a flight-data API",
        "where": "backend/clawback/findings/refunds.py",
        "note": "Needs a paid flight-data API. We trust the airline's emails. EU261 / UK261 are only checked for departures from the EU / UK, not EU-airline arrivals; arrival delays aren't known.",
    },
    # --- Product / submission --------------------------------------------------------------------
    {
        "id": "notifications",
        "area": "Product",
        "priority": "P2",
        "what": "Alerts by email or push. In-app alerts (GET /api/alerts) are built",
        "where": "backend/clawback/alerts.py",
        "note": "Background runs (webhooks, the nightly job) record new flags and findings, and the dashboard shows them. Nothing is sent outside the app.",
    },
    {
        "id": "deploy",
        "area": "Submission",
        "priority": "P0",
        "what": "Public demo URL (frontend on Vercel, backend on a Nebius VM) that works until Dec 15",
        "where": "docs/DEPLOY.md, deploy/vm, backend/Dockerfile",
        "note": "The runbook, VM setup scripts, systemd units (app and nightly timer) and Caddy config are written; nothing is deployed. After deploy: register the Nylas callback and webhook, set PUBLIC_API_URL for the Plaid webhook, and turn on the nightly timer.",
    },
    {
        "id": "license-public",
        "area": "Submission",
        "priority": "P0",
        "what": "Make the repo public (required to submit). The MIT LICENSE file is added",
        "where": "LICENSE, docs/DEPLOY.md",
        "note": "Private on purpose for now. Before going public: rotate every key, untrack backend/.env and clean the history (docs/DEPLOY.md section 13).",
    },
    {
        "id": "write-up",
        "area": "Submission",
        "priority": "P0",
        "what": "The submission write-up and the tool feedback",
        "where": "docs/WRITEUP.md, docs/token-factory-feedback.md",
        "note": "Drafted. The numbers are [EVAL: ...] placeholders until the eval runs on the merged code and the held-out set, and the demo URL is missing.",
    },
    {
        "id": "demo-video",
        "area": "Submission",
        "priority": "P0",
        "what": "Demo video under 3 minutes",
        "where": "docs/VIDEO.md",
        "note": "A shot-by-shot script (2:45) is written; record it once the hosted demo works.",
    },
    {
        "id": "own-accounts-run",
        "area": "Submission",
        "priority": "P1",
        "what": "Run ClawBack on the team's own email and bank, to report real money found",
        "where": "not started",
        "note": "Zero Data Retention is on. Needs the hosted demo, a connected inbox and a bank (a real bank needs Plaid Production, so this may use statement uploads).",
    },
    {
        "id": "mobile-app",
        "area": "Product",
        "priority": "P2",
        "what": "A native phone app (Expo) on the same API, with push notifications and sign-ins that return to the app",
        "where": "docs/MOBILE.md",
        "note": "Stage 1, installing the web app on a phone, is built. Stages 2 and 3 (native app, app stores) are planned in docs/MOBILE.md.",
    },
]


def as_markdown() -> str:
    rows = ["| Priority | Area | What is missing | Where |", "|---|---|---|---|"]
    for item in sorted(REGISTRY, key=lambda m: (m["priority"], m["area"])):
        rows.append(f"| {item['priority']} | {item['area']} | {item['what']} | `{item['where']}` |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(as_markdown())
