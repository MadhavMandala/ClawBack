# ClawBack: project write-up

Draft for the submission page. Placeholders in `[brackets]` get filled in before submitting:
- `[EVAL: ...]` comes from `docs/EVAL.md`, the synthetic test set. Never write a number there that `docs/EVAL.md`
  doesn't show.
- `[DEMO URL]`, `[VIDEO URL]` and `[REPO URL]` come after the deploy.
- `[TEAM: ...]` is a decision for the team.

It is written for the finished build. These statements depend on work landing after the merge; check each one
before submitting, and cut it if the work didn't land:
- per-visitor sessions with no login;
- SQLite storage and encrypted tokens;
- the injection screen on email text;
- the cancel page checked to be on the merchant's own site, and cached per merchant;
- letters and emails saved as Nylas drafts;
- the nightly job;
- the backend running on Nebius AI Cloud.

**Track:** Best Apps and Agents.

- **Demo:** `[DEMO URL]`
- **Video:** `[VIDEO URL]`
- **Code:** `[REPO URL]`

---

## Inspiration

Small amounts of money leave most people's accounts every month without a decision behind them. A streaming
service nobody has opened since spring. A delivery membership that costs more than it saves. An internet bill that
jumped when a promotional rate ended. An overdraft fee a bank would reverse if asked. A store price drop, inside
the refund window. A class-action settlement for something already bought.

Each one is worth a few dollars to a few hundred. None of them feels worth an evening of reading statements,
policies and fine print. So the money stays where it is.

The evidence is already in two places people own: the bank statement and the inbox. The statement shows what you
pay. The inbox shows what you use: order receipts, "we miss you" emails, renewal notices, trial reminders, flight
changes. We wanted an agent that reads both, works out where money is slipping away, and does the paperwork to get
it back, while leaving the last click to the person.

## What it does

ClawBack connects to your bank (through Plaid) and your email, from any provider (through Nylas). It finds money in
five places:

| Area | What ClawBack finds | What it prepares |
|---|---|---|
| Subscriptions | Services you've stopped using, memberships that lose money, two plans doing one job, trials about to convert, prices that crept up | The merchant's own cancel page and a reminder before the next charge, or a cheaper plan that fits how you use it |
| Bills | Internet, phone and insurance that went up, often when a promotion ended | A negotiation script with what you paid before |
| Bank charges | The same charge twice; overdraft, ATM and foreign transaction fees | A dispute letter with its deadline, or a polite request to reverse the fee |
| Refunds owed | Price drops inside a store's adjustment window; cancelled or heavily changed flights | A claim citing the store's policy, or the US Department of Transportation refund rule, or EU261 / UK261 |
| Settlements | Open class-action settlements that match your purchases | The official claim link and the proof it asks for |

**ClawBack never sends, cancels, pays, disputes or files anything itself.** It prepares the request. The person
reads it and makes the final click. Letters, and cancellation emails for merchants that take them, can be saved as
drafts in the person's own mailbox, ready to send.

Every finding shows its working: the charges and emails it relied on, the rule behind it, and a link to that rule's
official source. Every step the agent takes is logged with the model it used, the time, the tokens and the cost, and
the dashboard shows that log.

An example, from the demo month:
- "DashPass cost $9.99 this month. One order saved you $2.99. Net, it cost you $7.00."
- "Hulu sent a 'we miss you' email. It still costs $9.99 a month." Help me cancel: one button to the cancel page on
  Hulu's own site, a calendar reminder before the next charge, and a bank check afterwards that the charge stopped.
  Hulu doesn't take cancellations by email, so ClawBack doesn't write one.
- "Best Buy charged $129.99 twice. Your email shows one order." A dispute letter with the deadline, written by
  Nemotron 3 Ultra and saved as a draft.

## How we built it

### The agent workflow

