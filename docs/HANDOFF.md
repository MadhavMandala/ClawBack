# Handoff: what's left before submission

Submissions close **Fri Oct 30, 10:00 am PT**. Most urgent first.

## 1. Merge the open PR

- [ ] Review and merge [PR #6](https://github.com/MadhavMandala/ClawBack/pull/6) (`feat/three-workflows`): the
      three-workflow dashboard (gym, Netflix, Best Buy price drop), the landing page rewrite and the new video
      script. Backend tests (820) and the frontend build pass.

## 2. Keys and a public repo (required)

`backend/.env` was committed until Oct 28. Its keys were treated as leaked and replaced (DEPLOY.md section 13).

- [x] Rotate every key in it: Nebius, Tavily, Nylas, Plaid. Still to do: delete the old Tavily key in Ishani's
      Tavily account.
- [x] Delete the `!backend/.env` line from `.gitignore`, then run `git rm --cached backend/.env`.
- [x] Remove the file from history with `git filter-repo`, or publish a fresh repo with squashed history.
- [x] Make the repo public (Oct 28). Check the MIT license shows in the GitHub About box.

## 3. Deploy (a working demo link is required)

- [ ] Follow [DEPLOY.md](DEPLOY.md): backend on Nebius, frontend on Vercel. Set `NEXT_PUBLIC_API_URL` and the
      backend environment variables.
- [ ] In the Nylas dashboard, point the callback and webhook URLs at the hosted address, and check the Google
      connector still has the `gmail.send` scope. Update Plaid's redirect URL if it has one.
- [ ] Test in a fresh browser:
  - the dashboard loads with three cards: Orangetheory, Netflix, Best Buy;
  - **Write and send the email** shows the email Nemotron 3 Ultra wrote;
  - **Cancel on Netflix** opens netflix.com/cancelplan;
  - the price card shows today's live price.
- [ ] The Nylas sandbox allows 5 connected inboxes in total. Decide whether judges should connect email, and say
      so in the write-up.

## 4. Film the video

- [ ] Follow [VIDEO.md](VIDEO.md): 2:40, about 390 words of voice-over, with a "before recording" checklist.
- [ ] Read the bracketed dates off the screen. The demo month is dated from the day you film.
- [ ] Upload to YouTube as public. Keep it under 3:00.

## 5. Write-ups

Done on Oct 28: WRITEUP.md, the README and the feedback doc now describe the three workflows (gym with Google Maps
Timeline, Netflix, Best Buy), the vision model is described the same way everywhere, and the factual `[confirm]`
items are filled. What's left:

- [ ] Paste the demo, video and repo links in for `[DEMO URL]`, `[VIDEO URL]` and `[REPO URL]` (WRITEUP.md, README).
- [ ] Check the hosting line under "The rest of the stack" in WRITEUP.md matches the actual deploy (an Oracle
      Cloud VM since Oct 28; see DEPLOY.md).
- [ ] [token-factory-feedback.md](token-factory-feedback.md): the team's own words for the four opinion items
      (onboarding time, "would we build with it again" twice, whether Ultra's thinking was worth it), and the
      Nebius AI Cloud section (planned, then not used: see DEPLOY.md section 14). The feedback is required,
      judged, and counts toward the feedback prize.

## 6. Devpost form

- [ ] Track: **Best Apps and Agents**.
- [ ] Demo link, public repo link, YouTube link, description, and the Token Factory feedback.
- [ ] ClawBack calls Tavily at runtime, so it qualifies for **Best Use of Tavily**.

## Good to know

- Uploading a Timeline file takes you out of the demo month, and no gym will match afterwards. Don't upload one in
  the demo or the video. The demo month comes with the Timeline already loaded.
- The first visit after a server restart takes a few seconds while the demo month is built. The page shows
  "Loading your month" meanwhile.
- The price drop is checked live on bestbuy.com. If the check fails, the price is labelled "simulated" and ClawBack
  retries after 10 minutes.

## If there's time

- [ ] The Gmail add-on (PR "Gmail add-on"): load `extension/` in Chrome, click **Connect** on the settings page,
      and film a short shot of a Netflix email in Gmail with the ClawBack flag and its hover card, then **More
      info** opening Netflix on the dashboard. It needs a real email from netflix.com, orangetheory.com or bestbuy.com
      in the inbox. Steps are in the README under "Gmail add-on".

- [ ] Run ClawBack once on a teammate's real bank statement CSV and report one real dollar found. This would raise
      the impact score more than anything else.
- [ ] Small leftovers from the review:
  - nothing on the server stops a gym email from being sent twice;
  - the fallback email (when the model is unavailable) doesn't mention the 30-day notice;
  - the price card disappears after you mark it done;
  - the Settings page (connected email) and the privacy page still call email access "read-only", though a
    send-only connection can send the gym email.
