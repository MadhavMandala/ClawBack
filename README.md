# ClawBack

**Rocket Money shows what you pay. ClawBack finds the money you can get back, and does the next step.**

- **Try it:** `[DEMO URL]` (no login; each browser gets its own made-up demo month)
- **Video:** `[VIDEO URL]`

ClawBack reads your bank, your email and your Google Maps Timeline. The dashboard leads with three jobs, each done
start to finish:
- A gym you stopped going to: the Timeline shows no visits since late August, so NVIDIA Nemotron 3 Ultra writes the
  cancellation email with the notice the gym asks for, and ClawBack sends it from your own inbox when you click
  Send.
- Streaming you don't watch: Netflix's price went up and it emailed "we miss you." One button opens Netflix's own
  cancel page, with a reminder before the next charge.
- A purchase that got cheaper: you paid $249 for AirPods, and bestbuy.com, checked live through Tavily, lists them
  for less today. Ultra writes the request for the difference before the store's window closes.

Behind those three, the same pipeline also finds bills that crept up, duplicate charges, bank fees, flight refunds
and class-action settlements. You make the final click: ClawBack doesn't cancel, pay or file anything, and the
only thing it sends is the gym email, after you click Send. In the demo, that email goes to your own address.

> Status: hackathon prototype. The NVIDIA Nemotron models on Nebius Token Factory run live. Each visitor gets
> their own private demo month with no login, and can connect their own email or Plaid's test bank. See
> [STATUS.md](STATUS.md) for what works and what doesn't, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
> for the full design.

## NVIDIA Nemotron on Nebius Token Factory

Every model call in ClawBack goes to an NVIDIA Nemotron model on Nebius Token Factory. Each of the five models has
one job. The small ones read every email; the large ones run only when you click something.

| Tier | Model | Job | When it runs |
|---|---|---|---|
| fast | `nvidia/Nemotron-3_5-Lightning` (thinking off) | Email to facts, receipts and flights, unknown senders and charges, the injection check, store prices | Every email that passes triage, once (cached) |
| fast_fallback | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Same, when Lightning fails | Only on failure |
| mid | `nvidia/nemotron-3-super-120b-a12b` | Reads plan pages, bill offers and settlement pages into lists | "Find cheaper", "Negotiate", the settlements refresh |
| reason | `nvidia/Nemotron-3-Ultra-550b-a55b` | Fits plans to usage (thinking on); writes letters, scripts and cancel emails when a merchant takes them | When you click |
| vision | `nvidia/Nemotron-3.5-Super-VL` | Receipt images and scanned PDFs | Attachments on receipt emails |

If a model call fails, the next tier takes over, then a code fallback, so the app keeps working. Models never
compute dates or money, and every link comes from a checked search result. Each session has a daily model spend
limit. The dashboard's trace shows every call with its tier, tokens (thinking tokens included) and cost. On the
held-out eval set, the whole pipeline cost about $0.057 per 1,000 emails ([docs/EVAL.md](docs/EVAL.md)).

### Where Token Factory sped us up

- One client for five models: the API is OpenAI-compatible, so the standard `openai` SDK pointed at Token Factory
  is all the client code ([backend/clawback/llm.py](backend/clawback/llm.py)). Moving a job to another model is a
  one-line change in the tier table.
- Strict JSON on every Nemotron model: a strict `json_schema` response format came back schema-shaped on all five,
  so we dropped most defensive parsing. The same prompt and schema work on every model, which is why the Lightning
  to Nano fallback needed no special case.
- Prices and model IDs from the public catalog, which needs no key. Our cost table comes from it, so each call's
  cost is logged as it happens.
- Speed: Lightning answers a short prompt in 0.7 to 0.9 seconds, and 15 emails in parallel took about 2.4 seconds.
  That made reading every email affordable.
- Zero Data Retention is one organization setting, and it's on, so prompts carrying facts from people's email
  aren't kept.

### Other Nebius services

- Nebius AI Cloud: the hosted backend is set up for one CPU VM (`cpu-d3`, 2 vCPU, 8 GB) with Caddy for HTTPS. We
  picked a VM over Serverless endpoints because the email sign-in and webhooks need a fixed URL. The runbook is
  [docs/DEPLOY.md](docs/DEPLOY.md), and the scripts are in `deploy/vm/`.
