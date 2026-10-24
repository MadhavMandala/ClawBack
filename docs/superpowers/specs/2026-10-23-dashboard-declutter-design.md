# Dashboard declutter and one-button cancel: design

Date: 2026-10-23 · Owner: Ishani · Branch: `feat/dashboard-declutter`

## Why

The hackathon demo video lives or dies in its first seconds on `/dashboard`, and today the page is cluttered.
Measured on the demo month (2026-10-23):
- about 25 screens of scrolling;
- 64 visible buttons;
- two rows of navigation, the second with 9 jump links;
- 8 stacked groups, ending with the 100-item "What's built" board;
- a prototype band and a first-visit guide above the findings.

Ishani wants a judge to see one picture first: **how much they spend on what, and how much of it could be cut**.
Then they open a part of it and get specific about the savings.

The cancel panel has the same problem. It shows four sentences of steps, two "checked links" and a full email
written by Nemotron 3 Ultra, yet most services (Hulu included) don't accept cancellation by email. The useful action
is getting to the merchant's own cancel page fast, and making sure the cancellation sticks.

This is a cleanup, not new features. The next project after this one is hackathon functionality.

## Constraints

- **Keep the existing visual system in `docs/DESIGN.md`:** colours, the three typefaces, no shadows, square
  surfaces with round controls.
  - Yellow (`--mark`) marks only money you can get back.
  - Its "Things to avoid" list still applies: no stat cards, no left-rule cards, no `A · B · C` middle-dot
    strings, no tiny uppercase labels, no gradients.
- **No emojis or unicode symbols as icons anywhere** (Ishani's rule; also in DESIGN.md). Icons come from
  `frontend/app/components/icons.tsx`.
- **No new frontend dependencies.** The donut is hand-drawn SVG, like `Strip.tsx`.
- **Keep the model trace ("How it worked").** It's the judges' proof that Nemotron runs live.
- **The teammate isn't in these files right now** (Ishani, 2026-10-23). The dashboard page and
  `SubscriptionRow.tsx` can be reworked directly. Still tell them when it lands.
- **Deadline:** submissions close Oct 30, 10:00 am PT.

## 1. The donut (top of the dashboard)

Replaces the spend bar (`components/Strip.tsx`) on `/dashboard`. The front page keeps its own visuals.

- **Headline:** the existing month sentence stays as the headline, e.g. "You pay $503.23 a month for 9
  subscriptions and 4 bills. You could save $81.97 a month and claim $615.06 you're owed."
- **Beside it, a donut of monthly spend** split into at most 6 groups. Each group is drawn as two arcs:
  - the part you keep, in `--keep` green;
  - the part you could cut, in `--mark` yellow.

  A 2px `--ground` gap separates arcs.
- **Centre text:** the monthly total ("$503 a month"), and below it the cuttable total in a highlighter chip
  ("$69 could go").
- **Groups:** the display group comes from each subscription's `category`. Group order is by spend, largest first,
  clockwise from 12 o'clock. With demo numbers:
  - Home and phone (internet, mobile, utility): $239.30, could cut $30.00
  - Insurance: $121.00, could cut $19.00
  - Software and AI: $79.99, none found
  - Streaming (video, music): $39.97, could cut $9.99
  - Cloud storage: $12.98, could cut $2.99
  - Food delivery (delivery memberships): $9.99, could cut $7.00
  - Anything that fits none of these goes in "Other". If there would be more than 6 groups, the smallest merge
    into "Other".
- **What counts:** the donut's total equals the month sentence's monthly total (`monthly_total`). Paying items
  only: no trials, no cancelled ones.
  - "Could cut" per item is the item's best flag saving (the same number the "Could save" column shows), capped
    at its monthly cost.
  - Kept items count as 0.
  - Items being cancelled (`cancel_pending`) still count, the same as the sentence does today, until the
    confirmation logic moves them to Cancelled.
  - The donut's yellow total plus any trial-note amounts equals the sentence's `potential_monthly_savings`. For the
    demo month that's $68.98 + $12.99 = $81.97. (Claude's call)
  - All money math stays in code, computed in the backend (`/api/summary` or a small new field) so the numbers
    can't drift from the month sentence.
- **Trial note:** under the donut, one plain line: "Plus a $12.99 Super Duolingo trial that starts charging Oct 24."
  It shows only when a trial is about to convert, and uses the trial's real merchant, price and date.