```
bank (Plaid) ─┐
              ├─> rules (code) ─> Nemotron 3.5 Lightning ─> code: usage, value, flags, findings
email (Nylas) ┘                   reads each email once

on a click:  Tavily ─> Nemotron 3 Super ─> Nemotron 3 Ultra ─> code checks ─> a prepared action
             finds     reads plan pages    fits plans to usage,   links and     the person sends it
             pages                         writes letters         numbers
```

1. **Data in.** Plaid Link and `/transactions/sync` pull 180 days of bank transactions. Nylas Hosted OAuth connects
   Gmail, Outlook, Yahoo, iCloud and other inboxes, and reads up to 150 subscription-like messages from 180 days. A
   statement CSV works too.
2. **Rules first.** Code finds recurring charges (steady cadence, steady amount) and matches bills to known
   providers. Sender and keyword rules set aside email that can't matter. Most email stops here, at no model cost.
3. **Lightning reads.** Nemotron 3.5 Lightning reads each email that passes the rules into facts: the kind of
   email, the merchant, an amount, the money a membership saved, an old and new price, the days left in a trial. It
   answers in a strict JSON schema, and each email is read once and cached.
4. **Code decides.** Code turns those facts into usage evidence, membership value, flags and findings. It does
   every date and every dollar, and checks each finding against rules data with official sources (refund windows,
   dispute deadlines, flight rules, fees, settlements).
5. **Super and Ultra judge, on request.** "Find a cheaper option": Tavily searches current plans, Nemotron 3 Super
   reads the pages into a list of plans, and Nemotron 3 Ultra, with thinking on, picks the ones that fit how the
   person uses the service. "Help me cancel": Tavily finds the cancel page, and once code has checked it, it
   becomes the panel's one button. Nemotron 3 Ultra writes the dispute and refund letters, the bill negotiation
   script, and a cancellation email when the merchant's own page says it takes one.
6. **Code checks the output.** Options that don't cite a page Tavily returned are dropped. A cancel page is shown
   only if it is on the merchant's own site. A letter or email is used only if it has no links and no numbers that
   aren't in the facts.
7. **The person acts.** The prepared action is a link, steps, a letter, a script or a draft in the person's
   mailbox. The person sends it.
8. **Every night,** a job syncs each connection, checks the email connection still works, and re-checks prices for
   items still inside a refund window.

### Nemotron on Nebius Token Factory: which tier does what

All model calls go to NVIDIA Nemotron models on Nebius Token Factory, through its OpenAI-compatible API. Each tier
has one job, and the big models run only when a person asks for something.

| Tier | Model | Job | When | $ per 1M tokens in / out |
|---|---|---|---|---|
| fast | `nvidia/Nemotron-3_5-Lightning`, thinking off | Email to facts, strict JSON | Every email that passes the rules, once | 0.06 / 0.24 |
| fast fallback | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | The same, when Lightning fails | Only on failure | 0.06 / 0.24 |
| mid | `nvidia/nemotron-3-super-120b-a12b` | Reads plan and pricing pages into a plan list | "Find a cheaper option" | 0.30 / 0.90 |
| reason | `nvidia/Nemotron-3-Ultra-550b-a55b` | Fits plans to usage (thinking on); writes letters, scripts and cancellation emails | When the person clicks | 1.00 / 3.00 |
| vision | `nvidia/Nemotron-3.5-Super-VL` | Receipts sent as images and PDFs | Planned | 0.30 / 0.90 |

Why this split:
- **Lightning for volume.** Reading email is most of the work, so it goes to the cheapest, fastest tier. Ultra costs
  about 17 times as much per input token and 12.5 times as much per output token.
- **Thinking off on Lightning.** With thinking on, Lightning writes its reasoning into the answer text, which breaks
  strict JSON. The code refuses to turn it on for that tier.
- **Super for long pages.** Plan and pricing pages are long and messy. Super reads them cheaply.
- **Ultra for judgement, on demand.** Matching plans to how someone actually uses a service, and writing a careful
  letter, are where reasoning pays off. Ultra runs only after a click, never on the whole inbox.
