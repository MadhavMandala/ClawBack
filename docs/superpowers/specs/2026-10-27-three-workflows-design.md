# Three workflows, built all the way: design

Date: 2026-10-27 · Owner: Ishani · Branch: `feat/three-workflows`

## Why

ClawBack shows too many half-built things. For the hackathon (submissions close Fri Oct 30, 10:00 am PT; filming
on Oct 28) it should show **three workflows that each go all the way to a result**. Less is better if the less is
built out more.

1. **A gym membership you don't use:** ClawBack proves you stopped going (from your Google Maps visits), writes the
   cancellation email, and **sends it** after you confirm.
2. **A streaming service you don't use (Hulu):** ClawBack takes you straight to Hulu's own cancel page, reminds you,
   and checks the charge stopped. (Built; keep it.)
3. **A price drop:** a purchase in your bank data (Plaid) and **today's real price** from the store's own site, side
   by side, with the request to get the difference back.

## Decisions (Ishani, 2026-10-27)

- **Sending:** the gym email is sent from the user's own Gmail through Nylas, only after they click "Send" on the
  finished email. The promise changes from "never sends anything" to "never sends anything without your click".
- **Location:** gym visits come from a **Google Maps Timeline export** the user uploads (Google offers no API for
  location history any more). The demo month ships with a made-up Timeline file.
- **Scope:** only the three workflows are visible on the dashboard. Bills, bank fees, flights, duplicate charges and
  settlements are hidden from the dashboard (code and tests kept).
- **UI extras:** add Tailwind v4 and Aceternity's **3D card** for the three workflow cards. No draggable card. The
  Gmail add-on is paused.
- **The gym:** a real chain whose cancellation can be done by email. LA Fitness was only an example; it asks for a
  mailed or in-person form. **Orangetheory** asks for 30 days' written notice, and email to the home studio is the
  usual way (studios vary). Claude's call: Orangetheory Fitness, a studio near South Plainfield NJ.

## 1. Gym workflow (Orangetheory)

**Demo data.** A monthly Orangetheory charge (`ORANGETHEORY FITNESS`, $169.00, six months) and a made-up Timeline
export: regular visits to the studio until about 8 weeks ago, none since. The studio is in the rules data
(`rules/gyms.json`: chain, studio name, address, lat/lng, how to cancel, the studio's email, source URL,
checked_on). Claude's call: the studio's email in the demo data is a team test address, never a real studio.

**Timeline upload.** `POST /api/ingest/timeline` takes the JSON file from Google Maps (Android: Settings > Location
> Timeline > Export; iPhone: Maps > Settings > Personal content > Export Timeline data).
- Parse both shapes: `{"semanticSegments": [...]}` and a bare array. Use `visit.topCandidate.placeLocation.latLng`
  ("40.58°, -74.41°" strings) and the segment's `startTime`/`endTime`. Ignore `rawSignals` and paths.
- Keep only **visits within 150 m of a known gym** for a gym subscription the user has. Discard everything else at
  parse time; never store the whole file or any other place. Store per gym: visit dates only.
- Gym location for real data: `rules/gyms.json` first; else look the club up once (Tavily on the chain's own
  site for the address, then OpenStreetMap Nominatim to geocode it, cached). If no location, say so; no guess.
- Uploading counts as real data (leaves demo mode), like a statement upload.

**Usage and flag.** Visits become a usage signal. Rule: no visit in the last 30 days and fewer than 2 in the last
60 → `unused`, high: "No visits to Orangetheory Edison since Aug 30 (Google Maps). It costs $169.00 a month."
Evidence lists the last visits with dates. Code computes dates and counts; no model.

**Cancel by email.** The cancel panel for this gym:
- says plainly: "Orangetheory asks for 30 days' written notice. Email to your studio is written notice."
- shows the finished email: **to** the studio address from `gyms.json`, subject and body written by Nemotron 3
  Ultra from code-computed facts (name placeholder, last charge, request 30-day notice starts today, ask for written
  confirmation); the existing checks apply (no links, no numbers not in the facts).
- **Send** button → a confirm step ("Send this email from you@gmail.com to studio@…? It can't be unsent.") →
  `POST /api/subscriptions/{id}/send-email` → Nylas `POST /v3/grants/{grant}/messages/send`.
- **Demo safety:** in demo mode, or when the recipient isn't a verified studio address, the email goes to the
  user's own connected address with "[ClawBack test]" in the subject, and the panel says so. Without a connected
  inbox, Send is replaced by "Connect email to send" and "Copy".
- After sending: "Sent Oct 27 from you@gmail.com" with the message id, and the subscription moves to cancelling
  (the bank watch starts), as "I cancelled it" does today.
- Gmail needs the `gmail.send` scope on the Nylas connector (Nylas dashboard; a person adds it). If missing, the
  error says "Reconnect email to allow sending."