- **Table beside the donut:** group, a month, could cut. It doubles as the legend and the accessible view.
- **Hover and click:**
  - Hovering a slice or a table row shows that group's name, monthly total and could-cut amount.
  - Clicking a slice or a table row selects that group. A short list opens under the chart: each subscription in
    the group with its monthly cost, could-save amount and its one main action button.
  - Clicking again, or a "Show all" control, clears the selection.
  - Keyboard works the same as mouse.
- **Phone:** the donut sits above the table. Same behaviour.

## 2. Page structure

Top to bottom:

1. **One navigation row:** logo, Dashboard, Your data, and one "Connect" button.
   - "Connect" opens a small menu: Connect email, Connect bank, Upload a statement.
   - The 9 jump links and the second nav row go away.
   - The "Demo data" tag, "Re-run" and "Reset demo data" become one quiet line in the page footer. Keep "Reset
     demo data" reachable: the video needs it.
2. **Month sentence, donut, table and trial note** (section 1).
3. **Alerts band** ("New since you last looked"), only when there are unseen alerts. Unchanged otherwise.
4. **"Owed to you"**, open.
5. **"Subscriptions to decide on"**, open.
6. **"Bills you could lower"**, open.
7. **"Worth a look"**, open.
8. **"Everything else":** one folded line that opens "Looks fine", "Cancelled" and "Money back". Example text:
   "2 look fine, 1 cancelled, $16.04 back so far". Use plain commas, not middle dots.
9. **"How it worked"** (the model trace), folded as today.

Removed from the dashboard:
- **The "What's built" board** (`components/BuildStatus.tsx`) moves to its own page, `/built`, linked from the
  footer. The "Show what's missing" list goes with it.
- **The prototype band** becomes one footer line: "Prototype. Made-up demo month." plus a link to `/built`.
- **The first-visit guide** shrinks to one line under the month sentence, shown once per browser in demo mode:
  "This is a made-up month. Click a slice, or open any row with a yellow amount." With "Got it".

## 3. Rows: one button each

- **One action per row:** each row in the tables keeps exactly one visible button, its main action.
- **Check-ins move inside the opened row,** next to the evidence: "Used it this month? Yes / No" today shows inline
  on rows like Adobe and ChatGPT.
- **The opened row keeps everything else:** evidence, keep, find a cheaper option and the rest, as today.

## 4. Cancel panel: one big button

Replaces the body of the cancel panel (`components/ActionPanel.tsx` and the cancel branch in the dashboard).
Mockups are in `.superpowers/brainstorm/` (local only, `cancel-panel-v2.html`).

The panel shows:
- **Title and saving:** "Cancel Hulu". "Saves $9.99 a month. Next charge Nov 19."
- **Primary button, "Cancel on Hulu":** opens the best cancel link in a new tab. The best link is the deepest page
  the backend has verified, in this order:
  1. Apple or Google Play subscriptions page, when they bill it;
  2. the merchant's known cancel URL;
  3. the bill rule's cancel or retention page;
  4. the verified cancel lookup result (`steps_url` first, else the verified link).

  5. the merchant's checked help page from `rules/merchant_sites.json` (`help_url`), with the label "Open Hulu's
     help page".

  It never opens an unverified search result. With no link at all, the button is hidden, and the folded steps say
  where to look ("Sign in and look for Account > Subscription"). Tavily runs live in the demo, so option 4 usually
  finds the exact page; the help page is the fallback. (Claude's call)
- **One line under the button:** where it goes, e.g. "Opens hulu.com, where the Cancel button is." Use the link's
  host. Never a model-written URL.
- **Secondary button, "Remind me on Nov 17":** downloads a calendar file (`.ics`) that opens in Google Calendar,
  Apple Calendar and Outlook. The event holds:
  - a title, e.g. "Cancel Hulu before Nov 19";
  - the link and the steps;
  - a time: 9:00 am local on the reminder date, 15 minutes.

  How the reminder date is chosen:
  - Paid subscription: 2 days before the next charge. If that date has already passed, use tomorrow. If the
    charge is tomorrow or today, the button reads "Remind me today".
  - Trial: 1 day before the trial converts.
  - No known next charge: no reminder button.

  The file is built in the browser. No calendar sign-in and no new permissions.
- **Folded "How to cancel on Hulu":** the merchant's own steps only. The rights line (ROSCA or the user's state law)
  goes inside this fold as its last line, with its source link. Drop the "After Nov 19, ClawBack checks…" sentence
  from the steps; it moves below.
