# Status: what works and what is MISSING

**This is a hackathon prototype, updated 2026-10-23.** It looks for money in a person's bank and email data in
five areas: subscriptions, bills, bank charge problems (duplicate charges, fees), refunds owed (store price drops,
flight refunds) and class-action settlements. It prepares the email, letter, script or claim, and the person makes
the final click. It never cancels, pays, sends or files anything itself.

- **Sessions:** each browser gets its own private session (no login) with its own copy of the made-up demo month.
  A visitor can connect their own email (any provider, through Nylas) or Plaid's test bank, or upload a CSV or
  OFX statement. The first real connection replaces the demo data.
- **Storage:** data is saved in an encrypted SQLite database, so a restart loses nothing. Real email text is
  never written to disk.
- **Models:** the NVIDIA Nemotron models on Nebius Token Factory make live calls, with Zero Data Retention on.
  - The live tests so far: all five tiers, email extraction, receipt and flight reading, the triage step, the
    injection screen, find cheaper, the Ultra letters and cancel emails, price checks, bill offers, merchant
    naming and the settlements refresh.
  - Nylas and Plaid are tested against fake APIs; no inbox or bank has been connected end to end yet.

The dashboard's build-status board lists every planned feature and its phase (planned, started, built,
live-tested), from `backend/clawback/features.py` (served at `GET /api/features`).

**Demo month:** $503.23 a month for 9 subscriptions and 4 bills, $81.97 a month that could be saved, $615.06 owed
across 7 findings, and one confirmed cancellation (Calm, $16.04 a month, $32.08 so far).

Every remaining gap is marked with the word `MISSING`:
- in the code (`grep -rn MISSING backend frontend/app`);
- in the API: unbuilt routes answer HTTP 501 with a `MISSING [...]` message instead of pretending to work;
- on the dashboard, where panels tag the part that isn't built.

The table below is generated from `backend/clawback/missing.py`, the single source of truth:
`cd backend && .venv/Scripts/python -m clawback.missing`.

## Works today

