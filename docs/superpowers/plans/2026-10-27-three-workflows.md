# Three Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three workflows that go all the way: an unused Orangetheory membership proven from Google Maps visits and cancelled by a sent email; Hulu's cancel page; a Best Buy price drop with today's live price. The dashboard shows only these, on 3D cards.

**Architecture:** Backend adds gym data (`rules/gyms.json`), a Timeline parser that keeps only gym visits, a visit-based usage rule, a Nylas send path with a send-only connection that keeps the demo, and a live price check in the demo for Best Buy. `/api/showcase` names the three workflows. Frontend adds Tailwind utilities (no preflight) and the Aceternity 3D card for three cards above the existing pane.

**Tech Stack:** FastAPI + pytest; Next.js 16 / React 19; Tailwind v4 (`tailwindcss`, `@tailwindcss/postcss`, `clsx`, `tailwind-merge`).

**Spec:** `docs/superpowers/specs/2026-10-27-three-workflows-design.md`

## Global Constraints

- Never email a real business from the demo: in demo mode, or when the recipient isn't a `gyms.json` studio address, the email goes to the user's own connected address with "[ClawBack test] " prefixed to the subject. The server decides the recipient, never the client.
- Nothing is sent without the user's click on Send and a confirm step.
- Keep only gym visits from a Timeline file; never store the file or other places.
- Dates, visit counts and prices are computed in code, never by a model.
- DESIGN.md rules stay: yellow only for money back; no emoji; the 3D card's hover shadow is the one noted exception.
- Tailwind is added without preflight (utilities only), so existing CSS is unchanged.
- Backend tests stay offline: `cd backend && .venv/bin/python -m pytest -q`.

## Review Focus

1. A Timeline file in the other shape (bare array), with degree strings and missing fields: parses or skips, never crashes → test in Task 1.
2. Send with no connected inbox, an expired grant, or a grant without the send permission: a clear message, nothing sent, status unchanged → tests in Task 2.
3. A client that posts a different `to` address: ignored; the server picks the recipient → test in Task 2.
4. The live price fails, or isn't below what was paid: "simulated" in the title, or the "No drop today" state; never a vanished card → tests in Task 3.
5. Connecting email from the Connect menu still leaves demo mode as before; only the Send path keeps the demo → test in Task 2.

---

### Task 1: Gym data, Timeline parsing, visit rule

**Files:** Create `backend/clawback/rules/gyms.json`, `backend/clawback/sources/timeline.py`, `backend/clawback/gyms.py`; modify `backend/clawback/store.py` (UserData `gym_visits: dict[str, list[date]]`), `backend/clawback/pipeline/usage.py`, `backend/clawback/pipeline/run.py`, `backend/clawback/demo_data.py`, `backend/clawback/main.py` (`POST /api/ingest/timeline`), `backend/clawback/merchants*` (Orangetheory pattern if needed). Test `backend/tests/test_gym.py`; extend `tests/test_demo_every_day.py`.

**Interfaces:**
- `gyms.json`: `{"checked_on", "gyms": [{"id", "chain", "studio", "address", "lat", "lng", "cancel": {"method": "email", "notice_days": 30, "email": str, "how": str, "source_url": str}, "demo": bool}]}`. One demo studio (`"demo": true`, email = a team test address placeholder `cancel-demo@clawback.test`, Edison NJ coordinates).
- `timeline.parse(raw: bytes) -> list[Visit]`, `Visit(lat: float, lng: float, start: date)`; both shapes; `"40.5°, -74.4°"` strings and `geo:` forms; bad segments skipped.
- `gyms.visits_near(visits, gym, meters=150) -> list[date]` (haversine).
- `gyms.for_subscription(sub) -> dict | None` (by chain name in merchant).
- Usage: when `u.gym_visits[sub.id]` exists, visits are signals; no visit in 30 days and <2 in 60 → summary level "none", evidence first line `"{last}: no visits to {studio} since {Mon D} (Google Maps)"`.
- Demo: `ORANGETHEORY FITNESS` $169.00 monthly (6 months, the 4th); `gym_visits` preloaded: 2–3 visits a week until 56 days ago, none after.
- `POST /api/ingest/timeline` (file) → leaves demo mode (`store.use_real_data`), stores only matched visit dates per gym subscription, returns `{"visits": n, "gyms": [...]}`.

- [ ] Tests first: both shapes and degree strings parse; far points dropped; visits_near radius; the unused rule (none in 30 days → none; 2 in last 60 → not flagged); demo flag text contains "no visits to Orangetheory" and "$169.00"; upload stores only dates; every-day test: Orangetheory has `unused`.
- [ ] Run (fail), implement, run full suite, commit "Gym workflow: Orangetheory, Timeline visits and the unused rule".

### Task 2: Gym email and Send

**Files:** modify `backend/clawback/sources/nylas.py` (`send_message`, purpose on sign-in state), `backend/clawback/connections.py` (`EmailConnection.send_only: bool = False`), `backend/clawback/connect.py` (send-only finish; `restore` ignores send-only), `backend/clawback/pipeline/cancel.py` (gym branch), `backend/clawback/main.py` (`GET /api/connect/email?purpose=send`, `POST /api/subscriptions/{id}/send-email`). Test `backend/tests/test_send.py`.

