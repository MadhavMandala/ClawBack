# Demo video script

Shot-by-shot script for the submission video. Target length 2:40, hard limit under 3:00. The voice-over is about
400 words, which fits at 150 words a minute.

**The pitch in one line:** your bank, your inbox and your Google Maps Timeline already show where money slips away.
ClawBack reads them, finds three kinds of it, and does the next step for you. You make the final click.

## Before recording

- Record on the hosted demo so the address bar shows the real URL. Use a fresh browser profile at 1920x1080, zoom
  110%, with no bookmarks bar and no other tabs.
- Open the dashboard once to start a session, then click **Reset demo data** in the footer.
- Connect a test Gmail inbox for sending: open the gym card, click **Connect email to send**, sign in. The demo
  month stays. Never show anyone's real mail.
- Warm the model-backed steps once, then reset: open the gym email, click **Claim the difference** on the price
  card, and click **Find a cheaper option** on Spotify. That last click puts Nemotron 3 Super and Ultra rows in
  the trace for shot 7.
- Check the price card. Its price is live from bestbuy.com. If it shows "simulated" or the drop is gone, film
  another day or say so in the voice-over.
- Merchant names (the gym chain, the streaming service, the store) appear only as data on screen. The voice-over
  says "my gym" and "the store", and the video shows no company logos. No copyrighted music.
- Say "NVIDIA Nemotron" and "Nebius Token Factory" out loud, clearly.

Values in `[brackets]` depend on the day the demo month is built (it is dated from today). Read them off the
screen.

## Shots

### 1. The hook (0:00 to 0:12)

- **Screen:** the dashboard, zoomed on the gym card: $169.00 a month, "no visits to Orangetheory Edison since
  [Aug 26] (Google Maps)".
- **On-screen text:** "$169 a month. No visits since August."
- **Voice-over:** "I pay my gym $169 a month. My Google Maps Timeline says I haven't been since August. I didn't
  notice. ClawBack did."

### 2. What ClawBack is (0:12 to 0:27)

- **Screen:** the front page. The highlighter runs down the statement: the gym line, the streaming line, the store
  purchase, then the Google Maps Timeline box. Slow scroll to "Three jobs, done start to finish."
- **On-screen text:** "Your bank, your email, your Google Maps Timeline."
- **Voice-over:** "ClawBack reads your bank, your email and your Google Maps Timeline. It looks for a gym you
  stopped going to, streaming you don't watch, and a purchase that got cheaper. Then it does the next step for
  you."

### 3. A demo month (0:27 to 0:37)

- **Screen:** click **See it on a demo month**. The dashboard opens on the sentence and the donut, with the three
  cards beside it.
- **On-screen text:** "A made-up month. Every visitor gets their own copy."
- **Voice-over:** "This is a made-up demo month: $672 a month in charges, and about $259 of it could go. The three
  cards are the three jobs."

### 4. The gym: proof, the email, sent (0:37 to 1:15)

- **Screen:**
  - The gym card is already open on the right: the visit dates from Google Maps, three a week, then none.
  - Click **Write and send the email**. The email appears with the tag "Written by Nemotron 3 Ultra": 30 days'
    notice, the price, the next charge date.
  - Point at the line "Demo: Send delivers this to your own inbox, not to the studio." Click **Send**, then
    **Yes, send it**.
  - Cut to the test inbox: the email has arrived, its subject starting "[ClawBack test]". Back in ClawBack, the
    line "Sent to ... ClawBack now watches your bank for the next charge."
- **On-screen text:** "From the Timeline, ClawBack keeps only gym visit dates." then "Sent from your own inbox, only
  when you click Send."
- **Voice-over:** "Here's the gym. ClawBack matched the charge to the studio and counted my visits there: three a
  week, then nothing. From the Timeline it keeps only those dates. The studio wants 30 days' written notice, so
  NVIDIA Nemotron 3 Ultra writes the email from facts the code worked out: the price, the next charge date and
  today's date. Nothing goes out until I click Send, and in the demo it comes to my own inbox, so we never email
  a real business. There it is. Now ClawBack watches my bank to make sure the next charge doesn't come."