- **Every call has a way down.** Lightning falls back to Nano, then to regex rules. Ultra's letters and emails fall
  back to a template. With no key at all, the app still runs on rules.

Prices are from the public Token Factory catalog, checked on 2026-10-22, and live in `backend/clawback/llm.py`. All
five models were called live on 2026-10-22, and every one answered in strict JSON.

### Search with Tavily

Tavily is the agent's only window onto the web. It finds a merchant's current plans and prices, the merchant's own
cancel page (results are cached per merchant), competitor offers for bill negotiation, and current prices for
price-drop checks. Every link a person sees comes from a Tavily result, the official source of a rule, or a short
list of checked pages, never from a model.

### Safeguards

- **Code does the dates and the dollars.** A model reports what an email says ("ends in 3 days"); code turns it into
  a date. Deadlines, totals and savings are never model output.
- **Models can't add links or numbers.** Recommendations must cite a page Tavily returned. A letter or email with
  a link, or with a number that isn't in the facts, is replaced by the template.
- **Email is untrusted.** Email text is wrapped in tags, the model is told to ignore instructions inside it, and an
  injection screen checks it before a model reads it.
- **Zero Data Retention** is on for the team's Token Factory organization, so prompts and answers aren't kept.
- **The person makes the final click.** ClawBack never sends, cancels, pays or files anything.
- **Facts, not email.** The database keeps facts pulled out of email, never email text. Saved bank and email tokens
  are encrypted.
- **Rules with sources.** Only rules rows marked verified can raise a finding, and each finding links to the rule's
  official page.
- **Published gaps.** A build board in the app lists every feature, from planned to tested live, including what
  isn't done.

### The rest of the stack

- Backend: Python, FastAPI, SQLite. It runs on a CPU virtual machine on Nebius AI Cloud, behind Caddy for HTTPS.
- Frontend: Next.js on Vercel.
- Email: Nylas v3, from any provider. Bank: Plaid (Sandbox).
- Each visitor to the demo gets their own session, with no login.

## Cost per 1,000 emails

The cost of watching an inbox is roughly

$$C \approx N\,(c_{rules} + p \cdot c_{Lightning}) + k \cdot c_{Ultra}$$

where $N$ is the number of emails, $p$ is the share that gets past the rules, and $k$ is the number of clicks that
call Ultra. Rules cost nothing. Keeping $p$ small, and Ultra on demand, is what makes it cheap enough to leave on.

Measured on the synthetic test sets (`docs/EVAL.md`):

| | Cost per 1,000 emails |
|---|---|
| ClawBack's whole pipeline: rules, Lightning, receipts and flights (held-out set) | $0.057 |
| The email-reading step alone: rules, then Lightning (main set) | $0.032 |
| Every email to Ultra instead, for comparison (estimated from a 24-email sample) | $1.18, about 37 times the reading step |

- About 9 in 10 test emails reached a model, because the test inboxes are almost all billing mail. A real inbox has
  far more mail that the free rules set aside.
- One "find a cheaper option" click (Tavily, Super, Ultra) cost about $0.004 in a live run on Hulu.

## How we tested it

- **211 synthetic, labelled emails in two sets** (109 and 102), with about six months of matching bank
  transactions each. They are made up and say so; no real person's mail is in them. Each one is labelled with what
  ClawBack should find.
- The second set was written separately and never used to tune the product. On it, with the models on, ClawBack:
  - found **93%** of the subscriptions and bills (**85%** with the right name);
  - caught **79%** of the problems worth flagging, with **1** false alarm;
  - found **all 10** one-time refunds, fees and settlements (every one of the 8 fixed amounts exact), plus 2 false
    findings;
  - ignored both prompt-injection emails.
- The same set measured before our fixes: 68% named right, 57% of problems caught with 4 false alarms, and one
  injection email followed. Both columns are in `docs/EVAL.md`.
