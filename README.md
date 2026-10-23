# ClawBack

**Rocket Money shows what you pay. ClawBack finds the money you can get back, and writes the request.**

ClawBack connects to your bank and your email and looks for money in five places:
- **subscriptions** you've stopped using, two plans doing one job, free trials about to convert, prices that crept up;
- **bills** that jumped when a promotional rate ended;
- **bank charges**: the same charge twice, and fees a bank will often reverse;
- **refunds owed**: price drops inside a store's adjustment window, cancelled or changed flights;
- **settlements**: open class-action settlements that match what you bought.

For each one it prepares the cancel page and email, the negotiation script, the dispute letter or the claim link,
and can save the email as a draft in your own mailbox. **You make the final click.** ClawBack never cancels,
pays, sends or files anything on its own.

> **Status: hackathon prototype.** Each visitor gets their own private demo month with no login, and can connect
> their own email or Plaid's test bank. The NVIDIA Nemotron models on Nebius Token Factory run live. Not deployed
> yet. See [STATUS.md](STATUS.md) for exactly what works and what doesn't, and
> [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Run it locally

You need Python 3.11+ and Node 20+.

**Backend** (FastAPI, port 8000):

```bash
cd backend
uv venv .venv            # or: python -m venv .venv
uv pip install -e ".[dev]" --python .venv/bin/python    # Windows: .venv/Scripts/python.exe
cp .env.example .env     # add your keys (loaded automatically)
.venv/bin/python -m clawback.llm --check                # one live call per model tier
.venv/bin/python -m uvicorn clawback.main:app --reload --port 8000
.venv/bin/python -m pytest -q                           # offline; never calls the APIs
CLAWBACK_LIVE=1 .venv/bin/python -m pytest tests/test_live.py tests/test_live_findings.py   # opt-in live checks
```

On Windows use `.venv/Scripts/python` in place of `.venv/bin/python`. Without keys the app still runs: rules stand
in for the models and templates for the letters.

**Frontend** (Next.js, port 3000):

```bash
cd frontend
npm install
npm run dev
```

Pages:
- http://localhost:3000, the front page;
- http://localhost:3000/dashboard, the app;
- http://localhost:3000/settings, "Your data": connections, your state, what's stored, delete everything;
- http://localhost:3000/privacy, the privacy policy.

On a phone, ClawBack installs on the home screen and opens full screen, like an app: the settings page has the
install button (Android) or the steps (iPhone). A native app is planned; see [docs/MOBILE.md](docs/MOBILE.md).

Each browser gets its own session and its own copy of the demo month. "Reset demo data" reloads it. To share
one user across browsers in local development, set `CLAWBACK_SESSIONS=single`.

### Other commands (from `backend/`)

```bash
.venv/bin/python -m clawback.nightly                     # grant check, sync, re-run checks, alerts; prune idle sessions
.venv/bin/python -m clawback.findings.settlements_refresh  # settlement candidates for a person to review
.venv/bin/python -m evals.run --models both              # the labelled eval set; writes docs/EVAL.md
.venv/bin/python -m clawback.missing                     # the MISSING table in STATUS.md
.venv/bin/python -m clawback.features                    # the build-status board as a table
```

### Connect real email and a bank (optional)

People using ClawBack just click **Connect email** or **Connect bank** and sign in on their provider's own page.
For that to work, the person running the app registers it once with two services and puts the keys in
`backend/.env` (copy `backend/.env.example`). Never commit real keys to a public repo.

**Email, any provider (Nylas).** One sign-in page covers Gmail, Outlook/Hotmail/Microsoft 365, Yahoo, iCloud
and other IMAP inboxes.
1. Sign up at https://dashboard-v3.nylas.com and create a Sandbox app. It's free for 5 connected accounts.
2. Copy the app's Client ID, and create an API key.
3. Under **Hosted authentication → Callback URIs**, add `http://localhost:8000/api/connect/email/callback`.
4. Set `NYLAS_CLIENT_ID` and `NYLAS_API_KEY`. EU apps also set `NYLAS_API_URI=https://api.eu.nylas.com`.
5. Saving drafts needs a write scope on the connector: Gmail `gmail.compose`, Microsoft `Mail.ReadWrite`.

**Bank (Plaid).**
1. Sign up at https://dashboard.plaid.com/signup.
2. Under **Developers → Keys**, copy the client ID and the Sandbox secret.
3. Set `PLAID_CLIENT_ID`, `PLAID_SECRET` and `PLAID_ENV=sandbox`.
4. Sandbox only has test banks. In the Plaid window, pick First Platypus Bank and sign in with `user_good` /
   `pass_good`.
5. Real banks need Plaid Production access. The team chose to stay on the test bank for the hackathon.

Restart the backend after editing `.env`. Connecting a real source replaces the demo data.

### Settings (`backend/.env` or the server's environment)

| Variable | What it does |
|---|---|
| `NEBIUS_API_KEY`, `TAVILY_API_KEY` | The models (Token Factory) and web search |
| `NYLAS_CLIENT_ID`, `NYLAS_API_KEY`, `NYLAS_API_URI` | Email through Nylas |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV` | Bank through Plaid |
| `CLAWBACK_DB_PATH` | The SQLite database (default `backend/.local/clawback.db`) |
| `CLAWBACK_SECRET_KEY` | Fernet key that encrypts every stored row and token. Without it, local dev makes one in `backend/.local/secret.key` |
| `CLAWBACK_SESSIONS` | `visitor` (default: a session per browser) or `single` (one shared user, for local dev) |
| `CLAWBACK_SESSION_IDLE_DAYS` | Days without a visit before a session is deleted (14) |
| `CLAWBACK_SESSIONS_PER_IP_HOUR` | New sessions allowed per IP per hour (20) |
| `CLAWBACK_SESSION_DAILY_USD`, `CLAWBACK_GLOBAL_DAILY_USD` | Daily model spend limits per session (0.25) and overall (5); 0 turns a limit off |
| `FRONTEND_ORIGIN` | Comma-separated allowed frontend origins; the first is where the email sign-in returns |
| `FRONTEND_ORIGIN_REGEX` | Extra allowed origins, e.g. Vercel preview URLs |
| `PUBLIC_API_URL` | The backend's public URL; new Plaid Links carry the webhook when it's set |
| `NYLAS_WEBHOOK_SECRET` | The secret Nylas returns when the email webhook is created |
| `CLAWBACK_CANCEL_CACHE` | The cancel-page cache file (default `backend/.local/cancel_pages.json`) |

## How it works (short version)

```
bank charges ──> recurring detection + merchant names (code, Lightning for unknowns) ──┐
                                                                                       ├─> usage, value, flags,
emails ──> triage (rules, Lightning for unknown senders) ──> injection screen ──>       │   findings (code) ──> dashboard
           extraction (Nemotron 3.5 Lightning, receipts by Super-VL) ──────────────────┘
"Find cheaper":   Tavily ──> Nemotron 3 Super (read plans) ──> Nemotron 3 Ultra (fit to usage)
"Prepare cancel": Tavily (merchant's own cancel page) + state rule + Nemotron 3 Ultra (email) ──> you send it
Letters:          Nemotron 3 Ultra writes from facts code worked out; code checks every number, date and link
```

Cheap steps run on everything. Models only see the few items that need judgement, and code does all the date and
money arithmetic. Every step is logged with its engine, time and cost, and the dashboard shows that log.

## Model tiers (Nemotron on Nebius Token Factory)

| Tier | Model | Job | When it runs |
|---|---|---|---|
| fast | `nvidia/Nemotron-3_5-Lightning` (thinking off) | Email to facts, receipts and flights, unknown senders and charges, the injection check, store prices | Every email that passes triage, once (cached) |
| fast_fallback | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Same, when Lightning fails | Only on failure |
| mid | `nvidia/nemotron-3-super-120b-a12b` | Reads plan pages, bill offers and settlement pages into lists | "Find cheaper", "Negotiate", the settlements refresh |
| reason | `nvidia/Nemotron-3-Ultra-550b-a55b` | Fits plans to usage (thinking on); writes the cancel email, letters and scripts | When you click |
| vision | `nvidia/Nemotron-3.5-Super-VL` | Receipt images and scanned PDFs | Attachments on receipt emails |

If a model call fails, the next tier takes over, then the code fallback, so the app never breaks. Models never
compute dates or money, and links always come from checked search results, never from a model. Each session has a
daily model spend limit. The model trace shows every call with its tier, tokens (including thinking tokens) and
cost. Measured cost on the eval set: about $0.026 per 1,000 emails for the whole pipeline (see
[docs/EVAL.md](docs/EVAL.md)).

## Docs

- [STATUS.md](STATUS.md): what works and what's MISSING
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): the full design
- [docs/DESIGN.md](docs/DESIGN.md): visual design rules
- [docs/EVAL.md](docs/EVAL.md): the labelled eval set, its results and every failure case
- [docs/DEPLOY.md](docs/DEPLOY.md): deploy runbook (Nebius VM + Vercel), and the cleanup before going public
- [docs/PRIVACY.md](docs/PRIVACY.md): the prototype privacy policy
- [docs/MOBILE.md](docs/MOBILE.md): ClawBack on your phone: the installable web app now, a native app later
- [docs/WRITEUP.md](docs/WRITEUP.md): the submission write-up draft
- [docs/VIDEO.md](docs/VIDEO.md): the demo video script
- [docs/token-factory-feedback.md](docs/token-factory-feedback.md): feedback on Token Factory and the models

## Built with

- **NVIDIA Nemotron** models on **Nebius Token Factory**, through its OpenAI-compatible API
  (`nvidia/Nemotron-3_5-Lightning`, `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/nemotron-3-super-120b-a12b`,
  `nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/Nemotron-3.5-Super-VL`). See "Model tiers" above.
- **Tavily** for current plans, cancel pages, bill offers, store prices and new settlements
- **Nylas** for email from any provider, and **Plaid** for bank transactions
- FastAPI (Python) with SQLite, and a Next.js frontend

## Repo layout

```
backend/clawback/
  main.py            API routes
  sessions.py        per-visitor sessions; demo.py copies the demo month into each one
  store.py, db.py    encrypted SQLite storage (crypto.py); budget.py daily model limits
  pipeline/          subscriptions: triage -> guard -> extract -> recurring -> usage -> value -> flags; cancel, cheaper, confirm
  findings/          bills, duplicate charges, bank fees, price drops, flight refunds, settlements; letters
  rules/             verified rules data with official sources (refund windows, flight rules, state laws, settlements)
  sources/           nylas.py (email, drafts, webhooks), plaid.py (bank, webhooks), statements.py (CSV, OFX)
  connect.py         connect / sync / disconnect; nightly.py the nightly job; alerts.py in-app alerts
  llm.py             Token Factory client: model tiers, fallbacks, prices, --check
  tools/             tavily.py (web search), prices.py (current-price checks)
  missing.py         the list of everything not built yet; features.py the build-status board
backend/evals/       the labelled eval set and its scorer
deploy/vm/           Nebius VM setup, update script, systemd units and Caddy config
frontend/app/        front page (page.tsx), dashboard/, settings/, privacy/
docs/                architecture, design, eval, deploy, privacy, write-up, video, feedback
STATUS.md            what works / what's MISSING
```

License: [MIT](LICENSE). The repo is private for now.
