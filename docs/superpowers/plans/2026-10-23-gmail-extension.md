# Gmail Add-on Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Decisions (Ishani, 2026-10-23)

1. **An unpacked Chrome extension, pinned to the toolbar.** No bookmarklet.
2. **Personal Gmail.** The teammate has no real Netflix price-change email, so we stage one (see Task 7).
3. **Deep link: scroll to that row and open it.** There's no separate focus panel. `/dashboard?focus=sub:<id>`
   (or `finding:<id>`) scrolls to the existing row and opens it; closing the row leaves the full dashboard.

**Goal:** In the teammate's Gmail inbox, ClawBack puts a small flag on emails that match a finding (for example a
Netflix price rise). Hovering shows one line ("Netflix went from $15.49 to $17.99. You could save $2.50/month.") and
"More info", which opens the dashboard focused on that subscription or finding. Closing the focus shows the rest of
the dashboard.

## Bookmarklet or extension

| | Bookmarklet | Unpacked Chrome extension (Manifest V3) |
|---|---|---|
| Install | Drag a link to the bookmarks bar | `chrome://extensions`, Developer mode, Load unpacked, then pin it |
| Runs in Gmail | Doubtful. Gmail sends a strict CSP (nonce-based `script-src`, `strict-dynamic`, Trusted Types). Chrome checks `javascript:` bookmarks against the page CSP, so the bookmarklet itself or the script it loads is likely refused. Check in Task 0 before trusting either way. | Yes. Content scripts run in an isolated world that the page CSP doesn't apply to. |
| Calls the backend | Page `fetch` is limited by Gmail's `connect-src`, which doesn't list our API. | The extension's service worker fetches with `host_permissions`, outside Gmail's CSP. |
| Survives Gmail's navigation | Must be clicked again after each reload | Runs on every load; a `MutationObserver` reflags rows as Gmail redraws them |
| Hover UI | Possible, if it runs at all | Shadow DOM, so Gmail's CSS can't reach it |
| Size | ~150 lines | ~250 lines plus a manifest, no build step, no dependencies |

**Recommendation: the unpacked Chrome extension.** The bookmarklet's failure mode is "nothing happens on camera",
and the fix for that would be the extension anyway. The extension is plain JS with no bundler, so it still fits in a
day. Ship it as `extension/` in the repo; it never goes to the Chrome Web Store for the demo.

## Architecture

- **Matching by Gmail id.** Each `Fact` is stored under `email_id`, the Nylas message id. For Google grants Nylas v3
  uses Gmail's own hex message id, and its message JSON carries `thread_id`, Gmail's hex thread id. Gmail's inbox
  rows carry the same hex thread id in a `data-legacy-thread-id` attribute (on the subject span), and an open
  message has `data-legacy-message-id`. So the backend returns flags keyed by thread id and message id, and the
  extension marks rows whose attribute matches. No sender, subject or body leaves the backend. Verify the id
  equality in Task 0, because it's the whole design. Fallback if it fails: match on normalised sender domain plus
  received date (both are things the inbox row shows), returned as `match: {sender_domain, date}`.
- **The flags endpoint.** `GET /api/email-flags` builds one flag per email that backs an open finding or a
  subscription with a saving: the price-change fact behind `Subscription.price_change`, fee or duplicate emails behind
  a `Finding`. Each flag has the blurb, the amount, and a dashboard deep link. Blurbs and money are computed in code.
- **Auth: a read-only add-on token, not the session id.** The dashboard's settings page gets "Connect the Gmail
  add-on". It calls `POST /api/addon-token`, which returns a random token scoped to `GET /api/email-flags` only, stored
  hashed with the user id, revoked by `DELETE /api/addon-token` and by "Delete all my data". The page hands it to the
  extension with `window.postMessage`, picked up by a tiny content script that only runs on the ClawBack frontend
  origin. The token lives in `chrome.storage.local`. Gmail's page never sees it, since only the service worker
  sends it.
- **CORS.** The service worker's fetch uses `host_permissions` for the API origin, so it doesn't need CORS. Don't add
  `mail.google.com` to `frontend_origins`. The flags route reads the token from an `X-ClawBack-Addon` header, which
  the existing `allow_headers=["*"]` already permits.