- Our notes on Token Factory, the Nemotron models and AI Cloud, including what we'd change, are in
  [docs/token-factory-feedback.md](docs/token-factory-feedback.md).

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

People using ClawBack click **Connect email** or **Connect bank** and sign in on their provider's own page.
For that to work, the person running the app registers it once with two services and puts the keys in
`backend/.env` (copy `backend/.env.example`). Never commit real keys to a public repo.

**Email, any provider (Nylas):** one sign-in page covers Gmail, Outlook/Hotmail/Microsoft 365, Yahoo, iCloud
and other IMAP inboxes.
1. Sign up at https://dashboard-v3.nylas.com and create a Sandbox app. It's free for 5 connected accounts.
2. Copy the app's Client ID, and create an API key.
3. Under **Hosted authentication → Callback URIs**, add `http://localhost:8000/api/connect/email/callback`.
4. Set `NYLAS_CLIENT_ID` and `NYLAS_API_KEY`. EU apps also set `NYLAS_API_URI=https://api.eu.nylas.com`.
5. Saving drafts needs a write scope on the connector: Gmail `gmail.compose`, Microsoft `Mail.ReadWrite`. The gym
   email's **Send** button needs `gmail.send`.

**Bank (Plaid):**
1. Sign up at https://dashboard.plaid.com/signup.
2. Under **Developers → Keys**, copy the client ID and the Sandbox secret.
3. Set `PLAID_CLIENT_ID`, `PLAID_SECRET` and `PLAID_ENV=sandbox`.
4. Sandbox only has test banks. In the Plaid window, pick First Platypus Bank and sign in with `user_good` /
   `pass_good`.
5. Real banks need Plaid Production access. The team chose to stay on the test bank for the hackathon.

Restart the backend after editing `.env`. Connecting a real source replaces the demo data.

### Gmail add-on (optional)

A Chrome extension in [`extension/`](extension) puts a small ClawBack flag on Gmail emails from services where
ClawBack found money, such as Netflix, the gym or Best Buy in the demo month. Hovering shows what ClawBack found
and how much you could save, and **More info** opens that item on the dashboard.

1. In Chrome, open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the
   `extension` folder. Pin it to the toolbar if you like.
2. Open ClawBack's settings page (`/settings`) in the same browser and click **Connect** on the Gmail add-on row.
3. Reload Gmail.

The extension reads one thing from Gmail: each sender's address, from the inbox list. It matches the address's
domain against the flags inside the browser, so nothing from Gmail is sent anywhere, and it never changes or clicks
anything in Gmail. It talks to ClawBack with a read-only token that lists flags and nothing else; **Disconnect** on
the settings page revokes it. The extension works with `localhost` and with a backend on `*.sslip.io`
([docs/DEPLOY.md](docs/DEPLOY.md)); for another address, add it to `host_permissions` in `extension/manifest.json`
and to `API_ALLOWED` in `extension/handoff.js`.

For filming, `CLAWBACK_DEMO_SENDERS=Netflix=teammate@example.com` on the backend flags mail from that exact address
as Netflix, in place of netflix.com, so a teammate can send the email that gets flagged. Separate merchants with
`;` and addresses with `,`.

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
Gym:              Timeline upload ──> gym visit dates (code) ──> Ultra writes the notice ──> sent on your click
Price drop:       Tavily (store's own site) ──> code checks the price is on the page ──> Ultra writes the request
Letters:          Nemotron 3 Ultra writes from facts code worked out; code checks every number, date and link
```

Cheap steps run on everything. Models only see the few items that need judgement, and code does all the date and
money arithmetic. Every step is logged with its engine, time and cost, and the dashboard shows that log.

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
  `nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/Nemotron-3.5-Super-VL`). See "NVIDIA Nemotron on Nebius Token
  Factory" above.
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
frontend/app/        front page (page.tsx), dashboard/, built/, settings/, privacy/
docs/                architecture, design, eval, deploy, privacy, write-up, video, feedback
STATUS.md            what works / what's MISSING
```

## License

ClawBack is open source under the [MIT License](LICENSE).
