# Demo video script

A shot-by-shot script for the submission video. Target length: **2:45**, hard limit under 3:00.

**The pitch in one line:** your bank statement and your inbox already show where money slips away. ClawBack reads
both, finds it, and writes the request to get it back. You make the final click.

## Before recording

- Record on the **hosted** demo, so the address bar shows the real demo URL. Use a fresh browser profile at
  1920×1080, zoom 110%, with no bookmarks bar and no other tabs.
- Click **Reset demo data** first, so the month is the standard demo month.
- For the cancel and draft shots, connect a **test inbox** made for the demo. Never show anyone's real mail.
- Press each model-backed button once before recording, then reset. That warms the caches, and the cost figures
  on screen are real.
- No music under copyright. Use no music, or a track with a licence that allows it. Show no company logos:
  merchant names appear only as statement text.
- Say "NVIDIA Nemotron" and "Nebius Token Factory" out loud, clearly, at least twice.
- Read the voice-over slowly. About 150 words a minute fits the timings below.

Numbers in `[brackets]` come from the screen or from `docs/EVAL.md` on the day. Read what the screen shows; never
round up.

## Shots

### 1. The hook (0:00 to 0:12)

- **Screen:** the dashboard, scrolled to the DoorDash DashPass row, opened. The evidence shows one order this month
  and $2.99 saved, against the $9.99 fee.
- **On-screen text:** "DashPass cost $9.99. It saved $2.99."
- **Voice-over:** "Last month DashPass cost me $9.99. It saved me $2.99 on one order. I was paying seven dollars
  a month to lose money. ClawBack noticed. I hadn't."

### 2. What ClawBack is (0:12 to 0:30)

- **Screen:** the front page. The highlighter runs down the statement and the margin notes appear. Slow scroll to
  "Five places money slips away."
- **On-screen text:** "ClawBack reads your bank and your email. It finds the money. You make the final click."
- **Voice-over:** "This is ClawBack. Connect your bank and your email, and it looks for money in five places:
  subscriptions you don't use, bills that crept up, bank fees, refunds you're owed, and class-action settlements.
  Then it writes the email, the letter or the script, and sends only when you click Send."

### 3. A demo month (0:30 to 0:45)

- **Screen:** click **See it on a demo month**. The dashboard opens on the sentence and the spend donut: $672 a month
  in six groups, yellow for what could go. Beside it, three cards that tilt toward the pointer: a gym you don't go
  to, a streaming service you don't watch, and a price drop.
- **On-screen text:** "A made-up demo month. Every visitor gets their own."
- **Voice-over:** "Here's a demo month: $672 a month, and $251 of it could go. ClawBack doesn't show you a list of
  everything. It shows the three things worth doing, and does each one all the way."

### 4. The gym: proof, then the email, sent (0:45 to 1:20)

- **Screen:** the Orangetheory card: "no visits to Orangetheory Edison since Aug 25 (Google Maps)", $169.00 a month.
  Click **Write and send the email**.
  - The pane shows the visits from Google Maps, then the email Nemotron 3 Ultra wrote: 30 days' written notice,
    the price, the next charge date, "Written by Nemotron 3 Ultra".
  - The note: "Demo: Send delivers this to your own inbox, not to the studio." Click **Send**, then **Yes, send it**.
  - Cut to the inbox: the email arrived, subject starting "[ClawBack test]". Back in ClawBack: "Sent ... ClawBack
    now watches your bank for the next charge."
- **On-screen text:** "Proof from your Google Maps Timeline: only gym visit dates are kept." / "Sent from your own
  inbox, only when you click Send."
- **Voice-over:** "I pay Orangetheory $169 a month. My Google Maps Timeline says I haven't been since August.
  ClawBack keeps only those visit dates, nothing else from the file. Orangetheory takes 30 days' written notice by
  email, so Nemotron 3 Ultra writes it from facts the code worked out, and when I click Send, it goes from my own
  inbox. Then ClawBack watches my bank to make sure the charges stop."
- **Before recording:** in the Nylas dashboard, add the `gmail.send` scope to the Google connector; click **Connect
  email to send** once (the demo month stays).

### 5. Hulu, then the price drop (1:20 to 1:55)

- **Screen, Hulu (15 s):** the Hulu card, **Cancel on Hulu**: the panel's one button opens Hulu's own cancel article;
  **Remind me on Nov 17** downloads a calendar event; **I cancelled it**.
