# Dashboard Declutter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lead the dashboard with a spend donut, cut the page to one nav row and one button per row, and replace the cancel panel with one big button, a calendar reminder and "I cancelled it".

**Architecture:**
- The backend computes the donut groups and trial notes in `/api/summary`, so all money math stays in code.
- The backend picks the cancel panel's one link and the reminder date. Opening the panel no longer marks a subscription as cancelling; a new endpoint does.
- The frontend draws the donut as hand-made SVG, restructures `dashboard/page.tsx`, and rewrites `CancelPanel` in `SubscriptionRow.tsx`.

**Tech Stack:** FastAPI + pytest (backend), Next.js 16 / React 19, no new dependencies (frontend).

**Spec:** `docs/superpowers/specs/2026-10-23-dashboard-declutter-design.md`

## Global Constraints

- Keep `docs/DESIGN.md`'s system: yellow (`--mark`) only on money you can get back, no stat cards, no `A · B · C` middle-dot strings, no tiny uppercase labels, no gradients or shadows.
- No emoji or unicode symbols as icons. Icons only from `frontend/app/components/icons.tsx`.
- No new npm or pip dependencies.
- Links shown to the user come only from the backend's verified sources. Dates and money are computed in code.
- Keep the model trace ("How ClawBack worked this out") on the dashboard, folded.
- Backend tests stay offline (`.venv/bin/python -m pytest -q` from `backend/`).
- There's no frontend test runner. The frontend gate is `npm run build` plus the browser check in Task 6.

## Review Focus

1. **A real-data user with no bills or a single category:** the donut must still draw. One group draws a full ring; no groups means no donut and no crash → test in Task 1 (`test_spend_groups_empty_and_single`) and checked in the browser in Task 6.
2. **A subscription whose saving exceeds its cost:** "could cut" is capped at the monthly cost, so a slice's yellow never overflows → test in Task 1.
3. **A trial that already converted, or has no date:** no trial note, and no reminder before today → tests in Tasks 1 and 2.
4. **A merchant with no verified link at all:** the panel shows no button, not a broken or search link → test in Task 2.
5. **A phone-width screen (375px):** the donut stacks above its table and nothing scrolls sideways → checked in the browser in Task 6.

---

### Task 1: Spend groups and trial notes in `/api/summary`

**Files:**
- Create: `backend/clawback/pipeline/spend.py`
- Modify: `backend/clawback/pipeline/run.py` (`summary()`)
- Test: `backend/tests/test_spend.py`

**Interfaces:**
- Produces:
  - `GROUP_OF: dict[str, str]` maps category to group label:
    - "Home and phone": `internet`, `mobile`, `utility`, `home_security`
    - "Insurance": `insurance`
    - "Software and AI": `software`, `software_creative`, `ai_assistant`, `security_vpn`
    - "Streaming": `video_streaming`, `music`
    - "Cloud storage": `cloud_storage`
    - "Food delivery": `delivery_membership`, `meal_kit`
    - every other category goes to "Other".
  - `could_cut(s: Subscription) -> float`: 0 when `s.status == "kept"`; otherwise `min(best_saving(s), s.monthly_cost)`, rounded to cents.
  - `spend_groups(subs: list[Subscription]) -> list[dict]`. Each group is `{"label": str, "monthly": float, "could_cut": float, "items": [{"id", "merchant", "monthly", "could_cut"}]}`.
    - It counts only paying items (status not `trial` or `cancelled`) with `monthly_cost > 0`.
    - Groups are sorted by `monthly`, largest first, and items within a group the same way.
    - With more than 6 groups, the smallest merge into "Other" until there are 6. "Other" goes last.
  - `trial_notes(subs: list[Subscription], today: date) -> list[dict]`. Each note is `{"id", "merchant", "amount", "starts_on"}`, for subscriptions with `status == "trial"`, a `next_expected` on or after `today`, and an amount above 0.
  - `summary()` gains the keys `"spend_groups"` and `"trials"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_spend.py`. Seed the demo month as `tests/test_pipeline.py` does: `store.reset("test")`, demo transactions and emails for `TODAY = date(2026, 10, 22)`, then `run("test", TODAY)`.

