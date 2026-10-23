# ClawBack on your phone

ClawBack is a web app today. This plan shows how it becomes a phone app in three stages, and what's already in
place for each. Stage 1 is built; stages 2 and 3 are planned and tracked on the build board under **Phone app**.

## Stage 1: install the web app (built)

ClawBack already installs on a phone's home screen and opens full screen, with its own icon, like an app.

- **Android (Chrome):** the settings page shows an **Install ClawBack** button. Chrome also offers it from its menu.
- **iPhone (Safari):** tap **Share**, then **Add to Home Screen**.

What makes this work:
- `frontend/app/manifest.ts`: the web app manifest, with the name, colours, start page (`/dashboard`), standalone
  display, and shortcuts to "Owed to you", "Money back" and "Your data".
- `frontend/public/icons/` and `frontend/app/apple-icon.png`: icons drawn from the logo, including a maskable
  Android icon. `frontend/app/icon.svg` is the browser tab icon.
- `frontend/app/layout.tsx`: iPhone home-screen settings (`appleWebApp`) and `viewportFit: "cover"`.
- `frontend/app/globals.css`: padding for the notch and the home indicator. The padding is 0 in an ordinary tab.
- `frontend/app/components/InstallApp.tsx`: the install button on Android and the steps on iPhone.
- Every page was checked at phone width (390 px) with no sideways scrolling.

Limits of stage 1:
- **Sessions:** the installed app keeps its own storage on iPhone, so it starts its own session. Connect email
  or the bank there too.
- **No push notifications:** new alerts show when you open the app.
- **No offline mode:** it needs a connection. A service worker could cache the last view; it isn't built.

## Stage 2: a native app (planned)

A React Native app built with **Expo**, in a new `mobile/` folder. It uses the same backend and the same API, and
nothing in the pipeline changes.

### What it reuses as it is

| Piece | Why it already works for a phone app |
|---|---|
| Sessions | The API identifies a visitor by the `X-ClawBack-Session` header, not a cookie. A native app stores the id in the phone's secure storage (`expo-secure-store`) and sends the same header. |
| Every route | Plain JSON over HTTPS: `/api/summary`, `/api/subscriptions`, `/api/findings`, `/api/recovered`, `/api/alerts`, `/api/me` and the actions. |
| Model work | All model calls run on the server through Nebius Token Factory. The app never holds an API key. |
| Delete my data | `DELETE /api/me` already exists. Apple requires in-app account deletion; this covers it. |
| Design | The colour tokens and the three typefaces in `docs/DESIGN.md` carry over. The highlighter still marks only money you can get back. |

### Screens

1. **Your month:** the sentence, the spend bar and the totals (`/api/summary`, `/api/subscriptions`).
2. **To do:** owed money first, then subscriptions to decide on, each with its main action (`/api/findings`, flags).
3. **One subscription or finding:** the evidence, then the cancel steps, the letter and "Save to my Drafts".
4. **Money back:** the confirmed and self-reported history (`/api/recovered`).
5. **Your data:** connections, state, today's model use and delete everything (`/api/me`, `/api/settings`).

### What the backend needs first (not built)

- **Sign-in that returns to the app.**
  - **Email:** today the Nylas callback redirects to the website. A native app opens the sign-in in the system
    browser (`expo-web-browser`), and the backend redirects back to an app link such as `clawback://connected`.
    That needs an allowed list of return targets, so the redirect can't be pointed anywhere else.
  - **Banks:** Plaid Link has a React Native SDK (`react-native-plaid-link-sdk`). It needs an Expo development
    build, not Expo Go. Banks that sign in with OAuth also need `android_package_name` and an iOS `redirect_uri`
    in the link token, but only with Plaid Production.
- **Push notifications.**
  - New routes register a device's Expo push token (`POST /api/devices`) and remove it (`DELETE /api/devices/{id}`).
  - The nightly job and the webhooks already create alerts (`backend/clawback/alerts.py`). They would also send each
    new alert to the user's devices through the Expo push service.
- **Shared types.** `frontend/app/api.ts` copies the backend's models by hand. Generate TypeScript types from
  FastAPI's OpenAPI schema (`openapi-typescript`) into a small shared package that the website and the app both
  import.

## Stage 3: the app stores (planned)

- Production access for email and banks comes first: a paid Nylas plan, Google's review for Gmail's restricted
  scopes, and Plaid Production. See `STATUS.md`.
- The privacy answers: Apple's privacy labels and Google Play's data safety form, filled in from `docs/PRIVACY.md`.
- A finance app gets a closer review. Keep "ClawBack never sends, cancels, pays or files anything on its own"
  visible in the app, as on the website.

## Order of work

1. Stage 1 is done.
2. Generate the shared types, then add the app return link to the email sign-in.
3. Build the Expo app with the five screens, using the demo session.
4. Add the Plaid SDK and push notifications.
5. Store release, after production access.