- **Screen, Best Buy (20 s):** the price-drop card, **See the purchase and ask**: "You paid $249.00, Oct 21" next to
  "Today $164.99 on bestbuy.com, checked Oct 27", difference $84.01 by Nov 5. Click **Claim the difference**:
  Ultra's chat message appears at the top of the pane.
- **On-screen text:** "Hulu's own cancel page, found and checked." / "Today's price, checked live on bestbuy.com."
- **Voice-over:** "Hulu doesn't take email, so ClawBack takes me to Hulu's own cancel page and reminds me. And these
  AirPods: I paid $249, and Best Buy's own site says $164.99 today. Best Buy matches its own price for 15 days, so
  ClawBack writes the request. Code does every date and dollar; the model writes the words."
- **Note:** the AirPods price is live. If Best Buy's price isn't lower on the day, the card says "No drop today";
  film the day the drop shows, or say the price is simulated (the card labels it).

### 6. Which model does what, and what it cost (1:55 to 2:20)

- **Screen:** open **How it worked** (the trace) at the bottom of the dashboard. Slow pan down the rows: the rules
  rows, the Lightning extraction row, the Super and Ultra rows from the clicks above, and the Tavily rows. Zoom on
  the tier, tokens and cost columns, then on the total.
- **On-screen text:**
  - "Nemotron 3.5 Lightning reads every email. Nemotron 3 Super reads plan pages. Nemotron 3 Ultra judges and writes."
  - "All on Nebius Token Factory, with Zero Data Retention."
  - "About 6 cents per 1,000 emails"
- **Voice-over:** "Every step is logged. Cheap rules run on everything. NVIDIA Nemotron 3.5 Lightning reads the
  emails that matter into plain facts. Nemotron 3 Super reads plan and pricing pages, and Nemotron 3 Ultra only runs
  when you click. All of it runs on Nebius Token Factory, with Zero Data Retention on. On our synthetic test inbox,
  reading a thousand emails cost about six cents."
- **Source:** the cost is the held-out set's whole-pipeline figure in `docs/EVAL.md` ($0.057 per 1,000 emails).

### 7. What's built, and what isn't (2:20 to 2:32)

- **Screen:** **What's built** (the `/built` page, linked from the dashboard footer): the board with its four phases. Pan across, pause on a few rows in
  "Live-tested" and one in "Planned".
- **On-screen text:** "Every feature, and how far along it is. Gaps included."
- **Voice-over:** "We publish what isn't done. This board lists every feature, from planned to tested live."

### 8. The close (2:32 to 2:45)

- **Screen:** back to the front page's closing line, "See what a month looks like with the highlighter on." Then
  the demo URL and the repo URL on a plain end card.
- **On-screen text:**
  - "On a held-out synthetic test set: every refund and fee found, 79% of problems flagged, 1 false alarm."
  - "NVIDIA Nemotron on Nebius Token Factory. Tavily search. Nylas email. Plaid banks."
  - the demo URL and the repo URL.
- **Voice-over:** "ClawBack is for anyone who suspects they're paying for things they don't use, and doesn't have
  an evening to read every statement. It finds the money, writes the request, and leaves the last click to you.
  ClawBack. Built on NVIDIA Nemotron and Nebius Token Factory."
- **Depends on the merge:** the eval caption needs `docs/EVAL.md`.

## What depends on work after the merge

| Shot | Needs |
|---|---|
| 3 | per-visitor sessions (only for the "every visitor" caption) |
| 4 | the cancel-page lookup with the merchant-site check, and Nylas drafts |
| 6 | `docs/EVAL.md` for the cost per 1,000 emails |
| 8 | `docs/EVAL.md` for the catch rate and false alarms |
| all | the hosted demo URL |

Shots 1, 2, 5 and 7 work on today's build.

## Timing check

| Shot | Length |
|---|---|
| 1. The hook | 0:12 |
| 2. What ClawBack is | 0:18 |
| 3. A demo month | 0:15 |
| 4. The gym: proof, email, sent | 0:35 |
| 5. Hulu, then the price drop | 0:35 |
| 6. Models and cost | 0:25 |
| 7. What's built | 0:12 |
| 8. The close | 0:13 |
| **Total** | **2:45** |

If the edit runs long, shorten shot 3 first, then shot 7. Keep shots 1, 4 and 6: they carry the "aha", the agent
working end to end, and the Nemotron tiers.
