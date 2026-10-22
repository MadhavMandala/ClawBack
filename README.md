# ClawBack

**Rocket Money shows what you pay. ClawBack works out what each subscription is worth to you.**

ClawBack connects to your bank and your email, finds every subscription you pay for, and checks whether you
actually use each one. When something isn't pulling its weight, it tells you why and does the legwork:
- a membership that costs more than it saves;
- a service you've stopped using;
- two plans doing the same job;
- a free trial about to convert;
- a price that quietly went up.

It finds the cancel page, writes the cancellation email, or finds a cheaper plan that fits how you use it.
**You make the final click.** ClawBack never cancels or sends anything on its own.

> **Status: rough prototype.** It runs end to end on made-up demo data, with live Nemotron calls when a Token
> Factory key is set. Real bank and Gmail connections, login and the database are **MISSING**. See [STATUS.md](STATUS.md) for exactly what works and what
> doesn't, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Run it locally

You need Python 3.11+ and Node 20+.

**Backend** (FastAPI, port 8000):

```bash
cd backend
uv venv .venv            # or: python -m venv .venv
uv pip install -e ".[dev]" --python .venv/bin/python    # Windows: .venv/Scripts/python.exe
cp .env.example .env     # add NEBIUS_API_KEY / TAVILY_API_KEY (loaded automatically)
.venv/bin/python -m clawback.llm --check                # one live call per model tier
.venv/bin/python -m uvicorn clawback.main:app --reload --port 8000
.venv/bin/python -m pytest -q                           # offline; never calls the APIs
CLAWBACK_LIVE=1 .venv/bin/python -m pytest tests/test_live.py   # opt-in live extraction check
```

On Windows use `.venv/Scripts/python` in place of `.venv/bin/python`. Without keys the app still runs: regexes stand
in for extraction and a template for the cancel email.

**Frontend** (Next.js, port 3000):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The backend seeds a demo user on start-up. "Reset demo" reloads it.

## How it works (short version)

```
bank charges ──> recurring detection (code) ──┐
                                              ├─> usage + value + flags (code) ──> dashboard
emails ──> triage (rules) ──> extraction (Nemotron 3.5 Lightning) ──┘
                     "Find cheaper": Tavily ──> Nemotron 3 Super (read plans) ──> Nemotron 3 Ultra (fit to usage)
                     "Prepare cancel": Tavily (cancel page) + Nemotron 3 Ultra (email text) ──> you send it
```

Cheap steps run on everything. Models only see the few items that need judgement, and code does all the date and
money arithmetic. Every step is logged with its engine, time and cost, and the dashboard shows that log.

## Model tiers (Nemotron on Nebius Token Factory)

| Tier | Model | Job | When it runs |
|---|---|---|---|
| fast | `nvidia/Nemotron-3_5-Lightning` (thinking off) | Email → structured facts, strict JSON schema | Every email that passes triage, once (cached) |
| fast_fallback | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Same, when Lightning fails | Only on failure |
| mid | `nvidia/nemotron-3-super-120b-a12b` | Reads plan/pricing pages into a plan list | "Find cheaper" click |
| reason | `nvidia/Nemotron-3-Ultra-550b-a55b` | Fits plans to your usage (thinking on); writes the cancel email | "Find cheaper" / "Prepare cancel" click |
| vision | `nvidia/Nemotron-3.5-Super-VL` | Receipt images and PDFs | Not wired in yet (MISSING) |

If a model call fails, the next tier takes over, then the code fallback, so the app never breaks. Models never
compute dates or money, and links always come from Tavily, never from a model. The dashboard's model trace shows
every call with its tier, tokens (including thinking tokens) and cost. Typical cost: about $0.0005 to read 15 emails,
about $0.005 per "Find cheaper" click.

## Built with

- **NVIDIA Nemotron** models on **Nebius Token Factory**, through its OpenAI-compatible API
  (`nvidia/Nemotron-3_5-Lightning`, `nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/Nemotron-3.5-Super-VL`).
  See "Model tiers" above.
- **Tavily** for current plan prices and cancel pages
- FastAPI (Python) backend, Next.js frontend
- Planned: Plaid, the Gmail API, Supabase (all MISSING)

## Repo layout

```
backend/clawback/
  main.py            API routes
  pipeline/          triage -> extract -> recurring -> usage -> value -> flags; recommend + cancel actions
  sources/           gmail.py, plaid.py (stubs), statements.py (CSV upload)
  llm.py             Token Factory client: model tiers, fallbacks, prices, --check
  tools/tavily.py    web search
  missing.py         the list of everything not built yet
  demo_data.py       the fake user
frontend/app/        one-page dashboard
docs/ARCHITECTURE.md full design
STATUS.md            what works / what's MISSING
```

License: **MISSING**. An open-source license is still to be chosen.