- **Deep link.** `/dashboard?focus=sub:<id>` or `/dashboard?focus=finding:<id>`. Once data loads, the dashboard
  opens that row (sets its open state), scrolls it to the centre, and removes the param with `router.replace` so a
  refresh doesn't jump again. The dashboard already does this for slice clicks (`pick(id)`), so reuse that.

**Tech stack:** FastAPI + pytest (backend), Next.js 16 / React 19 (frontend), plain MV3 JS (extension). No new
dependencies anywhere.

## Global Constraints

- Follow `docs/DESIGN.md`: yellow (`--mark`) only on the money you can get back (the "$2.50/month" in the blurb, not
  the flag or the link). No emoji or unicode symbols as icons; the flag is a drawn SVG (three highlighter strokes,
  as in the app icon). No shadows or gradients, 2-3px radius on the hover card, Schibsted Grotesk, sentence case.
- Read-only. The extension never changes Gmail: no labels, no archive, no sends, no clicks on Gmail controls. It only
  adds its own elements next to rows.
- The extension reads only the thread/message id attributes from Gmail's DOM. It never reads or sends subject,
  sender or body text.
- Never put the session id or the add-on token in a URL. The deep link carries only a finding or subscription id.
- Don't read or print `backend/.env`. No live keys in the extension.
- Don't edit the inside of `frontend/app/dashboard/page.tsx` or `components/SubscriptionRow.tsx` beyond the one
  mount line in Task 5; the other session owns them. Rebase onto its branch before Task 5.
- Backend tests stay offline (`.venv/bin/python -m pytest -q` from `backend/`).

## Review Focus

1. **Gmail ids:** the hex thread id from Nylas matches `data-legacy-thread-id` → checked by hand in Task 0, and a
   test that a Nylas message's `thread_id` survives into the flags (Task 1).
2. **Token scope:** the add-on token opens `/api/email-flags` and nothing else, and the session header never
   accepts it → test in Task 2 (`test_addon_token_cannot_read_summary`).
3. **No email text in a flag:** a flag has no subject, sender or body → test in Task 1.
4. **Kept or cancelled subscriptions, dismissed findings:** no flag → test in Task 1.
5. **Gmail redraws:** flags come back after switching tabs, paging and opening and closing a thread → manual check
   in Task 7.

---

### Task 0: Spike (1 hour, no commits)

- [ ] In the teammate's Gmail, open DevTools on the inbox. Confirm the subject span has `data-legacy-thread-id`
  and note its format (hex, e.g. `18f3a...`).