- **Email:** shown only when the merchant's own page lists a cancellation address (`email.to` is set).
  - It appears as one line: "Or email them at <address>. Their help page says they accept it." Then "Show the
    email" and "Save to my Drafts".
  - When there's no address, no email is written. Skip the Ultra call, which also saves cost. Letters elsewhere
    still show Ultra's writing.
- **Footer of the panel:** "Done it?" with "I cancelled it" (primary) and "Not yet" (quiet, closes the panel).
  Under it, one line: "ClawBack then checks your bank after Nov 19 and tells you if Hulu charged anyway."
- **Trials:** the row button says "Cancel before Oct 24" as today, the panel says "Ends Oct 24, then $12.99/month",
  and the reminder uses the trial rule.

**Backend change: opening the panel no longer marks a subscription as cancelling.**
- `POST /api/subscriptions/{id}/cancel-prep` returns the preparation only.
- A new `POST /api/subscriptions/{id}/cancelled` records the user's "I cancelled it". It does what cancel-prep does
  today: sets `cancel_pending`, clears `kept`, re-runs the pipeline. The existing confirmation logic (watching for
  the next charge, money back) is unchanged.
- cancel-prep's response gains a `primary_link` field: `{label, url, host, verified}`, picked by the order above. It
  also gains a `reminder_on` date, computed in code, so the frontend doesn't do date math.

## Goals

- A judge on `/dashboard` sees the donut and the month sentence on the first screen, without scrolling, on a laptop.
- The dashboard is at most about a third of today's height for the demo month, with every group except "Everything
  else" and "How it worked" open.
- Every row has one visible button.
- Cancelling Hulu takes one click to reach Hulu's page, with a reminder and "I cancelled it" in the same panel.

## Non-goals

- New findings, data sources or model calls (the next project).
- Changing the colour system, fonts or the front page.
- A Google Calendar connection.
- Automating the cancellation itself on the merchant's site. That would mean storing people's passwords, and the
  team ruled it out.
- A native app.

## Anti-goals

- **Wrong colours:** yellow on anything that isn't money back, or the donut drawn in many category colours. Groups
  are told apart by labels and the table, not hue.
- **Emojis, unicode arrows as icons, stat cards,** or other patterns in DESIGN.md's "Things to avoid".
- **Model-made numbers or links:** a reminder date or donut number computed by a model, or a link that didn't come
  from the backend's verified sources.
- **Lost proof:** losing the model trace, or hiding "Owed to you".
- **Teammate surprises:** a change that rewrites files the teammate is mid-way through without telling them.

## Testing

- **Backend unit tests:**
  - `primary_link` order;
  - `reminder_on` rules (paid, trial, charge tomorrow, already passed, no charge);
  - cancel-prep no longer sets `cancel_pending`;
  - the new `/cancelled` endpoint does;
  - no Ultra email call when there's no support address;
  - the donut's total equals `monthly_total`;
  - the donut's yellow total plus the trial notes equals `potential_monthly_savings`.
- **Frontend:** `npm run build`.
- **Browser check** on the demo month:
  - donut and sentence above the fold at 1280×800;
  - click a slice, and its list opens;
  - Hulu "Help me cancel" opens the new panel;
  - the reminder downloads a valid `.ics`;
  - "I cancelled it" moves Hulu to cancelling;
  - phone width (375px) has no sideways scroll.

## Left to the builder

- The exact category-to-group mapping for categories not in the demo month.
- Component split, e.g. `Donut.tsx` and `CancelPanel.tsx`.
- Hover tooltip styling within DESIGN.md.
- How the "Connect" menu opens (a small popover or a disclosure).
- Whether `/built` reuses `BuildStatus.tsx` as is.

## Also update

- `docs/DESIGN.md`: the donut replaces the spend bar on the dashboard; the one-row nav; the cancel panel; `/built`.
- Note: the cancel panel lives in `CancelPanel` inside `frontend/app/components/SubscriptionRow.tsx`, not
  `ActionPanel.tsx`.
- `docs/VIDEO.md`: the opening shot is the donut.
