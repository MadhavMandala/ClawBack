# Status: what works and what is MISSING

**This is a rough prototype.** It looks for money in a person's bank and email data in five areas:
subscriptions, bills, bank charge problems (duplicate charges, fees), refunds owed (store price drops, flight
refunds) and class-action settlements. It runs end to end on **made-up demo data for one fake user** by default.
With Nylas and Plaid keys in `backend/.env`, it can also read the user's own email from any provider (read-only,
through Nylas) and their bank transactions (Plaid). The first real connection replaces the demo data. Those two
connections are covered by mocked tests only: nobody has run them against the live Nylas or Plaid APIs yet.
With a Token Factory key set, the Nemotron model tiers make live calls; all five tiers were checked live on
2026-10-22 (`python -m clawback.llm --check`). The findings' own model calls (purchases, flight details, price
checks) haven't been run live yet.

The dashboard's build-status board lists every planned feature and its phase (planned, started, built, live-tested),
from `backend/clawback/features.py` (served at `GET /api/features`).

Every gap is marked with the word `MISSING`:
- in the code (`grep -rn MISSING backend frontend/app`),
- in the API (unbuilt routes answer HTTP 501 with a `MISSING [...]` message instead of pretending to work),
- on the dashboard (the yellow "Prototype" banner lists everything below).

The list below is generated from `backend/clawback/missing.py`, the single source of truth:
`cd backend && .venv/bin/python -m clawback.missing`.

## Works today

| Piece | What it does | Where |
|---|---|---|
| Recurring-charge detection | Finds weekly/monthly/annual charges with a steady amount (or one price change). Ignores groceries, gas, food orders | `backend/clawback/pipeline/recurring.py` |
| Bills | Internet, mobile, insurance, utility and gym charges matched to `rules/bills.json` come out as bills. Flags: price stepped up 10%+ (`bill_increase`), a "promotional rate ends" email (`promo_ending`), "you could ask for less" (`negotiable`). Utility swings aren't flagged | `findings/bills.py` |
| Bill negotiation script | `POST /api/subscriptions/{id}/negotiate`: talking points (price now and before, customer since), a chat message, the provider's account and retention pages. Competitor offers need Tavily | `findings/actions.py` |
| Duplicate charges | Same merchant and amount within 3 days, not a recurring charge. High confidence when one email receipt shows one order. Dispute letter citing the Fair Credit Billing Act / Regulation E, with an estimated deadline | `findings/charges.py` |
| Bank fees | Overdraft, NSF, ATM, foreign transaction, maintenance, late, returned payment and wire fees, matched with `rules/bank_fees.json`. A polite one-time courtesy-reversal request | `findings/charges.py` |
| Price drops | Purchases read from receipt emails; for stores that price-adjust (`rules/retailers.json`), a drop of $5+ inside the window. Demo uses simulated prices; live checks need Tavily + Nebius. Walmart and Amazon are never flagged | `findings/refunds.py`, `tools/prices.py` |
| Flight refunds | Airline cancellation / schedule-change emails. US DOT cash refund (cancellation, or a 3h domestic / 6h international change, unless accepted). EU261 / UK261 compensation by great-circle distance band | `findings/refunds.py`, `findings/airports.py` |
| Class-action settlements | Open, verified settlements in `rules/settlements.json` that match the user's charges or emails. Links to the official claim site only; never files | `findings/settlements.py` |
| Findings API | `GET /api/findings`, `POST /api/findings/{id}/prepare|dismiss|done`. Stable ids, so dismiss / done survive re-runs. `done` adds a self-reported amount to "recovered" | `main.py`, `findings/detect.py` |
| Price-increase detection | Spots "was $15.49, now $17.99" from the charges themselves | same |
| Usage signals | Counts per-use receipts, "we miss you" emails, usage-summary emails and your Yes/No check-ins | `pipeline/usage.py` |
| Membership value math | "DashPass cost $9.99, saved you $2.99 on 1 order: net -$7.00" | `pipeline/value.py` |
| Flags | unused, membership losing money, two plans doing the same job, trial about to convert, price went up | `pipeline/flags.py` |
| Free-trial detection from email | Finds trials before the first charge, with the end date computed in code | `pipeline/run.py` |
| Apple-billed charges | Names an `APPLE.COM/BILL` charge by matching an Apple receipt email with the same amount (demo only) | `pipeline/recurring.py` |
| Cancel prep | Link + steps + cancellation email written by Nemotron 3 Ultra (template fallback). Never cancels or sends anything | `pipeline/cancel.py` |
| Email extraction | Nemotron 3.5 Lightning reads each email once (cached) into facts with a strict JSON schema; Nano and regexes as fallbacks | `pipeline/extract.py` |
| "Find cheaper" | Tavily finds current plans, Nemotron 3 Super lists them, Nemotron 3 Ultra fits them to your usage; every option cites a Tavily page. Code hints without keys | `pipeline/recommend.py` |
| Statement CSV upload | Real transactions without any bank approval, in demo or real mode | `sources/statements.py` |
| Email connection, any provider (read-only) | One "Connect email" button: Nylas Hosted OAuth with its provider picker (Gmail, Outlook / Microsoft 365, Yahoo, iCloud, IMAP), CSRF `state` check, a clear "reconnect" error when the grant expires. Sync reads the last 180 days of subscription-like mail (up to 150 messages): native search on Gmail and Outlook, keyword rules elsewhere. Untested live | `sources/nylas.py` |
| Bank connection (Plaid) | Link token, public-token exchange, `/transactions/sync` cursor loop with a wait for brand-new Items, added / modified / removed changes, Sandbox or Production. Untested live | `sources/plaid.py` |
| Demo vs real mode | First real connection drops the demo data so the two never mix; `POST /api/demo/seed` switches back. `GET /api/connections` shows the mode and each connection | `connect.py`, `store.py` |
| Saved connections | Tokens, sync cursor, account and timestamps survive a restart; on startup ClawBack re-syncs them. Plaintext, local only | `connections.py` → `backend/.local/connections.json` |
| Disconnect | Forgets the connection, deletes the Nylas grant / removes the Plaid Item (best effort), drops that source's data from memory | `connect.py` |
| Model trace | Every step, including each Nylas / Plaid call, logs its tier, engine, time, tokens (incl. thinking) and cost. Sync rows and click-time rows survive re-runs. Shown on the dashboard | `trace.py` |
| Token Factory client | Five model tiers, verified live; strict JSON, fallbacks, retries, timeouts; `python -m clawback.llm --check` | `llm.py` |
| Front page | Explains ClawBack through one demo month of statement lines with margin notes; the demo's numbers and the build status come live from the backend | `frontend/app/page.tsx` |
| Dashboard | Monthly total and what you could get back, money owed to you, subscriptions and bills in groups, check-ins, cancel / cheaper / negotiate panels, connect buttons, the build status of every feature, and the trace | `frontend/app/dashboard/page.tsx` |
| Tests | 199 offline backend tests (no network; a fake model client): the demo data, every findings detector (with the negative cases), the findings API, email (Nylas) and Plaid against fake APIs, model tiers and fallbacks, extraction, "find cheaper" and the cancel email. `tests/test_rules.py` checks the rules data. Plus an opt-in live extraction test (`CLAWBACK_LIVE=1`) | `backend/tests/` |