| Piece | What it does | Where |
|---|---|---|
| Sessions | `POST /api/session` gives each browser its own session and a copy of the demo month, built once a day. A missing or idle session gets 401 "session expired" and the frontend makes a new one. At most 20 new sessions per IP per hour. Idle sessions are deleted after 14 days, with their Nylas grant and Plaid Item | `sessions.py`, `demo.py`, `frontend/app/api.ts` |
| Storage | SQLite (WAL) at `CLAWBACK_DB_PATH`, every row encrypted with `CLAWBACK_SECRET_KEY`. Only demo emails are written; real mail is read again from Nylas after a restart. The nightly job and the API can both write safely (row versions) | `db.py`, `store.py`, `crypto.py` |
| Spend limits | $0.25 of model calls per session per day and $5 overall. Past a limit, calls are skipped (shown in the trace) and the rules and templates take over | `budget.py`, `llm.py` |
| Delete my data | `DELETE /api/me` removes the Nylas grant and Plaid Item and every row for the session. `GET /api/me` shows what is held, never tokens | `sessions.py`, `main.py` |
| Recurring-charge detection | Weekly, monthly, quarterly and yearly charges. A one-off charge doesn't break a series, a renamed descriptor doesn't split it, and a yearly plan with one charge counts when an email confirms it. Rent, loans, copays, transfers and card payments are set aside | `pipeline/recurring.py`, `pipeline/annual.py`, `rules/not_subscriptions.json` |
| Merchant names | 153 US subscriptions and bills in `rules/merchants.json`. Nemotron 3.5 Lightning names the rest from the descriptor alone; low confidence keeps the bank's text | `merchants.py`, `pipeline/naming.py` |
| Apple and Google Play | Names each `APPLE.COM/BILL` and `GOOGLE *` charge from receipt and subscription emails: bundles, tax, several apps in one series. Lightning reads odd layouts | `pipeline/store_billing.py` |
| Usage signals and learning | Receipts, "we miss you" and usage-summary emails, joined to charges even when the names differ a little. Two "no" check-ins make unused certain; three "yes" ask less often; a "no" after Keep raises it again | `pipeline/usage.py` |
| Membership value | Saved-versus-paid math for DashPass, Uber One, Instacart+, Walmart+, Grubhub+ and Prime, from published fees. It says "not enough receipts to tell" rather than guess | `pipeline/value.py`, `rules/memberships.json` |
| Flags | Unused, membership losing money, two plans doing one job (by category), trial about to convert (days left or an end date), price went up, paid twice, charged after cancelling | `pipeline/flags.py` |
| Cancel and refund confirmation | After cancelling starts, no charge by the due date confirms it; a new charge is flagged. A finding marked done waits for a matching bank credit, which confirms it | `pipeline/confirm.py` |
| Money recovered | `GET /api/recovered`: confirmed and self-reported money, and cancellations with their monthly saving | `pipeline/recovered.py` |
| Bills | Internet, mobile, insurance, utility and gym charges matched to `rules/bills.json`. Flags: price up 10%+, a promotional rate ending, "you could ask for less" | `findings/bills.py` |
| Bill negotiation | Nemotron 3 Ultra writes the talking points and chat message from the bill's history. Tavily and Nemotron 3 Super add up to 3 competitor offers, each priced on the page it cites | `findings/actions.py`, `findings/letters.py` |
| Duplicate charges | Same merchant and amount within 3 days, not recurring, and not already refunded. The dispute deadline uses the card's real statement date from Plaid when there is one | `findings/charges.py` |
| Bank fees | Overdraft, NSF, ATM, foreign transaction and other fees, with a one-time courtesy-reversal request | `findings/charges.py` |
| Price drops | Purchases read from receipts (Lightning in strict JSON, or the rules), then a live price check on the store's own site with Tavily and Lightning. The price must appear on the cited page | `findings/refunds.py`, `tools/prices.py` |
| Receipts as PDFs and images | PDF text through pypdf and Lightning; images through Nemotron 3.5 Super-VL. Attachments are capped at 5 MB, type-checked and kept in memory only | `findings/receipts.py` |
| Flight refunds | US DOT cash refunds and EU261 / UK261 compensation from airline emails | `findings/refunds.py`, `findings/airports.py` |
| Settlements | Open, verified settlements matched only when a purchase is in the class period, names the product and fits any state limit. `python -m clawback.findings.settlements_refresh` finds candidates for a person to review | `findings/settlements.py`, `findings/settlements_refresh.py` |
| Letters | Nemotron 3 Ultra writes the dispute, fee, price-adjustment and flight letters. Code rejects any number, date or link not in the facts and falls back to the template; each letter says who wrote it | `findings/letters.py` |
| Cancel prep | Finds the merchant's own cancel page with Tavily (code checks the domain; steps must be quoted from the page). Adds the person's state auto-renewal rule or the federal one. Ultra writes the email | `pipeline/cancel.py`, `pipeline/cancel_lookup.py`, `pipeline/rights.py` |
| Drafts | Saves the cancel email or a letter as a draft in the connected mailbox. Never sends | `drafts.py`, `sources/nylas.py` |
| Find cheaper | Tavily finds plans, Nemotron 3 Super lists them, Nemotron 3 Ultra fits them to usage; every option cites a returned page | `pipeline/recommend.py` |
| Email extraction and triage | Lightning reads each email once (cached) into facts. Code keeps a value only if the email writes it. Unknown senders get a Lightning yes or no | `pipeline/extract.py`, `pipeline/triage.py` |
| Prompt-injection guard | A rule screen (plus a Lightning check for borderline mail) before any model reads email. A flagged email goes to the rules only | `pipeline/guard.py`, `pipeline/grounded.py` |
| Email connection, any provider | Nylas Hosted OAuth with its provider picker, a CSRF `state` check, and a clear reconnect message when access expires. Reads 180 days of subscription mail | `sources/nylas.py` |
| Bank connection (Plaid) | Link, token exchange, the `/transactions/sync` loop, and liabilities for statement dates (optional product). Test bank only, by decision | `sources/plaid.py` |
| Webhooks | Nylas (challenge echo, HMAC signature, one message read per notification) and Plaid (ES256 JWT check, sync on new data) | `sources/nylas.py`, `sources/plaid.py` |
| Nightly job | `python -m clawback.nightly`: checks each email grant, syncs, re-runs the checks and records alerts. Safe to run twice | `nightly.py`, `alerts.py` |
| Statement upload | CSV, OFX and QFX; the same OFX file twice adds nothing | `sources/statements.py` |
| Model trace | Every step logs its tier, engine, time, tokens and cost, and the dashboard shows it | `trace.py` |
| Front page | One demo month of statement lines with margin notes; live numbers from the backend | `frontend/app/page.tsx` |
| Dashboard | Spend sentence and bar; money owed; subscriptions and bills grouped by what to do; cancelled subscriptions; Money back; new-since-last-visit alerts; a first-visit guide; panels with drafts; the build board; the trace | `frontend/app/dashboard/page.tsx` |
| Settings and privacy | `/settings`: session, connections, state, what's stored, today's model use, delete everything. `/privacy`: the prototype policy | `frontend/app/settings`, `frontend/app/privacy` |
| Eval | 109 synthetic emails and 589 transactions for three made-up people, with labels. `python -m evals.run` scores rules-only and live-model runs; see `docs/EVAL.md` | `backend/evals` |
| Tests | 690 offline backend tests and 9 opt-in live tests (`CLAWBACK_LIVE=1`). No network; fake model, Nylas and Plaid clients | `backend/tests/` |