- [ ] Against the deployed backend with his session, look up the Netflix email's Nylas message id and thread id
  (a temporary log line or the Nylas dashboard; don't print keys). Confirm the thread id equals the attribute.
- [ ] Paste a one-line `javascript:alert(1)` bookmark into Gmail to record whether CSP blocks it, for the writeup.
- [ ] If ids don't match, switch Task 1 to the sender-domain + date fallback before going further.

### Task 1: Thread ids and `GET /api/email-flags`

**Files:**
- Modify: `backend/clawback/models.py` (`Email.thread_id: str | None = None`; `Fact.thread_id: str | None = None`)
- Modify: `backend/clawback/sources/nylas.py` (`_email()`: `thread_id=str(m.get("thread_id") or "") or None`)
- Modify: `backend/clawback/pipeline/extract.py` (copy `email.thread_id` onto each fact)
- Modify: `backend/clawback/demo_data.py` (give the demo Netflix price-change email a fake `thread_id`)
- Create: `backend/clawback/pipeline/email_flags.py`
- Modify: `backend/clawback/main.py` (route)
- Test: `backend/tests/test_email_flags.py`

**Interfaces:**
- `email_flags(user_id: str) -> list[EmailFlag]`, where
  `EmailFlag = {message_id: str, thread_id: str | None, kind: "price_change" | "unused" | "finding", target: "sub:<id>" | "finding:<id>", merchant: str, blurb: str, amount: float, period: "month" | "once", link: str}`.
  - Price change: `"{merchant} went from ${old:.2f} to ${new:.2f}. You could save ${new-old:.2f}/month."`,
    from the fact with `kind == "price_change"` whose merchant matches the subscription.
  - Finding: its `title` and `amount`, for each `evidence` email id the finding records. If findings don't record
    email ids today, add `Finding.email_ids: list[str]` and fill it only where the detector already has the email.
  - `link = f"{settings.frontend_origins[0]}/dashboard?focus={target}"`.
  - Skip subscriptions with status `kept`/`cancelled` and findings with status `dismissed`/`done`.
- `GET /api/email-flags` → `{"flags": [...], "generated_at": iso}`; auth from Task 2.

- [ ] Write the tests first: the demo user returns a Netflix flag with the right blurb and amount; no field holds
  subject, sender or body text; kept subscriptions and dismissed findings give no flag; a Nylas message dict with
  `thread_id` gives an `Email` with it.
- [ ] Implement, then run `cd backend && .venv/bin/python -m pytest -q`.
- [ ] Commit: "Email flags: one flag per email behind a finding, keyed by Gmail ids".

### Task 2: Read-only add-on token

**Files:**
- Modify: `backend/clawback/sessions.py` (`create_addon_token(user_id) -> str`, `resolve_addon(token) -> str`,
  `revoke_addon(user_id)`; stored hashed like session ids; `delete()` also revokes)
- Modify: `backend/clawback/main.py` (`POST /api/addon-token` and `DELETE /api/addon-token` with `current_user`;
  `/api/email-flags` depends on a new `addon_user` dependency that reads `X-ClawBack-Addon`)
- Test: `backend/tests/test_addon_token.py`

- [ ] Tests: token opens `/api/email-flags`; the same token in `X-ClawBack-Session` is rejected on `/api/summary`;
  revoke and delete-my-data both stop it; `CLAWBACK_SESSIONS=single` still works with no token.
- [ ] Implement, run pytest, commit: "Add-on token scoped to email flags".

### Task 3: Extension skeleton

**Files (all new):**
- `extension/manifest.json`: MV3, `name: "ClawBack for Gmail"`, `permissions: ["storage"]`,
  `host_permissions: ["https://mail.google.com/*", "<API origin>/*", "http://localhost:8000/*"]`,
  content scripts `gmail.js` on `https://mail.google.com/*` and `handoff.js` on the frontend origin(s),
  `background.service_worker: "worker.js"`, icons from `frontend/app/icon.svg` exported to PNG.
- `extension/config.js`: `API` and `APP` origins (deployed and localhost).
- `extension/worker.js`: on message `{type: "flags"}`, reads the token from `chrome.storage.local`, fetches
  `/api/email-flags` with `X-ClawBack-Addon`, caches for 60 seconds, replies with the flags (never the token).
- `extension/handoff.js`: listens for `window.postMessage({source: "clawback", type: "addon-token", token})` from
  its own origin only (check `event.origin`), saves the token, posts back `{type: "addon-connected"}`.
- `extension/README.md` is not needed; the install steps go into `README.md` in Task 8.

- [ ] Load unpacked, check the service worker starts with no errors.
- [ ] Commit: "Extension skeleton: worker fetches flags with the add-on token".

### Task 4: Flags and hover card in Gmail

**Files:**
- Create: `extension/gmail.js`, `extension/flag.css` (injected into a shadow root, not the page)

**Behaviour:**
- On load and on each `MutationObserver` batch (debounced 300ms), find `[data-legacy-thread-id]` and
  `[data-legacy-message-id]` elements, look each id up in the flags, and add one host element per row, once
  (mark the row with `data-clawback="1"`).
- The flag: a 16px SVG of three short strokes in `--mark`-free ink colour on a small dark green pill
  (`#07110d` ground, `#e8efe9` ink) placed before the subject. It's not yellow, because it's not money.
- Hover or keyboard focus opens a card (max 280px): merchant in Schibsted Grotesk, the blurb with only the dollar
  saving wrapped in a `--mark` highlight, then "More info" as a plain underlined link to `flag.link` with
  `target="_blank" rel="noopener"`. Closes on mouse leave (150ms delay) and Escape.
- If the worker returns no token: no flags and no errors in the console beyond one `console.info`.

- [ ] Manual check on the teammate's inbox (Task 7 list). Commit: "Gmail flags with a hover card".

### Task 5: Deep link opens the row on the dashboard

**Files:**
- Modify: `frontend/app/dashboard/page.tsx`: after the first load, read `focus` from the URL. For `sub:<id>`, call
  the existing `pick(id)`. For `finding:<id>`, set `findOpen` and scroll to `#finding-<id>`. Then drop the param.
  Land this after the other session's dashboard rework merges, or coordinate with it.
- Modify: `frontend/app/components/FindingRow.tsx`: add `id="finding-<id>"` to the row if it's missing.

**Behaviour:**
- An unknown id shows a short notice ("That item isn't in this session."), and the page loads normally.
- If the item is in a folded group ("Everything else"), that group opens first.
- The browser must already hold the teammate's session in localStorage (he opened the dashboard on this machine
  before), otherwise the link lands on a fresh demo session. See Task 6.