- Every failure on the first set is published in `docs/EVAL.md`. What's left is mostly utility bills that vary a lot,
  Apple-billed apps with no receipt in the inbox, newsletters read as usage, and low-confidence flight hints. The
  held-out set's item-by-item failures stay out of the page, so it stays held out.
- 691 offline tests cover every detector, the model fallbacks, the citation and email checks, sessions and storage,
  the webhooks, and the email and bank connections against fake APIs. Live checks call each Nemotron tier on demand.

## Challenges we ran into

- **Lightning with thinking on.** Nemotron 3.5 Lightning writes its reasoning into the answer when thinking is on,
  with no tags, and can use the whole token budget. We found it on the first live call and now keep thinking off on
  that tier, with a guard in code.
- **Probing what Token Factory supports.** Strict JSON schemas and the thinking switch work on all five models, but
  we had to test each one to find out.
- **Rules that are right.** Every store, airline and card has its own window and its own fine print. We turned them
  into rules data with an official source for each row, and kept the date math in code.
- **Not doing the last step.** Cancelling for people would need their passwords and could cancel the wrong thing.
  Preparing the request, and saving it as a draft, keeps the person in control.
- **Real accounts.** Plaid's production access and Gmail's restricted scopes both need reviews that take longer
  than a hackathon, so the demo uses Plaid's test banks and Nylas's Sandbox.

## Accomplishments that we're proud of

- An agent cheap enough to leave on: most email never reaches a model, and Ultra runs only when a person asks.
- No model writes a date, a dollar amount or a link that a person sees.
- Every step is visible, with its model and cost, and every gap is published on the build board.
- It works with no keys at all, on rules and templates, and gets better with each key.

## What we learned

A cheap filter in front of a big model changes what you can afford to build. Running Ultra on every email doesn't
make sense; running it on the few things a person asks about does. The hard part of an agent like this isn't
writing the request. It's being right about whether there is money to claim, which is why the rules, the evidence
and the date math got the most care.

## Limitations

- The demo connects **Plaid's test banks only**. Real banks need Plaid's production approval.
- Email runs on the **Nylas Sandbox**, which allows 5 connected inboxes in total. `[TEAM: say whether judges should
  connect their own inbox, or use the demo month.]`
- The test set is **synthetic**. Real inboxes will be messier.
- Settlement matching is by merchant name, so it can match a settlement about a different product from the same
  company.
- Dispute deadlines are estimated: the card's real statement date isn't known.
- Price-drop checks are simulated in the demo month, and labelled so.
- "Recovered" is what the person says came back. Nothing checks it against the bank yet.
- US-first: US rules, US dollars, English only.

## What's next

- Plaid production and OAuth banks, so real people can connect real accounts.
- Nylas production and Google's verification for Gmail.
- Nemotron 3.5 Super-VL for receipts sent as images and PDFs.
- Checking that a cancelled charge really stopped, from the next statement.
- State auto-renewal rules in requests, such as New York's partial refund after an unconsented price increase.
- A trained email filter, once volume makes it cheaper than Lightning.

## Built with

NVIDIA Nemotron 3.5 Lightning, NVIDIA Nemotron 3 Nano, NVIDIA Nemotron 3 Super, NVIDIA Nemotron 3 Ultra, Nebius
Token Factory, Nebius AI Cloud, Tavily, Nylas, Plaid, Python, FastAPI, SQLite, Next.js, React, TypeScript, Vercel,
Caddy.

## Made during the hackathon

All of ClawBack was written during the submission period. The first commit is from October 22, 2026.

## Feedback on Token Factory, AI Cloud and Nemotron

See `docs/token-factory-feedback.md`.

## Trying the demo

- Open `[DEMO URL]`. There is no login. Each browser gets its own session with a made-up demo month.
- **Connect bank:** pick a test bank in the Plaid window and sign in with `user_good` / `pass_good`.
- **Connect email:** `[TEAM: as decided above.]`
- **Reset demo data** reloads the demo month at any time.