```python
def test_demo_groups_match_month_sentence():
    s = summary("test")
    groups = s["spend_groups"]
    assert [g["label"] for g in groups][:2] == ["Home and phone", "Insurance"]
    assert round(sum(g["monthly"] for g in groups), 2) == s["monthly_total"]
    assert len(groups) <= 6

def test_yellow_plus_trials_equals_potential_savings():
    s = summary("test")
    cut = sum(g["could_cut"] for g in s["spend_groups"]) + sum(t["amount"] for t in s["trials"])
    assert round(cut, 2) == s["potential_monthly_savings"]

def test_trial_note_for_duolingo():
    [t] = summary("test")["trials"]
    assert t["merchant"] == "Super Duolingo" and t["amount"] == 12.99

def test_kept_item_cuts_nothing():
    # mark Hulu kept, re-run: Hulu's could_cut is 0 and the Streaming group's could_cut drops by 9.99

def test_could_cut_capped_at_cost():
    # Subscription(monthly_cost=5, flags=[Flag(monthly_savings=9, ...)]) -> could_cut == 5

def test_more_than_six_groups_merge_into_other():
    # 8 subscriptions in 8 different groups -> 6 groups, last one labelled "Other", totals preserved

def test_spend_groups_empty_and_single():
    assert spend_groups([]) == []
    # one Netflix subscription -> one group "Streaming"
```

(The commented tests are written in full, using `Subscription(...)` and `Flag(...)` from `clawback.models`.)