### 5. Streaming (1:15 to 1:30)

- **Screen:** the streaming card, **Cancel on Netflix**. The panel shows **Cancel on Netflix** (opens
  netflix.com/cancelplan) and **Remind me on [Nov 3]**. In the evidence: the price went from $15.49 to $17.99, and
  the "we miss you" email. Click the cancel button: the service's sign-in page opens, which leads straight to its
  cancel page.
- **On-screen text:** "The service's own cancel page, one click away."
- **Voice-over:** "Next, streaming. The price went up in September, then the service emailed me 'we miss you.'
  It doesn't cancel by email, so ClawBack opens its own cancel page and reminds me before the next charge."

### 6. The price drop (1:30 to 1:55)

- **Screen:** the price card, **See the purchase and ask**. Three boxes: "You paid $249.00", "Today [$164.99] on
  bestbuy.com, checked [Oct 28]", "Difference [$84.01] by [Nov 5]". Click **Claim the difference**. The message
  Nemotron 3 Ultra wrote appears at the top of the pane, with the phone script below it.
- **On-screen text:** "Today's price, read from the store's own site."
- **Voice-over:** "And these earbuds. I paid $249 last week. ClawBack searched the store's own site with Tavily and
  found them at [$164.99] today. Code checks that the price is written on that page before it counts. The store
  adjusts prices for 15 days, so Nemotron 3 Ultra writes the message: [$84.01] back, before [November 5th]."

### 7. Which model does what, and what it cost (1:55 to 2:22)

- **Screen:** open **How ClawBack worked this out** at the bottom of the dashboard. Pan down the rows: rules first,
  then Nemotron 3.5 Lightning reading emails, then the Tavily, Super and Ultra rows from the clicks. Zoom on the
  tier, tokens and cost columns, then on the total in the header.
- **On-screen text:** "Lightning reads. Super reads plan pages. Ultra writes, only when you click." then "Nebius
  Token Factory, Zero Data Retention on." then "About 6 cents per 1,000 emails (held-out test inbox)."
- **Voice-over:** "Every step is logged. Rules run on everything first. Nemotron 3.5 Lightning reads the emails that
  matter into plain facts, Nemotron 3 Super reads plan pages, and Ultra runs only when you click. All of it runs on
  Nebius Token Factory with Zero Data Retention. If a model fails, the next tier takes over, then plain code. On our
  held-out test inbox, reading a thousand emails cost about six cents."
- **Source:** $0.057 per 1,000 emails, held-out set with models on, in `docs/EVAL.md`.

### 8. The close (2:22 to 2:40)

- **Screen:** the front page's closing line, "See what a month looks like with the highlighter on." Then an end card
  with the demo URL and the repo URL.
- **On-screen text:** "Held-out test set: 79% of problems flagged, 1 false alarm." then "NVIDIA Nemotron on Nebius
  Token Factory. Tavily search. Nylas email. Plaid banks." then the two URLs.
- **Voice-over:** "ClawBack is for anyone paying for things they've stopped using, who doesn't have an evening to
  read every statement. It finds the money, shows its proof, and leaves the last click to you. Built on NVIDIA
  Nemotron and Nebius Token Factory."

## Timing check

| Shot | Length |
|---|---|
| 1. The hook | 0:12 |
| 2. What ClawBack is | 0:15 |
| 3. A demo month | 0:10 |
| 4. The gym | 0:38 |
| 5. Streaming | 0:15 |
| 6. The price drop | 0:25 |
| 7. Models and cost | 0:27 |
| 8. The close | 0:18 |
| **Total** | **2:40** |

If the edit runs long, trim shot 3 first, then the pan in shot 7. Keep shots 1, 4 and 7 whole: the hook, the agent
finishing a job end to end, and the Nemotron tiers on Token Factory.

## If something goes wrong on the day

- **Send fails with "Reconnect email to allow sending":** click **Reconnect email** and sign in again, then send.
- **The dashboard is blank:** the server is waking up. Wait for "Loading your month" to clear, or reload after a
  minute.
- **The price card shows a simulated price:** the live search missed. Reload after ten minutes; ClawBack retries.
