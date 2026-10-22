# Status: what works and what is MISSING

**This is a rough prototype.** It runs end to end on **made-up demo data for one fake user**. It does not connect to
any real bank or inbox yet. With a Token Factory key set, the Nemotron model tiers make live calls.

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
| Price-increase detection | Spots "was $15.49, now $17.99" from the charges themselves | same |
| Usage signals | Counts per-use receipts, "we miss you" emails, usage-summary emails and your Yes/No check-ins | `pipeline/usage.py` |
| Membership value math | "DashPass cost $9.99, saved you $2.99 on 1 order: net -$7.00" | `pipeline/value.py` |
| Flags | unused, membership losing money, two plans doing the same job, trial about to convert, price went up | `pipeline/flags.py` |
| Free-trial detection from email | Finds trials before the first charge, with the end date computed in code | `pipeline/run.py` |
| Apple-billed charges | Names an `APPLE.COM/BILL` charge by matching an Apple receipt email with the same amount (demo only) | `pipeline/recurring.py` |
| Cancel prep | Link + steps + cancellation email written by Nemotron 3 Ultra (template fallback). Never cancels or sends anything | `pipeline/cancel.py` |
| Email extraction | Nemotron 3.5 Lightning reads each email once (cached) into facts with a strict JSON schema; Nano and regexes as fallbacks | `pipeline/extract.py` |
| "Find cheaper" | Tavily finds current plans, Nemotron 3 Super lists them, Nemotron 3 Ultra fits them to your usage; every option cites a Tavily page. Code hints without keys | `pipeline/recommend.py` |
| Statement CSV upload | Real transactions without any bank approval | `sources/statements.py` |
| Model trace | Every step logs its tier, engine, time, tokens (incl. thinking) and cost. Click-time rows survive re-runs. Shown on the dashboard | `trace.py` |
| Token Factory client | Five model tiers, verified live; strict JSON, fallbacks, retries, timeouts; `python -m clawback.llm --check` | `llm.py` |
| Dashboard | One page: totals, subscription cards, check-ins, cancel / cheaper panels, trace, MISSING banner | `frontend/app/page.tsx` |
| Tests | Offline backend tests (fake model client) plus an opt-in live extraction test | `backend/tests/` |

## MISSING

P0 = needed for the hackathon demo. P1 = needed for a convincing submission. P2 = roadmap.

| Priority | Area | What is missing | Where |
|---|---|---|---|
| P0 | Actions | Write cancellation emails as Gmail drafts (drafts.create). The user always presses send. | `backend/clawback/sources/gmail.py` |
| P0 | Actions | 'Find something cheaper': Tavily pulls current plans and prices, Nemotron Ultra matches them to your usage | `backend/clawback/pipeline/recommend.py` |
| P0 | Actions | Find the merchant's real cancel page / support email with Tavily and cite it | `backend/clawback/pipeline/cancel.py` |
| P0 | Data sources | Gmail connection (OAuth consent with gmail.readonly + gmail.compose) | `backend/clawback/sources/gmail.py` |
| P0 | Data sources | Bank connection with Plaid Link (Sandbox first, then Trial for up to 10 real banks) | `backend/clawback/sources/plaid.py, frontend` |
| P0 | Safety | Turn on Zero Data Retention in Token Factory before any real user email is processed | `Token Factory profile settings` |
| P0 | Storage | Real database (Supabase Postgres) with per-user row-level security; currently an in-memory dict that resets on restart | `backend/clawback/store.py` |
| P0 | Storage | User accounts / login (Supabase Auth). Everything is one hard-coded 'demo' user right now | `backend/clawback/main.py` |
| P0 | Submission | Public demo URL (frontend on Vercel, backend somewhere reachable) that works until Dec 15 | `not started` |
| P0 | Submission | Open-source LICENSE file and making the repo public (both required to submit) | `repo root` |
| P1 | Actions | Confirm a cancellation worked (charge missing on the next statement / cancellation email) and add it to 'recovered' | `backend/clawback/pipeline/run.py` |
| P1 | Data sources | Gmail push notifications (users.watch -> Pub/Sub -> history.list), daily watch renewal, polling fallback | `backend/clawback/sources/gmail.py, POST /api/ingest/gmail/push` |
| P1 | Data sources | Transaction sync (/transactions/sync cursor loop + SYNC_UPDATES_AVAILABLE webhook) | `backend/clawback/sources/plaid.py, POST /api/ingest/plaid/webhook` |
| P1 | Pipeline | Work out which app an 'APPLE.COM/BILL' or 'GOOGLE *' charge is, by matching Apple / Google Play receipt emails | `backend/clawback/pipeline/recurring.py` |
| P1 | Pipeline | Learn usage patterns over time (adjust check-in frequency, trust per signal type, per-user thresholds) | `backend/clawback/pipeline/usage.py` |
| P1 | Safety | Prompt-injection guard on email content before it reaches a model (required by Google's Workspace data policy) | `backend/clawback/pipeline/extract.py` |
| P1 | Storage | Encrypted storage of Google refresh tokens and Plaid access tokens | `not started` |
| P1 | Submission | Labelled test set + metrics (subscriptions found, false flags, cost per 1,000 emails) | `not started` |
| P2 | Actions | State auto-renewal rules in the claim text (e.g. NY pro-rata refund after an unconsented price increase) | `not started` |
| P2 | Data sources | Outlook / Microsoft 365 via Microsoft Graph (Mail.Read + Mail.ReadWrite drafts) | `not started` |
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
- No CI.

## Decisions made for this prototype (change them if they're wrong)

1. **Subscriptions only.** Price-drop refunds and flight refunds from the original idea are roadmap, not demo.
2. **Ask before cancelling.** ClawBack prepares the cancellation (link, steps, email) and the user does the final click.
   Automatic cancelling would mean storing everyone's passwords, and a wrong cancellation can hurt.
3. **No browser extension for now.** It's the best usage signal but the biggest privacy cost and extra build.
4. **Rules + Nemotron 3.5 Lightning instead of a fine-tuned classifier**, at least for the demo. At a few users, sending
   the leftover emails to Lightning ($0.06 per 1M input tokens) costs less than keeping a classifier server running.
