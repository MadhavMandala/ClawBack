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
  Then it writes the email, the letter or the script. It never sends anything itself."

### 3. A demo month (0:30 to 0:55)

- **Screen:** click **See it on a demo month**. The dashboard opens: the sentence at the top, the spend bar with the
  yellow "could save" part, then **Owed to you**.
- **On-screen text:** "A made-up demo month. Every visitor gets their own."
- **Voice-over:** "Here's a demo month. You pay `[monthly total]` a month for subscriptions and bills. ClawBack
  found `[could save]` a month you could save, and `[owed]` you're owed right now. Yellow means money you can get
  back, and nothing else. Every row shows the charges and emails it relied on."
- **Depends on the merge:** "Every visitor gets their own" needs per-visitor sessions. Without them, drop that
  caption.

### 4. One cancel, start to finish (0:55 to 1:35)

- **Screen:** open the Hulu row ("we miss you" email, $9.99 a month). Click **Help me cancel**.
  - The cancel page appears with a **Checked link** tag. Hover it to show the address is on Hulu's own site.
  - Scroll to the email Nemotron 3 Ultra wrote.
  - Click **Save as draft**.
  - Cut to the test inbox's **Drafts** folder: the email is there, unsent.
- **On-screen text:**
  - "Cancel page found by Tavily, checked to be on the merchant's own site."
  - "Email written by NVIDIA Nemotron 3 Ultra."
  - "Saved as a draft. You press send."
- **Voice-over:** "Hulu sent me a 'we miss you' email, and I'm still paying $9.99 a month. Help me cancel. Tavily
  finds the cancel page, and code checks it's on Hulu's own site before it's shown. Nemotron 3 Ultra, running on
  Nebius Token Factory, writes the email from facts the code worked out. It can't add a link or a number of its
  own. One click saves it as a draft in my own mailbox. I read it, and I press send."
- **Depends on the merge:** the checked cancel page (cancel lookup) and **Save as draft** (Nylas drafts). Until they
  land, the panel shows "Unchecked" links and no draft button; don't record this shot before then.

### 5. Money owed: a refund letter (1:35 to 1:55)

- **Screen:** under **Owed to you**, open the Best Buy row: $129.99 charged twice on one day, and one order email.
  Click **Dispute it**. The dispute letter appears with its deadline and the **Read the rule** link.
- **On-screen text:** "Charged twice. One order. A dispute letter with the deadline."
- **Voice-over:** "Best Buy charged me $129.99 twice, and my email shows one order. ClawBack writes the dispute
  letter, cites the federal rule for card billing errors, and gives the deadline. Code does every date and every
  dollar. The model never does."
- **Alternative:** the overdraft fee row ($35.00), **Ask for it back**, and its reversal request. Same length.

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

- **Screen:** **What's built** on the dashboard: the board with its four phases. Pan across, pause on a few rows in
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
| 3. A demo month | 0:25 |
| 4. One cancel | 0:40 |
| 5. A refund letter | 0:20 |
| 6. Models and cost | 0:25 |
| 7. What's built | 0:12 |
| 8. The close | 0:13 |
| **Total** | **2:45** |

If the edit runs long, shorten shot 3 first, then shot 7. Keep shots 1, 4 and 6: they carry the "aha", the agent
working end to end, and the Nemotron tiers.