## 2. Hulu workflow

Already built: the one-button cancel panel (Hulu's own cancel page, the calendar reminder, "I cancelled it", the bank
watch). Only polish: it becomes one of the three workflow cards.

## 3. Price drop (Best Buy, live price)

**Data.** The purchase is a bank charge (demo: a fake Plaid-style charge `BEST BUY 00012345`; real: a Plaid
transaction) matched to an order email that names the item (demo: a made-up Best Buy order email). Claude's call:
switch the demo item from Target to Best Buy, because Best Buy is the store whose live price check works (Target's
pages give no price).

**Live price.** When keys are set, the demo runs the **real** price check (`tools/prices.py`, Tavily on bestbuy.com +
Lightning + code checks) on the demo item; when it fails or keys are off, it falls back to the simulated price and
says "simulated" in the finding's headline, not only in evidence. The finding shows **what you paid** (date,
amount, the bank line) next to **today's price on bestbuy.com** (with the link and when it was checked), the
difference, and the deadline (Best Buy: 15 days from delivery; code).

**Request.** The existing prepared request (Ultra writes the chat message; Best Buy's own price-match page link).

**Plaid sandbox (optional, for the real-connection path).** A custom sandbox user in the Plaid dashboard with the
same Best Buy charge, so "Connect bank" shows a real Plaid purchase. A person sets it up; the code needs no change.

## 4. Dashboard

- **Top:** the month sentence and the donut stay.
- **Middle:** three **workflow cards** (Aceternity 3D card, hover tilt) instead of the long list: "Stop paying for a
  gym you don't use" (Orangetheory), "Cancel what you don't watch" (Hulu), "Get the price drop back" (Best Buy).
  Each shows the merchant, the one-line finding, the money (yellow only for money back), and one button that opens
  the workflow in the detail pane.
- **Below:** "Everything else" fold keeps the other subscriptions only (no other findings shown).
- **Connect menu:** adds "Upload Google Maps Timeline".
- Tailwind v4 is added only for the 3D card and the cards' layout. Existing CSS stays. The cards follow DESIGN.md
  colors and fonts; the 3D card's shadow is allowed only on hover (a deliberate exception, noted in DESIGN.md). No
  Unsplash images: each card shows the merchant name large instead.

## Goals

- Each of the three workflows runs end to end on the demo month with live models, ready to film.
- The gym email really sends (to the user's own inbox in demo) and the gym moves to cancelling.
- The price drop shows a live Best Buy price when it can, and says "simulated" plainly when it can't.
- The dashboard shows the three workflows first and nothing else competing for attention.

## Non-goals

- Automating cancellation on any website.
- Reading location history any way other than a user's uploaded Timeline export.
- The Gmail add-on, the draggable card, other finding types on the dashboard.

## Anti-goals

- Emailing a real business from the demo.
- Storing a user's full location history or any place other than their gym visits.
- A model computing visit counts, dates or prices.
- Calling a mailed-form gym "cancelled by email".

## Testing

- Backend tests: Timeline parsing (both shapes, degree strings, far-away visits dropped, nothing else stored);
  the visit rule; the gym flag text; send-email (fake Nylas: demo redirects to self, confirm required, missing
  scope message, moves to cancelling); the price-drop finding with a live price and the fallback label; the
  every-day demo test still passes with the new gym and Best Buy item.
- Frontend: `npm run build`; browser check of the three cards and each workflow.
- Live: one real send to the connected inbox; one live Best Buy price check.

## Calls from the builder check (Claude's calls, 2026-10-27)

1. **Send from the demo:** connecting email normally leaves demo mode. Connecting from the gym's Send button uses a
   "send-only" connection: the grant is stored, demo mode and the demo month stay, nothing is synced from the inbox,
   and sends go to the user's own address with "[ClawBack test]". Connecting from the Connect menu works as today.
2. **Timeline:** the demo Timeline is preloaded in the demo month. Uploading a file is the real-data path (leaves
   demo mode).
3. **No drop today:** the demo Best Buy item is one that is on sale at Best Buy now (checked live once while
   building); the demo purchase is at its regular price. If the live price is not below what was paid, the card says
   "No drop today. ClawBack checks every day." instead of disappearing.
4. **Real-data sending:** only to studios listed in `rules/gyms.json` (checked addresses). Any other gym: Copy, and
   "Send to myself".
5. **Live price check:** once a day when the shared demo template is built (prices.py already caches one check per
   item per day); the card shows when it was checked.
6. **Best Buy duplicate:** the demo's duplicate charge moves to another store, so the price-drop purchase is the only
   Best Buy charge in the demo month.

## Left to the builder

The exact Orangetheory studio and price, card copy, Tailwind setup details, file layout.
