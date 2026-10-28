# Feedback on Nebius Token Factory and NVIDIA Nemotron

Running notes for the hackathon submission's feedback section. Add to it while building.

How this file is laid out:
- **By tool:** for each of Token Factory, the Nemotron models and AI Cloud, what we used it for, what worked, what
  needs work, how onboarding felt, and whether we'd build with it again.
- **Running notes:** dated notes kept while building, below the summaries.

Items marked **[confirm]** are our best reading of the code or the docs, not something we watched happen. The team
checks each one before submitting, and cuts it if it doesn't hold.

## Nebius Token Factory

**What we used it for.** Every model call in ClawBack: five NVIDIA Nemotron models behind one OpenAI-compatible
API, called with the `openai` Python SDK and `base_url` set to `https://api.tokenfactory.nebius.com/v1/`. One table
in `backend/clawback/llm.py` maps each job to a model.

**What worked.**
- **OpenAI compatibility.** Pointing the standard SDK at Token Factory was all the client code we needed.
- **The public catalog.** `https://tokenfactory.nebius.com/api/public/models_info` needs no key and lists every
  model's ID, context length and price. Our price table and model IDs come straight from it, and the `/v1/models`
  listing matched it exactly.
- **Strict JSON on every Nemotron model.** `response_format` with `json_schema` and `strict: true` returned
  schema-shaped JSON on all five, with thinking on or off (see the running notes).
- **Token counts on every response.** `usage` let us log tokens and cost for each call, and show that log to users.
- **Zero Data Retention as one switch.** Turning it on for the organization was a single setting.

**What needs work.**
1. **Say which request options Nemotron honours.** Strict `json_schema` works, but no Nemotron entry in the catalog
   carries a "JSON mode" tag. The thinking switch, `extra_body={"chat_template_kwargs": {"enable_thinking": ...}}`,
   works too, but it isn't in the API reference. We found both by testing each model. One table per model of
   supported options (JSON schema, thinking switch, `reasoning_effort`, tools) would save every team that probe.
   We didn't try `reasoning_effort`, so we can't say how it maps onto Nemotron's thinking.
2. **Document the thinking default.** Thinking is on by default for Nemotron 3. A caller who sets a small
   `max_tokens` for a short JSON answer can lose the whole budget to reasoning. Stating the default on each model
   page, next to the switch, would prevent that.