## MISSING

P0 = needed for the hackathon demo. P1 = needed for a convincing submission. P2 = roadmap.

| Priority | Area | What is missing | Where |
|---|---|---|---|
| P0 | Submission | Public demo URL (frontend on Vercel, backend on a Nebius VM) that works until Dec 15 | `docs/DEPLOY.md, deploy/vm, backend/Dockerfile` |
| P0 | Submission | Make the repo public (required to submit). The MIT LICENSE file is added | `LICENSE, docs/DEPLOY.md` |
| P0 | Submission | The submission write-up and the tool feedback | `docs/WRITEUP.md, docs/token-factory-feedback.md` |
| P0 | Submission | Demo video under 3 minutes | `docs/VIDEO.md` |
| P1 | Data sources | A paid Nylas plan for real users: the free Sandbox allows 5 connected accounts and isn't meant for production | `Nylas Dashboard, privacy policy` |
| P1 | Submission | Run ClawBack on the team's own email and bank, to report real money found | `not started` |
| P2 | Data sources | Plaid Production access for real banks, plus OAuth-bank support (redirect URI in /link/token/create and a return page in the frontend) | `Plaid Dashboard, backend/clawback/sources/plaid.py, frontend` |
| P2 | Data sources | A forwarding address for receipts, for inboxes that can't be connected | `not started` |
| P2 | Findings | Check what actually happened to a flight (arrival delay, cancellation cause) with a flight-data API | `backend/clawback/findings/refunds.py` |
| P2 | Pipeline | Fine-tuned ModernBERT email filter (labels from Nemotron, int8 ONNX on CPU) | `backend/clawback/pipeline/triage.py` |
| P2 | Pipeline | Optional usage connections for services with APIs (e.g. Spotify listening history) | `not started` |
| P2 | Pipeline | Browser extension that notices which subscribed sites you actually visit | `not started` |
| P2 | Product | Alerts by email or push. In-app alerts (GET /api/alerts) are built | `backend/clawback/alerts.py` |

### Smaller gaps (not in the table)

- Nothing has run against a connected Nylas inbox or a Plaid Link sign-in yet, so drafts, attachment downloads,
  statement dates and the webhooks are tested against fakes only. Gmail drafts may need the `gmail.compose` scope
  on the Nylas Google connector.
- Text hidden with a CSS class or white on white still counts as visible to the injection screen.
- Days left in a trial are range-checked but not yet checked against the email text.
- Stores that load prices in the browser (Target) never get a live price.
- The cancel-page cache is a JSON file (`CLAWBACK_CANCEL_CACHE`), not in the database.
- Plaid Items linked before `PUBLIC_API_URL` was set have no webhook.
- The OAuth `state` lives in memory, so the backend runs as one process.
- Spend limits are soft: calls already in flight can pass a limit by a few cents.
- "Potential savings" still counts subscriptions you have started cancelling.
- One inbox and one bank per session; connecting another replaces it.
- Outlook's native search (KQL) through Nylas is unverified; sync falls back to the keyword scan.
- Purchases ignore quantities, tax and shipping; per-bank CSV quirks beyond common column names aren't handled.
- Frontend types are hand-copied from the backend models rather than generated. No CI.

## Decisions made for this prototype (change them if they're wrong)

1. **Five areas, one data set (2026-10-22).** Subscriptions, bills, bank charge problems, refunds owed and
   settlements, all from the same bank and email data. Every rule comes from `backend/clawback/rules`
   (fact-checked separately, with source links); only `verified` rows can raise a finding.
2. **Ask before acting.** ClawBack prepares the cancellation, dispute letter, request or script, and the person
   sends it, from their own mailbox when drafts are allowed. It never files a settlement claim (those are made
   under penalty of perjury).
3. **No browser extension for now.** It's the best usage signal but the biggest privacy cost.
4. **Rules + Nemotron 3.5 Lightning instead of a fine-tuned classifier.** At a few users, Lightning costs less
   than keeping a classifier server running.
5. **Decided on 2026-10-23:**
   - **Demo access:** each visitor gets their own session with no login.
   - **Hosting:** the backend goes on Nebius AI Cloud.
   - **Banks:** Plaid stays on the test bank.
   - **Build:** Nylas drafts, the Tavily cancel-page lookup, and Apple and Google Play matching.
   - **Eval:** a synthetic labelled set, disclosed as synthetic.
   - **Nightly job:** built now, scheduled after deploy.
   - **Zero Data Retention** is on in Token Factory.