- [ ] `cd frontend && npm run build`. Check `/dashboard?focus=sub:<netflix id>` in the browser at 1280px and
  375px: the Netflix row is open and centred, and closing it shows the full page.
- [ ] Commit: "Dashboard deep links open the item's row".

### Task 6: Connect the add-on from settings

**Files:**
- Modify: `frontend/app/settings/page.tsx`: a "Gmail add-on" row on the connections sheet with "Connect" and
  "Disconnect". Connect calls `POST /api/addon-token` then `window.postMessage({source: "clawback", type:
  "addon-token", token}, location.origin)` and shows "Connected" when the extension answers, or "Install the add-on
  first" after 2 seconds of silence.
- Modify: `frontend/app/api.ts` (`createAddonToken`, `revokeAddonToken`).

- [ ] `npm run build`, then connect in the browser and confirm `chrome.storage.local` holds the token and the page
  doesn't keep it anywhere. Commit: "Connect the Gmail add-on from settings".

### Task 7: Stage the demo and a fallback

- [ ] **The email (staged; he has no real one).** Send it from a team address to his Gmail.
  - Use a clear subject such as "Your Netflix price is changing", and a body stating the old and new price.
  - Nylas picks it up via the webhook. The sender won't be netflix.com, so the merchant must come from the body.
  - The video script says it's a staged email.
  - Never spoof Netflix's From address. Mark it unread just before recording.
- [ ] Run sync on his session and confirm `/api/email-flags` returns the flag for that thread id (worker console).
- [ ] **Fallback if live matching fails on camera:** a `?clawback-demo=1` mode in `gmail.js` that, when no live flag
  matches, flags the first inbox row whose id is listed in `extension/config.js` `DEMO_THREAD_IDS` (filled in
  before recording) with the demo Netflix flag from `/api/email-flags` on the demo session. Also record a clean
  backup take the day before.
- [ ] Manual check list: flag shows on load; after switching Inbox/Promotions tabs; after paging; after opening and
  closing the thread; hover card readable at 100% and 125% zoom; "More info" opens the dashboard with that row open and
  centred; closing the row shows the full dashboard; with the add-on disconnected, no flags.

### Task 8: Docs and privacy

**Files:**
- Modify: `README.md` (install: Load unpacked, pin, connect from settings)
- Modify: `docs/ARCHITECTURE.md` (the add-on, the token, the id matching)
- Modify: `docs/DESIGN.md` ("Pieces added": the Gmail flag and hover card)
- Modify: `docs/PRIVACY.md` and `frontend/app/privacy` (the add-on reads only message and thread ids from the
  Gmail page; it sends nothing to Gmail and changes nothing; flags come from data ClawBack already holds; the token
  only lists flags and can be revoked)

- [ ] Note the Google side honestly: the extension doesn't use Google APIs, so Google's API user-data policy and
  its Workspace review don't apply to it directly; mail access still goes through the existing Nylas grant, which
  stays under those rules. A Chrome Web Store release would need its own privacy disclosure and review.
- [ ] Commit: "Docs: Gmail add-on".

## Verification

- `cd backend && .venv/bin/python -m pytest -q` passes, including the new flag and token tests.
- `cd frontend && npm run build` passes.
- Network tab on Gmail: the only ClawBack request is the worker's `GET /api/email-flags`; no request carries email
  text, and no URL holds a token or session id.
- The Task 7 manual check list passes on the teammate's machine.