3. **Document the token fields, and which models cache.** Token Factory fills the standard OpenAI fields. In a live
   check on 2026-10-28, `usage.completion_tokens_details.reasoning_tokens` came back on Super, Ultra and Super-VL,
   counted inside `completion_tokens`. `usage.prompt_tokens_details.cached_tokens` showed 1,424 of 1,441 input
   tokens cached when we repeated a Super prompt, but 0 on the same repeat for Ultra and Super-VL, though the
   catalog lists a cached-input price for Ultra. We learned all of this by probing. The docs could say that these
   fields are filled, which models cache input and when, and whether reasoning tokens bill at the output price.
   (Our own cost log doesn't read the cached field yet, so it charges every input token at the full price.)
4. **Publish typical latency and retry advice.** The OpenAI SDK retries twice by default. With Ultra thinking, one
   click could then wait for minutes. We turned SDK retries off and do one retry of our own on 429 and 5xx, and none
   on timeouts, with per-tier timeouts of 20 s (Lightning, Nano), 60 s (Super, Super-VL) and 90 s (Ultra). Typical
   and worst-case latency per model, and a recommended retry policy, would have let us pick those numbers from data.
5. **Model IDs follow three styles.** `nvidia/Nemotron-3_5-Lightning` uses an underscore for the version dot,
   `nvidia/nemotron-3-super-120b-a12b` is lower case, and `nvidia/Nemotron-3.5-Super-VL` keeps the dot. We copy IDs
   from the catalog rather than type them. One naming scheme, or aliases, would help.
6. **Warn about removals in the API itself.** Nemotron 3 Nano Omni was removed on 2026-08-31, during the hackathon.
   The deprecation page was clear, but an app only finds out from a failed call. A `Deprecation` or `Sunset`
   response header on models that are due to go would let apps log a warning weeks ahead.
7. **Let an app confirm Zero Data Retention.** ZDR is an organization setting on the profile page. Nothing in an API
   response says it is on. We process email, so we'd like our health check to assert it at start-up. A response
   header, or a field on `/v1/models`, would make that possible.
8. **A Nemotron guard model.** Google's rules for Gmail data ask for protection against prompt injection. There is no
   NVIDIA safety or guard model on Token Factory to build that screen on. A hosted Nemotron guard model would fit
   that need directly. We built ours in two steps: rules first (instruction-like phrases, hidden characters, hidden
   HTML), then Nemotron 3.5 Lightning answering yes or no on borderline emails. A guard model would replace the
   second step. There is also no NVIDIA embedding model; the only embedding model is `Qwen/Qwen3-Embedding-8B`.
9. **Fine-tuning for Nemotron.** Fine-tuning covers Qwen, Llama, gpt-oss and Gemma, not Nemotron. We'd have liked to
   train Lightning or Nano on labels from Ultra for our email filter, and keep the whole pipeline on Nemotron.

**Onboarding (zero to hello world).** The OpenAI SDK, the base URL and a key were enough for a first call. The
part that took time was finding out which options each Nemotron model honours (items 1 and 2).
**[confirm]** how long the first call took, from sign-up, in the team's own words.

**Would we build with it again?** **[confirm]** Draft: yes. One OpenAI-compatible API gave us the whole Nemotron
range, from Lightning for every email to Ultra for the hard calls, at clear per-token prices, with Zero Data
Retention for user email. The gaps above cost us probing time, not features.

## NVIDIA Nemotron models

**What we used them for.**
- Nemotron 3.5 Lightning reads every email that passes our rules into facts, with thinking off.
- Nemotron 3 Nano is Lightning's backup.
- Nemotron 3 Super reads plan and pricing pages into a list of plans.
- Nemotron 3 Ultra fits those plans to how a person uses a service (thinking on), and writes the gym cancellation
  email and the price-drop request.
- Nemotron 3.5 Super-VL reads receipt images attached to order emails. It ran live on made-up receipts; no real
  inbox has sent one through it yet.

**What worked.**
- Lightning is fast and cheap enough to run on every email (timings in the running notes).
- Super, Ultra and Super-VL keep reasoning out of the answer, in `reasoning_content`, so strict JSON still works
  with thinking on.
- **[confirm]** Ultra's thinking was worth it for the one judgement call we give it: matching plans to usage.
- The same prompt and schema worked across all five models, so the fallback from Lightning to Nano needed no
  special case.

**What needs work.**
- Lightning with thinking on writes its reasoning into `content`, with no tags, and can use the whole budget. Our
  code refuses to turn thinking on for that tier.
- Lightning over-labels receipts out of the box, and returns merchant names as written. Both are easy to handle in
  the prompt and in code.

**Would we build with them again?** **[confirm]** Draft: yes. Having fast, mid and large models from one family,
behind one API, made the tier split simple to build and to explain.

## Nebius AI Cloud

To finish after the deploy. Notes from planning it, from the docs before creating anything, are below;
**[confirm]** each one once the VM is running.

**What we used it for.** One small CPU VM (`cpu-d3`, 2 vCPU, 8 GB) that runs the ClawBack API, its SQLite database
and the nightly job, behind Caddy for HTTPS.

**What we found while planning.**
- **No Windows CLI.** The CLI installer supports Linux and macOS only. We planned the whole deploy in the web
  console, with Cloud Shell as the fallback for CLI steps.
- **Default CPU quota is 0 in some regions.** A new account has no CPU quota in `eu-north1` and `us-central1`, but
  200 vCPUs in `us-north1` and other regions. A first-time user who picks one of those regions hits a quota error
  before their first VM. Saying so in the VM quickstart would help.
- **Serverless endpoints don't fit webhook apps yet.** An endpoint's image and environment variables can't change
  after creation, and a new endpoint gets a new URL. Our OAuth callback and webhooks are registered against a fixed
  URL, so every settings change would mean re-registering them. The container disk is also wiped on restart. We
  chose a VM for these reasons.
- **No scheduled Serverless Jobs.** We wanted a nightly job. Jobs have no schedule option, so it runs as a timer on
  the VM.
- **Clear prices.** Per-second billing, per-vCPU and per-GiB prices, and free public IPs and traffic made the cost
  easy to work out before creating anything.

**Onboarding (zero to hello world).** `[AFTER DEPLOY: time from sign-up to the API answering over HTTPS]`

**What surprised us.** `[AFTER DEPLOY]`

**Would we build with it again?** `[AFTER DEPLOY]`

## Running notes

### 2026-10-22: first live calls (all five Nemotron models)

- **Strict JSON works everywhere.** `response_format: {"type": "json_schema", "strict": true}` returned valid,
  schema-shaped JSON on Lightning, Nano, Super, Ultra and Super-VL. That let us drop prompt-only JSON and most
  defensive parsing. The docs don't say this is supported for Nemotron models; saying so would save teams a probe.
- **Lightning with thinking on breaks structured output.** With `chat_template_kwargs.enable_thinking: true`,
  Nemotron 3.5 Lightning writes its reasoning ("Here's a thinking process: ...") straight into `content`, with no
  `<think>` tags and no `reasoning_content`, and used the whole `max_tokens` budget. We never enable thinking on
  Lightning. Either separating it like the larger models or documenting the behaviour would help.
- **Super, Ultra and Super-VL separate reasoning cleanly** into `message.reasoning_content`, and strict JSON still
  works with thinking on. Ultra used about 1,000-1,400 thinking tokens on our "fit plans to usage" prompt
  (~4 s, ~$0.005 per call).
- **Speed** on short prompts with thinking off: Lightning ~0.7-0.9 s, Nano ~0.5-0.6 s, Super / Ultra / Super-VL
  ~0.5-0.9 s. Fifteen emails in parallel (8 at a time) took ~2.4 s on Lightning.
- **Lightning over-labels receipts.** Out of the box it called a grocery receipt an app-store receipt. One line in
  the prompt fixed it.
- **Merchant names come back "as written"** ("Chipotle" for a DoorDash order, "Duolingo" for Super Duolingo).
  That's reasonable, but it means app code must map names to its own catalog. We do that in code.
- The `/v1/models` listing matches the public catalog's IDs exactly, which made setup easy.

### 2026-10-28: token fields

- One short prompt per model with thinking on, sent twice. Super, Ultra and Super-VL all filled
  `completion_tokens_details.reasoning_tokens`, inside `completion_tokens`, and all returned `reasoning_content`.
- Only Super reported cached input on the repeat (1,424 of 1,441 tokens). Ultra and Super-VL reported 0.

### 2026-10-23: planning the deploy

- The notes under "Nebius AI Cloud" above come from the docs, read while planning the deploy (`docs/DEPLOY.md`).
