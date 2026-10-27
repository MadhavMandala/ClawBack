# Handoff: what's left before submission

Submissions close **Fri Oct 30, 10:00 am PT**. Most urgent first.

## 1. Merge the open PR

- [ ] Review and merge [PR #6](https://github.com/MadhavMandala/ClawBack/pull/6) (`feat/three-workflows`): the
      three-workflow dashboard (gym, Netflix, Best Buy price drop), the landing page rewrite and the new video
      script. Backend tests (820) and the frontend build pass.

## 2. Keys and a public repo (required)

`backend/.env` is committed. Its keys must be treated as leaked once the repo goes public.

- [ ] Rotate every key in it: Nebius, Tavily, Nylas, Plaid.
- [ ] Delete the `!backend/.env` line from `.gitignore`, then run `git rm --cached backend/.env`.
- [ ] Remove the file from history with `git filter-repo`, or publish a fresh repo with squashed history.
- [ ] Make the repo public. Check the MIT license shows in the GitHub About box.
- [ ] Delete the README's last line, "The repo is private for now."

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

- [ ] [WRITEUP.md](WRITEUP.md) (the Devpost text):
  - fill the placeholders: the demo, video and repo links and the `[TEAM: ...]` lines;
  - delete the preamble at the top;
  - add the Google Maps Timeline gym workflow, and say Netflix instead of Hulu;
  - remove "backend running on Nebius AI Cloud" unless the deploy ends up there.
- [ ] [token-factory-feedback.md](token-factory-feedback.md): fill its `[confirm]` items. The feedback is required,
      judged, and counts toward the feedback prize.
- [ ] README: add a "Try it" section at the top with the demo link, and lead with the three workflows.
- [ ] Make the docs agree on the vision model (Nemotron 3.5 Super-VL). Some say "planned", others say "used".

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

- [ ] Run ClawBack once on a teammate's real bank statement CSV and report one real dollar found. This would raise
      the impact score more than anything else.
- [ ] Small leftovers from the review:
  - nothing on the server stops a gym email from being sent twice;
  - the fallback email (when the model is unavailable) doesn't mention the 30-day notice;
  - the price card disappears after you mark it done;
  - the Settings page still says "read-only".
