# Model tiers: design

Date: 2026-10-22 · Owner: Ishani · Branch: `feat/model-tiers`

## Why

ClawBack is entering the Nebius x NVIDIA Global AI Hackathon, **Best Apps and Agents** track. Submissions close
**Fri Oct 30, 10:00 am PT**. A project counts if it "makes a runtime call to the Token Factory inference API" and uses
at least one NVIDIA open model. Judges score "how effectively it uses ... Nemotron" and the track asks for
"Ultra when you need serious reasoning, Nano or Super for the fast, everyday calls."

Today every model call in the code is written but untested, and the regex stand-ins do the real work. This
project makes the models real: each tier makes live calls, every feature that should use a model does, and
the dashboard trace shows which model did what and what it cost.

Split of work: a teammate is building the Gmail and bank (Plaid) connections. This project owns the model
tiers and every place the pipeline calls a model.

## What was verified live (2026-10-22, one call per model)

All five models are in the account's `/v1/models` list under the exact IDs in `llm.py`.

| Model | Strict JSON (`response_format: json_schema`) | Thinking on | Speed (short email, thinking off) |
|---|---|---|---|
| `nvidia/Nemotron-3_5-Lightning` | works | **breaks output**: writes "Here's a thinking process: ..." as plain text in `content`, no `<think>` tags, and used all 400 tokens | ~0.7 s |
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | works | content stays clean; no separate reasoning returned | ~0.6 s |
| `nvidia/nemotron-3-super-120b-a12b` | works, also with thinking on | reasoning comes back in `message.reasoning_content`; `content` is clean | ~0.9 s |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | works, also with thinking on | same as Super | ~0.8 s (≈1.2 s with thinking) |
| `nvidia/Nemotron-3.5-Super-VL` | works (text only tested) | reasoning in `reasoning_content` | ~0.9 s |

`chat_template_kwargs: {enable_thinking: bool}` is honoured. This closes the `MISSING [json-schema-check]` item.

## The tiers

| Tier (role key) | Model | Thinking | Jobs | When it runs |
|---|---|---|---|---|
| `fast` | Nemotron 3.5 Lightning | **always off** | Email → structured facts (extraction) | Every email that survives rules triage |
| `fast_fallback` | Nemotron 3 Nano | off | Same as `fast` | Only when a `fast` call fails or returns invalid JSON |
| `mid` | Nemotron 3 Super | off | Read plan/pricing page text → list of plans with prices | "Find cheaper", on request |
| `reason` | Nemotron 3 Ultra | on for choosing plans, off for writing | Fit plans to the user's usage; write the cancellation email | "Find cheaper" and "Prepare cancel", on request |
| `vision` | Nemotron 3.5 Super-VL | — | Receipts as images/PDFs | **Not in this project** (stays MISSING, P2) |

Cheap, fast models run on volume. Expensive models run only when the user clicks something.

## Where each tier is used

### 1. Extraction (`pipeline/extract.py`, tier `fast`)

- When a Nebius key is set, every triaged email goes to Lightning with a strict JSON schema matching the
  existing `Fact` fields (`kind` as an enum, numbers or null, `trial_days_left` as integer or null).
- Thinking off. Small `max_tokens` (~300).
- The model reports what the email says; **code** still does all date math (`trial_days_left` → `trial_end`).
- Failure chain per email: Lightning → Nano → regex rules. Each attempt is a trace row, so a fallback is visible.
- With no key (tests, offline demo), today's regex path stays as it is.
- The `extract_all(user_id, emails: list[Email])` signature stays the same. The teammate's Gmail code feeds it
  `Email` objects and needs nothing else from us.

### 2. Find cheaper (`pipeline/recommend.py`, tiers `mid` then `reason`)

1. Tavily search for the merchant's current plans (as today).
2. **New, `mid`:** Super reads the returned page text and returns a structured list of plans
   (`name`, `monthly_price`, `source` index). This gives Super a real job and makes Ultra's input short and clean.
3. `reason`: Ultra, thinking on, strict JSON schema, gets the plan list plus the usage evidence and returns up
   to 3 options (`option`, `monthly_price`, `why`, `source`).
4. Code keeps the existing rule: an option without a valid `source` index is dropped, and the URL always comes
   from Tavily, never from the model.