**Interfaces:**
- `nylas.start_url(user_id, login_hint=None, purpose="connect")`; `nylas.check_state(state) -> str` unchanged; new `nylas.state_purpose(state) -> str` read before `check_state` pops it.
- `nylas.send_message(user_id, conn, to, subject, body) -> str` (message id); `POST /v3/grants/{grant}/messages/send`; permission errors → `SendNotAllowed` ("Reconnect email to allow sending.").
- `finish_email` with purpose "send": saves `send_only=True`, keeps demo mode, no sync, redirects `?connected=email-send`.
- `cancel_prep` for a gym: `primary_link` = studio info page if any; `email` written by Ultra (or template) **to** the studio address; new `send: {"to_shown": str, "goes_to": str, "test": bool, "from": str | None, "connected": bool}`; `how_to` says "Orangetheory asks for 30 days' written notice. Email to your studio counts as written notice."
- `POST /api/subscriptions/{id}/send-email {subject, body}` → server picks recipient (demo or non-`gyms.json` → user's own address, subject prefixed "[ClawBack test] "); sends; marks `cancel_pending`; returns `{"sent_to", "test", "message_id"}`; 409 with a message when no inbox; 403 "Reconnect email to allow sending." on scope errors.

- [ ] Tests first (fake Nylas): demo send goes to self with the prefix; posted `to` ignored; no connection → 409, nothing sent; scope error → 403, status unchanged; success → cancel_pending; send-only sign-in keeps demo mode and demo data; Connect-menu sign-in still leaves demo mode; restore() ignores send-only.
- [ ] Run, implement, full suite, commit "Gym email: written by Ultra, sent after a click, demo sends to yourself".

### Task 3: Best Buy live price drop

**Files:** modify `backend/clawback/demo_data.py` (Best Buy AirPods Pro 2 at $249.00 six days ago with its order email; remove the Target purchase and email; move the duplicate charge from Best Buy to `STAPLES 00123` with a Staples order email; PRICE_CHECKS gets `("best buy", "airpods pro 2"): 189.99` as the labelled fallback), `backend/clawback/findings/detect.py` (demo: live when available, else simulated), `backend/clawback/findings/refunds.py` (title says "simulated" when simulated; keep a `price_watch` entry when no drop), `backend/clawback/store.py` (`price_watch: list[dict]`), `backend/clawback/tools/prices.py` (`_CONDITION` adds `open-?box` and `marketplace`). Tests `backend/tests/test_price_workflow.py`; every-day test keeps passing.

**Interfaces:**
- Finding details for price drops: `{"paid", "paid_on", "bank_line", "price_now", "price_url", "checked_on", "how": "live"|"simulated"}`.
- `u.price_watch`: `[{"store", "item", "paid", "price_now", "url", "checked_on", "how"}]` for checked items with no drop.

- [ ] Tests first: demo with live off → simulated, title contains "simulated"; with a fake live check below paid → live finding with url; live not below → no finding and a price_watch entry; openbox and marketplace URLs rejected; demo has one Best Buy charge.
- [ ] Run, implement, full suite, commit "Price drop: Best Buy purchase vs today's live price".

### Task 4: Showcase API and the dashboard cards

**Files:** modify `backend/clawback/main.py` (`GET /api/showcase`); frontend: `package.json` (tailwindcss, @tailwindcss/postcss, clsx, tailwind-merge), create `postcss.config.mjs`, `app/lib/utils.ts` (`cn`), `app/components/ui/3d-card.tsx` (Aceternity source as given), `app/components/Showcase.tsx`; modify `app/globals.css` (`@import "tailwindcss/theme" layer(theme); @import "tailwindcss/utilities" layer(utilities);` — no preflight), `app/api.ts`, `app/dashboard/page.tsx` (cards replace the middle groups; "Everything else" keeps other subscriptions; findings other than the showcase one hidden), `app/components/SubscriptionRow.tsx` (CancelPanel: send UI + confirm + connect-to-send), `app/components/FindingRow.tsx` (paid vs now block, no-drop state), Connect menu "Upload Google Maps Timeline".

**Interfaces:** `GET /api/showcase` → `{"gym": {"sub_id", ...} | null, "streaming": {"sub_id"} | null, "price": {"finding_id"} | {"watch": {...}} | null}`.

- [ ] Build passes; browser check: three cards tilt on hover; each opens its workflow in the pane; Send shows confirm and, with no inbox, "Connect email to send"; price card shows paid vs live price with link; phone width stacks.
- [ ] Commit "Dashboard: three workflow cards".

### Task 5: Docs, live checks, review

- [ ] Update `docs/DESIGN.md` (cards, the hover-shadow exception), `docs/PRIVACY.md` (Timeline: only gym visit dates kept; sending only on click), README/WRITEUP/STATUS lines that say "never sends" → "sends only when you click Send", `docs/VIDEO.md` (three workflows).
- [ ] Live: one live Best Buy check through the demo; one send to the connected inbox if a send-scoped grant exists (otherwise note it for the user).
- [ ] Final whole-branch review, fix pass, push, PR.
