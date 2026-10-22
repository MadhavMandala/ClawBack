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

> **Status: rough prototype.** It runs end to end on made-up demo data. Real bank and Gmail connections, the live
> Nemotron calls, login and the database are **MISSING**. See [STATUS.md](STATUS.md) for exactly what works and what
> doesn't, and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

## Run it locally

You need Python 3.11+ and Node 20+.

**Backend** (FastAPI, port 8000):

```bash
cd backend
uv venv .venv            # or: python -m venv .venv
uv pip install -e ".[dev]" --python .venv/Scripts/python.exe   # macOS/Linux: .venv/bin/python
cp .env.example .env     # optional: add NEBIUS_API_KEY / TAVILY_API_KEY
.venv/Scripts/python -m uvicorn clawback.main:app --reload --port 8000
.venv/Scripts/python -m pytest -q                               # 8 tests
```

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
                     "Find cheaper": Tavily (current plans) ──> Nemotron 3 Ultra (fit to your usage)
                     "Prepare cancel": Tavily (cancel page) + email draft ──> you send it
```

Cheap steps run on everything. Models only see the few items that need judgement, and code does all the date and
money arithmetic. Every step is logged with its engine, time and cost, and the dashboard shows that log.

## Built with

- **NVIDIA Nemotron** models on **Nebius Token Factory**, through its OpenAI-compatible API
  (`nvidia/Nemotron-3_5-Lightning`, `nvidia/Nemotron-3-Ultra-550b-a55b`, `nvidia/Nemotron-3.5-Super-VL`).
  The client is written, but no live call has been made yet (MISSING).
- **Tavily** for current plan prices and cancel pages (written, untested: MISSING)
- FastAPI (Python) backend, Next.js frontend
- Planned: Plaid, the Gmail API, Supabase (all MISSING)

## Repo layout

```
backend/clawback/
  main.py            API routes
  pipeline/          triage -> extract -> recurring -> usage -> value -> flags; recommend + cancel actions
  sources/           gmail.py, plaid.py (stubs), statements.py (CSV upload)
  llm.py             Nebius Token Factory client, model roles, prices
  tools/tavily.py    web search
  missing.py         the list of everything not built yet
  demo_data.py       the fake user
frontend/app/        one-page dashboard
docs/ARCHITECTURE.md full design
STATUS.md            what works / what's MISSING
```

License: **MISSING**. An open-source license is still to be chosen.