5. Ultra's `reasoning_content` is never shown as the answer. Its length (tokens) goes in the trace note.
6. If Super fails, Ultra gets the raw snippets (today's behaviour). If Ultra fails, the user still sees the
   code hints, and the trace shows the error.

### 3. Prepare cancel email (`pipeline/cancel.py`, tier `reason`, thinking off)

- Ultra writes a short, polite cancellation email that uses what we know: merchant, price, a recent price
  increase, a trial end date (all passed in as facts computed by code).
- Output is JSON `{subject, body}`. It must keep the `[your account email]` placeholder and must not invent
  account numbers, dates or links.
- If the call fails or there's no key, the current template is used.
- Still never sent: the teammate's Gmail drafts work picks it up later.

## Shared model layer (`llm.py`)

- One table, per tier: model ID, fallback tier, default thinking, default `max_tokens`, timeout.
- `chat()` gains a `schema=` argument that sends `response_format: json_schema`. `parse_json` stays as a
  safety net.
- `chat()` refuses `thinking=True` on the `fast` tier (a guard against the Lightning problem above).
- Every call records a trace row: tier, model, ms, tokens in/out, reasoning tokens if any, cost, and
  `ok` / `fallback` / `error`.
- A smoke-test command, `python -m clawback.llm --check`, makes one tiny call per tier and prints a table like
  the one above. It's for us, for the README, and for the hackathon feedback section.

## Decisions from review (Claude's calls; change them if wrong)

- **Cache extraction per email.** `run()` is called on many clicks (sync, keep, check-in, cancel prep).
  Facts are cached by `email.id` in the user's store, so each email goes to Lightning once. The trace still
  shows one `extract` row per run, with a note like "12 emails: 3 sent to Lightning, 9 cached".
  "Reset demo" clears the cache.
- **On-click model rows survive pipeline re-runs.** Today `run()` clears the whole trace, which would wipe
  the Ultra cancel-email row before the dashboard shows it. Pipeline rows (triage, extract, code steps) are
  replaced on each run. On-click rows (Super, Ultra, Tavily) are kept, newest first, capped at the last 20, and
  cleared by "Reset demo".
- **Small dashboard changes are in scope.** Add `tier`, `reasoning_tokens` and a `fallback` status to
  `TraceStep` and the frontend types, and show them in the existing trace table (a tier column and a style for
  "fallback"). No other frontend work.

## Goals

- Every tier except `vision` makes live calls in the running app, with the key set.
- Extraction, find cheaper and cancel email all use their tier for real.
- The dashboard trace shows each model call with its cost, so the "which model does what" story is visible
  in the demo video.
- The app still works end to end with no key (demo data + regexes + template), so tests and offline demos
  don't break.

## Non-goals

- Hosting models ourselves (Nebius Serverless Endpoints, downloading weights). Token Factory calls meet the
  rules; this can be a stretch goal after Oct 30 is safe.
- The vision tier / PDF receipts.
- A trained email classifier.
- Gmail, Plaid, Supabase, login (teammate or other work).

## Anti-goals (would be a failure even if it "works")

- A model computing a date, a total, or a deadline.
- A link shown to the user that came from a model instead of Tavily or our verified list.
- Model reasoning text shown to the user as the answer.
- The demo breaking because one model call failed.
- Unit tests that need a key or hit the network.

## Constraints

- Deadline Oct 30, 10:00 am PT.
- Zero Data Retention must be on in the Token Factory profile before any real email is processed.
- Credits are limited: expensive tiers run only on a click; extraction stays on Lightning.
- Keys live only in `backend/.env` (git-ignored).

## Testing

- Unit tests use a fake client (no network): schema is sent, fallback chain works, `fast` + thinking is
  refused, unsourced options are dropped, template is used when the model fails.
- One opt-in live test (skipped without `NEBIUS_API_KEY`) runs the demo emails through Lightning and checks
  the facts match today's regex results.
- `--check` smoke command before recording the demo.

## Left to the builder

- Exact JSON schemas and prompt wording.
- Whether extraction runs emails in parallel (a small thread pool is fine) or one by one.
- Timeout values and retry counts (suggest one retry on a 429/5xx before falling back).
- Whether tiers can be overridden with environment variables.
- How the trace note formats reasoning token counts.

## Also update

- `missing.py`: close `json-schema-check`, `llm-extraction`, and the model half of `alternatives`.
- README and `docs/ARCHITECTURE.md` §7: the verified table above.
- Keep a running list of Token Factory/Nemotron feedback for the submission (first item: Lightning with
  thinking on writes its reasoning into `content` with no tags).