- [ ] **Step 2: Run them and check they fail.**
  - Run: `cd backend && .venv/bin/python -m pytest tests/test_spend.py -q`
  - Expected: FAIL (`clawback.pipeline.spend` doesn't exist).
- [ ] **Step 3: Implement** `spend.py` as specified, and add the two keys to `summary()`.
- [ ] **Step 4: Run the whole suite.**
  - Run: `.venv/bin/python -m pytest -q`
  - Expected: all pass. If the demo totals don't match, the yellow-plus-trials test is the one that tells you why.
- [ ] **Step 5: Commit** with the message `Spend groups and trial notes in the summary, for the dashboard donut`.

---

### Task 2: Cancel prep picks one link and a reminder date; "I cancelled it" endpoint

**Files:**
- Modify: `backend/clawback/pipeline/cancel.py` (`cancel_prep`)
- Modify: `backend/clawback/main.py` (`prepare_cancel`, new `mark_cancelled`)
- Modify: `backend/tests/test_api.py` (`test_cancel_email_row_survives_rerun` assumes an email is always written)
- Test: `backend/tests/test_cancel_panel.py`

**Interfaces:**
- Produces:
  - `reminder_on(next_charge: date | None, trial: bool, today: date) -> date | None`:
    - `None` if `next_charge` is missing or before `today`;
    - otherwise `max(today, next_charge - timedelta(days=1 if trial else 2))`.
  - `primary_link(links: list[dict], lookup: dict, merchant: str) -> dict | None`. It returns `{"label", "url", "host", "verified": True}`. Only verified links count, in this order:
    1. The first verified link in `links`. The Apple, Google Play, known-URL and bill branches already put theirs first. Skip links whose label starts with "The law:".
    2. `lookup["steps_url"]`, when it is set and on a verified host.
    3. `rules.merchant_site(merchant).help_url`, labelled `f"Open {merchant}'s help page"`.
    4. Otherwise `None`.

    In cases 1 and 2 the label is `f"Cancel on {merchant}"`.
  - The `cancel_prep` response gains:
    - `primary_link`;
    - `reminder_on` (ISO date or null);
    - `how_to: list[str]`, the merchant steps only, without the rights lines and without the "After …, ClawBack checks your bank" line;
    - `rights` (already there);
    - `watch_after` (ISO `next_charge` or null).

    `email` is `None` unless the lookup found a support address. In that case `write_email` is called as today and `email["to"]` is set; with no address, `write_email` is not called. `steps`, `links` and `missing` stay for compatibility.
  - `POST /api/subscriptions/{sub_id}/cancelled` sets `cancel_pending[sub_id] = today`, pops `kept`, runs the pipeline and returns the subscription. `POST .../cancel-prep` no longer touches `cancel_pending` or `kept`, and no longer re-runs the pipeline.

- [ ] **Step 1: Write the failing tests** in `tests/test_cancel_panel.py`:

```python
@pytest.mark.parametrize("next_charge, trial, expected", [
    (date(2026, 11, 19), False, date(2026, 11, 17)),
    (date(2026, 10, 24), True,  date(2026, 10, 23)),
    (date(2026, 10, 24), False, date(2026, 10, 23)),   # charge tomorrow -> remind today
    (date(2026, 10, 20), False, None),                 # already passed
    (None, False, None),
])
def test_reminder_on(next_charge, trial, expected):
    assert reminder_on(next_charge, trial, date(2026, 10, 23)) == expected

def test_primary_link_prefers_verified_link_and_skips_law():
    links = [{"label": "The law: ROSCA", "url": "https://www.ftc.gov/x", "verified": True},
             {"label": "Apple subscriptions page", "url": "https://apps.apple.com/account/subscriptions", "verified": True}]
    assert primary_link(links, {}, "iCloud+")["host"] == "apps.apple.com"

def test_primary_link_falls_back_to_help_page():
    link = primary_link([{"label": "x", "url": "https://evil.example/hulu", "verified": False}], {}, "Hulu")
    assert link["url"] == "https://help.hulu.com/" and link["label"] == "Open Hulu's help page"

def test_primary_link_none_when_nothing_verified():
    assert primary_link([], {}, "Acme Unknown Co") is None

def test_cancel_prep_does_not_mark_cancelling(client_with_demo):
    # POST cancel-prep for Hulu -> subscription status unchanged (not cancel_pending)

def test_cancelled_endpoint_marks_cancelling(client_with_demo):
    # POST /cancelled for Hulu -> status == "cancel_pending"; a kept subscription loses "kept"

def test_no_email_without_support_address(client_with_demo, monkeypatch):
    # cancel_lookup.lookup patched to return a verified page with no support_email -> prep["email"] is None and write_email not called
```

(`client_with_demo` is a fixture: a `TestClient(app)` that seeds the demo, the way `test_api.py` does.)

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement** as specified. Then update `test_cancel_email_row_survives_rerun` so it patches the lookup to return a support address, so Ultra's email is still written and its row still survives the re-run that `/cancelled` triggers.
- [ ] **Step 4: Run the whole suite.** Expected: all pass.
- [ ] **Step 5: Commit** with the message `Cancel prep: one verified link, a reminder date, email only when accepted; add I cancelled it`.

---

### Task 3: Donut at the top of the dashboard

**Files:**
- Create: `frontend/app/components/Donut.tsx`
- Modify: `frontend/app/api.ts` (`Summary` gains `spend_groups` and `trials`; new types `SpendGroup` and `TrialNote`)
- Modify: `frontend/app/dashboard/page.tsx` (replace `<Strip>` and its legend)
- Modify: `frontend/app/dashboard/dashboard.css`

**Interfaces:**
- Consumes: the `spend_groups` and `trials` shapes from Task 1.
- Produces: `<Donut groups={SpendGroup[]} total={number} selected={string | null} onSelect={(label: string | null) => void} />`.

What it draws:
- **Ring:** an SVG with `viewBox="0 0 260 260"`, outer radius 118, inner radius 78. Each group is a keep arc in `var(--keep)` followed by a cut arc in `var(--mark)`, with a 2px `var(--ground)` stroke between arcs. It starts at 12 o'clock and runs clockwise.
- **One group:** two arcs spanning 360°, drawn as two paths split at 180°, so the ring still closes.
- **Centre:** the total as `$503` in Newsreader, "a month" under it, and a highlighter chip `$69 could go` when the cut total is above 0.
- **Table beside the ring:** the columns are Group, A month, Could cut. Could cut is highlighted, or reads "None found". Rows are buttons (`aria-pressed`). Hovering a row or a slice highlights both and shows that group's numbers.
- **Selection:** clicking a slice or a row calls `onSelect(label)`, and clicking the selected one again calls `onSelect(null)`.
- **Under the table:** the trial note sentence, built in the page from `summary.trials[0]`: "Plus a $12.99 Super Duolingo trial that starts charging Oct 24."
- **Selected group's list:** under the donut, the page shows the group's items: merchant, monthly cost, could save (highlighted), and the row's main action. Reuse `PrimaryAction`, exported from `SubscriptionRow.tsx`. A "Show all" quiet button clears the selection.
- **No donut** when there are no groups.
- **Below 760px:** the table stacks under the ring.

- [ ] **Step 1: Implement**, then run `cd frontend && npm run build`. Expected: compiles, and the type check passes.
- [ ] **Step 2: Commit** with the message `Spend donut at the top of the dashboard`.

---

### Task 4: One nav row, a short page, and `/built`

**Files:**
- Modify: `frontend/app/dashboard/page.tsx`, `frontend/app/components/SiteNav.tsx`, `frontend/app/dashboard/dashboard.css`
- Create: `frontend/app/built/page.tsx` (it renders `<SiteNav />`, `<BuildStatus data={features} />` from `GET /api/features`, and the existing "what's missing" list from `GET /api/missing`)

Spec section 2, exactly:
- **Navigation:** `SiteNav` links become Overview, Dashboard, Your data. "What's built" moves to the footer as a link to `/built`.
- **Connect menu:** the dashboard's nav end becomes one `Connect` button that opens a disclosure. It holds the two existing `ConnectButton`s and the upload label. "Sync now" stays next to it when there's real data.
- **Remove** the `.dash-index` block, the 9 jump links and its demo actions.
- **Footer**, in this order:
  - "Prototype. Made-up demo month." or "Your data, kept on this computer."
  - a `/built` link;
  - the demo tag;
  - "Re-run" (demo only);
  - "Reset demo data" or "Switch to demo data";
  - the existing never-sends sentence.
- **Guide:** one line, "This is a made-up month. Click a slice, or open any row with a yellow amount.", plus "Got it". Same storage key and conditions as today.
- **Groups:** "Owed to you", "To decide", "Bills" and "Worth a look" render as today.
- **Everything else:** "Looks fine", "Cancelled" and "Money back" render inside one `<details className="group rest">`. Its summary is built from the counts present, joined with commas, e.g. "Everything else: 2 look fine, 1 cancelled, $16.04 back so far".
- **Remove `<BuildStatus>`** from the dashboard. The model trace stays last, folded.
- **Old links:** `#build-status` links elsewhere go to `/built`, so search with grep.

- [ ] **Step 1: Implement**, then run `npm run build`. Expected: passes.
- [ ] **Step 2: Commit** with the message `One nav row and a shorter dashboard; What's built gets its own page`.

---

### Task 5: One button per row, and the new cancel panel

**Files:**
- Modify: `frontend/app/components/SubscriptionRow.tsx`
- Modify: `frontend/app/api.ts` (`CancelPrep`)
- Modify: `frontend/app/dashboard/page.tsx` (`onCancelled`, which posts `/cancelled`)
- Modify: `frontend/app/dashboard/dashboard.css`
- Create: `frontend/app/ics.ts`

**Interfaces:**
- Consumes: Task 2's response. `CancelPrep` gains:
  - `primary_link: {label, url, host, verified} | null`;
  - `reminder_on: string | null`;
  - `how_to: string[]`;
  - `watch_after: string | null`;
  - and `email` becomes nullable.
- Produces:
  - `calendarFile(p: {title: string; date: string; description: string; url: string | null}) -> string`. It returns an RFC 5545 text, `VCALENDAR` / `VEVENT`:
    - a floating local time, `DTSTART:YYYYMMDDT090000`, with `DURATION:PT15M`;
    - a `UID` of the form `clawback-<id>-<date>@clawback`;
    - commas, semicolons and newlines escaped in text, and lines folded at 75 octets.
  - `downloadCalendar(filename, text)` saves it as a `text/calendar` Blob download.
  - `SubscriptionRow` gains the prop `onCancelled: () => void`.

**Row:**
- `PrimaryAction` never renders the Yes/No check-in. For `unknown_usage` or `needs_checkin` it renders one button, "Did you use it?", which opens the row (calls `onToggle` when the row is closed).
- The check-in pair inside the opened row stays.
- Export `PrimaryAction` for Task 3. Task 3 can ship first with a local copy; if it does, switch it to this export here.

**`CancelPanel` (spec section 4):**
- **Head:**
  - Title: "Cancel {merchant}".
  - The line under it: "Saves $9.99 a month. Next charge Nov 19." For trials: "Ends Oct 24, then $12.99/month."
  - A "Close" quiet button.
- **Primary button:** an `<a className="btn solid big">` to `primary_link.url`, opening in a new tab. Its text is `primary_link.label`. Under it: "Opens {host}."
- **Reminder button,** when `reminder_on` is set: "Remind me on Nov 17", or "Remind me today" when it's today. It downloads `cancel-{merchant}.ics`:
  - title "Cancel {merchant} before {next charge}";
  - the description holds the link and the how-to steps.
- **Fold:** `<details>` "How to cancel on {merchant}" holds the `how_to` list, then the rights line(s) with their source links.
- **Email:** only when `email` is set. One line, "Or email them at {to}. Their help page says they accept it.", then a "Show the email" disclosure holding the letter, Copy and `SaveDraft`.
- **Panel footer:**
  - "Done it?", then "I cancelled it" (solid; calls `onCancelled`, then closes) and "Not yet" (quiet; closes).
  - Under it: "ClawBack then checks your bank after {watch_after} and tells you if {merchant} charged anyway."
- **Missing notes** show as today.

- [ ] **Step 1: Implement**, then run `npm run build`. Expected: passes.
- [ ] **Step 2: Commit** with the message `One button per row, and the one-button cancel panel with a calendar reminder`.

---

### Task 6: Browser check and docs

**Files:**
- Modify: `docs/DESIGN.md` (the donut replaces the spend bar on the dashboard; the one-row nav and Connect menu; the cancel panel; `/built`)
- Modify: `docs/VIDEO.md` (the opening shot is the donut)

- [ ] **Step 1: Start the backend and frontend, and open `/dashboard` at 1280×800.** Expected:
  - The month sentence and donut are above the fold, with $503 in the centre and "$69 could go".
  - The trial note shows Super Duolingo $12.99.
  - Page height is at most about a third of today's 25 screens.
- [ ] **Step 2: Click the "Streaming" slice.** Expected: its list shows Netflix, Spotify and Hulu, and "Show all" clears it.
- [ ] **Step 3: On Hulu, click "Help me cancel".** Expected:
  - one big "Cancel on Hulu", or "Open Hulu's help page";
  - "Opens …";
  - "Remind me on Nov 17";
  - no email (Hulu lists no address);
  - Hulu is NOT marked cancelling yet.
- [ ] **Step 4: Check the reminder file.** Fetch the generated `.ics` text through a JS hook in the page. Expected: it starts with `BEGIN:VCALENDAR`, has `DTSTART:20261117T090000` and ends with `END:VCALENDAR`.
- [ ] **Step 5: Click "I cancelled it".** Expected: Hulu moves to cancelling.
- [ ] **Step 6: Resize to 375px.** Expected: the donut stacks and nothing scrolls sideways.
- [ ] **Step 7: Update the docs.** Run `cd backend && .venv/bin/python -m pytest -q`. Expected: all pass.
- [ ] **Step 8: Commit** with the message `Docs: donut, one-row nav and one-button cancel panel`.