## MISSING

P0 = needed for the hackathon demo. P1 = needed for a convincing submission. P2 = roadmap.

| Priority | Area | What is missing | Where |
|---|---|---|---|
| Priority | Area | What is missing | Where |
| P0 | Actions | Save cancellation emails as drafts in the user's mailbox (Nylas drafts API). The user always presses send. | `backend/clawback/sources/nylas.py, POST /api/subscriptions/{id}/email-draft` |
| P0 | Actions | 'Find something cheaper': Tavily pulls current plans and prices, Nemotron Ultra matches them to your usage | `backend/clawback/pipeline/recommend.py` |
| P0 | Actions | Find the merchant's real cancel page / support email with Tavily and cite it | `backend/clawback/pipeline/cancel.py` |
| P0 | Data sources | Plaid Production access for real banks, plus OAuth-bank support (redirect URI in /link/token/create and a return page in the frontend) | `Plaid Dashboard, backend/clawback/sources/plaid.py, frontend` |
| P0 | Safety | Turn on Zero Data Retention in Token Factory before any real user email is processed | `Token Factory profile settings` |
| P0 | Storage | Real database (Supabase Postgres) with per-user row-level security; currently an in-memory dict that resets on restart | `backend/clawback/store.py` |
| P0 | Storage | User accounts / login (Supabase Auth). Everything is one hard-coded 'demo' user right now | `backend/clawback/main.py` |
| P0 | Submission | Public demo URL (frontend on Vercel, backend somewhere reachable) that works until Dec 15 | `not started` |
| P0 | Submission | Open-source LICENSE file and making the repo public (both required to submit) | `repo root` |
| P1 | Actions | Confirm money actually came back: a cancelled charge missing from the next statement, a refund or reversal credit, a settlement payment | `backend/clawback/pipeline/run.py, POST /api/findings/{id}/done` |
| P1 | Data sources | Nylas message.created webhooks, so new mail arrives without pressing Sync | `backend/clawback/sources/nylas.py, POST /api/ingest/email/webhook` |
| P1 | Data sources | A paid Nylas plan for real users: the free Sandbox allows 5 connected accounts and isn't meant for production | `Nylas Dashboard, privacy policy` |
| P1 | Data sources | Plaid SYNC_UPDATES_AVAILABLE webhook, so new transactions arrive without pressing Sync | `backend/clawback/sources/plaid.py, POST /api/ingest/plaid/webhook` |
| P1 | Findings | Live current-price checks for price drops (Tavily search + extract, Nemotron reads the price) | `backend/clawback/tools/prices.py` |
| P1 | Findings | Read purchases and flight details from real receipt and airline emails with Nemotron | `backend/clawback/findings/purchases.py, findings/refunds.py` |
| P1 | Findings | Real card statement dates for dispute deadlines (Plaid Statements or Liabilities) | `backend/clawback/findings/charges.py` |
| P1 | Findings | Keep the class-action settlement list current (new settlements, passed deadlines) | `backend/clawback/rules/settlements.json` |
| P1 | Findings | Current competitor offers for bill negotiation scripts | `backend/clawback/findings/actions.py` |
| P1 | Pipeline | Work out which app an 'APPLE.COM/BILL' or 'GOOGLE *' charge is, by matching Apple / Google Play receipt emails | `backend/clawback/pipeline/recurring.py` |
| P1 | Pipeline | Learn usage patterns over time (adjust check-in frequency, trust per signal type, per-user thresholds) | `backend/clawback/pipeline/usage.py` |
| P1 | Safety | Prompt-injection guard on email content before it reaches a model (required by Google's Workspace data policy for Gmail data) | `backend/clawback/pipeline/extract.py` |
| P1 | Storage | Encrypted storage of Plaid access tokens and Nylas grant ids (today they sit in plaintext in backend/.local/connections.json) | `backend/clawback/connections.py` |
| P1 | Submission | Labelled test set + metrics (subscriptions found, false flags, cost per 1,000 emails) | `not started` |
| P2 | Actions | State auto-renewal rules in the claim text (e.g. NY pro-rata refund after an unconsented price increase) | `not started` |
| P2 | Findings | Check what actually happened to a flight (arrival delay, cancellation cause) with a flight-data API | `backend/clawback/findings/refunds.py` |
| P2 | Pipeline | Fine-tuned ModernBERT email filter (labels from Nemotron, int8 ONNX on CPU) | `backend/clawback/pipeline/triage.py` |
| P2 | Pipeline | Receipts sent as PDFs or images (render pages to PNG -> Nemotron 3.5 Super-VL) | `backend/clawback/pipeline/extract.py` |
| P2 | Pipeline | Optional usage connections for services with APIs (e.g. Spotify listening history) | `not started` |
| P2 | Pipeline | Browser extension that notices which subscribed sites you actually visit | `not started` |
| P2 | Product | Notify the user when something is flagged (email digest or push) | `not started` |

### Smaller gaps (not in the table)

- The merchant list (`merchants.py`) has 9 hand-written entries. Unknown recurring charges show their raw bank text.
- An annual plan needs two charges before bank data can detect it.
- Membership value math covers delivery memberships only (no Uber One, Instacart+, Prime, Walmart+ yet).
- "Potential savings" still counts subscriptions you have started cancelling.
- Frontend types are hand-copied from the backend models rather than generated.
- Email sync re-reads the newest matching mail each time instead of reacting to webhooks (part of `email-webhooks`).
- One inbox at a time; connecting another replaces it (and deletes the old Nylas grant).
- Outlook's native search (KQL) and its exact quoting through Nylas are unverified; if Nylas refuses the query,
  sync falls back to the keyword scan.
- One bank (Plaid Item) at a time; connecting another replaces it.
- With a Nebius key set, connecting email runs Nemotron on every candidate email before the browser is sent back,
  so the first connect can take a while.
- Settlement matching is by merchant name only, so it can match a settlement about a different product from the
  same company (the demo's iCloud receipt matches an Apple iPhone settlement, as "low" confidence). `owed_total`
  still counts estimated settlement payouts.
- A duplicate charge's dispute rule assumes a credit card (FCBA); Regulation E for debit cards is linked too.
- Purchases and price checks cover the items named in the receipt; quantities, tax and shipping are ignored.
- Finding statuses (dismiss / done) live in memory and reset on restart (MISSING [database]).
- No CI.

## Decisions made for this prototype (change them if they're wrong)

1. **Five areas, one data set (widened 2026-10-22).** Subscriptions, bills, bank charge problems, refunds owed and
   settlements, all from the same bank and email data. Every rule comes from `backend/clawback/rules` (fact-checked
   separately, with source links); only `verified` rows can raise a finding.
2. **Ask before acting.** ClawBack prepares the cancellation, dispute letter, request or script, and the user sends
   it. It never files a settlement claim (those are made under penalty of perjury).
   Automatic cancelling would mean storing everyone's passwords, and a wrong cancellation can hurt.
3. **No browser extension for now.** It's the best usage signal but the biggest privacy cost and extra build.
4. **Rules + Nemotron 3.5 Lightning instead of a fine-tuned classifier**, at least for the demo. At a few users, sending
   the leftover emails to Lightning ($0.06 per 1M input tokens) costs less than keeping a classifier server running.
