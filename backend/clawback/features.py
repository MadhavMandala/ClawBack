"""Every feature ClawBack planned, built or not, and how far along each one is.

The dashboard's build-status board reads this through GET /api/features. Print it with:

    python -m clawback.features

Phases, lowest first:
  planned  designed or listed (docs/ARCHITECTURE.md, STATUS.md, missing.py), no code yet;
  started  some code exists (a stub, a partial path, a 501 route), but it doesn't work end to end;
  built    works end to end on the demo data and/or against fakes, covered by offline tests, but has never
           run against the real outside service or real user data;
  live     has run against the real outside service (Token Factory, Tavily, Nylas, Plaid) or real data at
           least once, with evidence (noted in a comment above each live feature).

Phases come from the code and tests, not the docs alone. Where a feature sat between two phases it got the lower
one, and `next` says why. Each item in missing.py is linked from exactly one feature (`missing_id`, with its
priority), and a feature whose MISSING item is still open is never `live`. tests/test_features.py checks both,
so the board can't silently drop a gap.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

from .missing import REGISTRY

UPDATED = "2026-10-23"

PHASES: tuple[dict[str, str], ...] = (
    {"id": "planned", "label": "Planned", "description": "Designed or listed; no code yet."},
    {"id": "started", "label": "Started", "description": "Some code exists, but it doesn't work end to end yet."},
    {"id": "built", "label": "Built",
     "description": "Works on demo data and in offline tests; not yet run against the real service."},
    {"id": "live", "label": "Live-tested", "description": "Has run at least once against the real service or real data."},
)
PHASE_IDS = tuple(p["id"] for p in PHASES)

AREAS: tuple[str, ...] = (
    "Data sources",
    "Subscriptions",
    "Bills",
    "Bank charges",
    "Refunds",
    "Settlements",
    "Actions",
    "Models and search",
    "Trust and safety",
    "Accounts and storage",
    "Dashboard",
    "Submission",
)

NOT_STARTED = "not started"
_PRIORITY = {m["id"]: m["priority"] for m in REGISTRY}


@dataclass(frozen=True)
class Feature:
    id: str  # kebab-case, unique
    area: str  # one of AREAS
    name: str  # a few plain words
    phase: str  # one of PHASE_IDS
    summary: str  # one sentence: what it does or will do
    next: str | None  # one sentence: what's left to reach the next phase (None only when nothing is left at live)
    where: str  # repo paths joined by ", ", or "not started"
    missing_id: str | None = None  # the matching missing.py id, when the gap is tracked there
    priority: str | None = field(default=None, init=False)  # P0 / P1 / P2, copied from missing.py

    def __post_init__(self) -> None:
        if self.missing_id:
            object.__setattr__(self, "priority", _PRIORITY.get(self.missing_id))


F = Feature

FEATURES: tuple[Feature, ...] = (
    # --- Data sources ---------------------------------------------------------------------------------
    F("demo-data", "Data sources", "Made-up demo user", "built",
      "Loads six months of fake bank charges and emails, so every check has something to find.",
      "Nothing outside to test: it is the fake data the demo and the judges see.",
      "backend/clawback/demo_data.py, backend/clawback/main.py"),
    F("demo-real-switch", "Data sources", "Demo and real data kept apart", "built",
      "The first real connection drops the demo data, and Reset switches back, so fake and real data never mix.",
      "Run it once with a real email or bank connection.",
      "backend/clawback/store.py, backend/clawback/connect.py"),
    F("bank-connection", "Data sources", "Bank connection (Plaid Link + sync)", "built",
      "Connects a bank through Plaid and pulls 180 days of transactions, including changed and removed ones.",
      "Plaid Sandbox issued a link token; run Link through to a first sync with the user_good test login.",
      "backend/clawback/sources/plaid.py, backend/clawback/connect.py"),
    F("plaid-webhook", "Data sources", "Automatic bank updates", "started",
      "Plaid tells ClawBack when new transactions arrive, so nobody has to press Sync.",
      "The route answers 501; it needs a public URL, Plaid's signature check and a sync on each update.",
      "backend/clawback/sources/plaid.py, backend/clawback/main.py", "plaid-webhook"),
    F("plaid-production", "Data sources", "Real banks through Plaid", "started",
      "Lets people connect real banks, including big banks such as Chase that only connect through their own sign-in page.",
      "The production address is wired; it still needs Plaid's approval, a redirect address in Link and a return page.",
      "backend/clawback/sources/plaid.py, backend/clawback/config.py", "plaid-production"),
    F("email-connection", "Data sources", "Email connection, any provider (Nylas)", "built",
      "One Connect email button signs in to Gmail, Outlook, Yahoo, iCloud or other inboxes and reads 180 days of subscription mail.",
      "The Nylas key, app and callback address are verified; connect one Sandbox inbox end to end.",
      "backend/clawback/sources/nylas.py, backend/clawback/connect.py"),
    F("email-webhooks", "Data sources", "Automatic email updates", "started",
      "Nylas tells ClawBack when new mail arrives, so nobody has to press Sync.",
      "The route answers 501; it needs a public URL, Nylas's signature check and a read of each new message.",
      "backend/clawback/sources/nylas.py, backend/clawback/main.py", "email-webhooks"),
    F("nylas-production", "Data sources", "Email for real users", "planned",
      "A paid Nylas plan, since the free Sandbox allows only 5 inboxes and isn't meant for real users.",
      "Choose a Nylas plan and, for Gmail, either Google's own app review or Nylas's verified Google app.",
      NOT_STARTED, "nylas-production"),
    F("statement-upload", "Data sources", "Bank statement upload (CSV)", "built",
      "Reads a bank statement file, so transactions come in without any bank approval.",
      "Upload one real bank's statement and check that the columns and signs come out right.",
      "backend/clawback/sources/statements.py, backend/clawback/main.py"),
    F("ofx-upload", "Data sources", "OFX bank file upload", "planned",
      "Reads OFX and QFX files, the other common format banks offer for download.",
      "Add an OFX reader next to the CSV one.",
      NOT_STARTED),
    F("forwarding-address", "Data sources", "Forwarding address for receipts", "planned",
      "A ClawBack email address that people forward receipts to when their inbox can't be connected.",
      "Set up a Cloudflare Email Worker that passes forwarded mail into the same checks.",
      NOT_STARTED),
    F("sync-now", "Data sources", "Sync now button", "built",
      "Pulls new mail and transactions from every connected source, then runs every check again.",
      "Run it against a connected Sandbox inbox and bank.",
      "backend/clawback/connect.py, backend/clawback/main.py"),
    F("disconnect", "Data sources", "Disconnect email or bank", "built",
      "Forgets a connection, tells Nylas or Plaid to drop it, and removes that source's data.",
      "Run it once on a real Sandbox connection.",
      "backend/clawback/connect.py"),
    F("grant-check", "Data sources", "Daily email connection check", "planned",
      "Checks every day that the email connection still works, so the hosted demo doesn't break quietly.",
      "Add a scheduled check once the backend is hosted.",
      NOT_STARTED),

    # --- Subscriptions --------------------------------------------------------------------------------
    F("recurring-detection", "Subscriptions", "Find recurring charges", "built",
      "Finds weekly, monthly and yearly charges with a steady amount, and skips groceries, gas and food orders.",
      "Run it on real bank data; a yearly plan needs two charges before it shows up.",
      "backend/clawback/pipeline/recurring.py"),
    F("email-triage", "Subscriptions", "Pick out subscription emails", "built",
      "Keeps only emails from known senders or with words like receipt, trial or renew.",
      "Run it on a real inbox and count what it drops by mistake.",
      "backend/clawback/pipeline/triage.py"),
    F("usage-evidence", "Subscriptions", "Usage evidence from email", "built",
      "Counts order receipts, usage summaries and \"we miss you\" emails to judge whether a service gets used.",
      "Run it on a real inbox to see which usage emails real services send.",
      "backend/clawback/pipeline/usage.py"),
    F("checkins", "Subscriptions", "Used it this month? check-ins", "built",
      "Asks one yes or no question when there's no evidence, remembers the answer, and Keep stops the questions for 90 days.",
      "Try it on real subscriptions once email and bank are connected.",
      "backend/clawback/pipeline/usage.py, backend/clawback/pipeline/flags.py, backend/clawback/main.py"),
    F("flag-unused", "Subscriptions", "Spot unused subscriptions", "built",
      "Flags a subscription that looks unused and shows what it costs each month.",
      "Check the flags on real data for false alarms.",
      "backend/clawback/pipeline/flags.py"),
    F("membership-value", "Subscriptions", "Membership losing money", "built",
      "Adds up what a delivery membership like DashPass saved on each order and compares it with the fee.",
      "Run it on real DoorDash order emails.",
      "backend/clawback/pipeline/value.py, backend/clawback/pipeline/flags.py"),
    F("membership-value-more", "Subscriptions", "Value math for more memberships", "planned",
      "The same saved-versus-paid math for Uber One, Instacart+, Prime and Walmart+.",
      "Estimate savings from order totals and each service's fees for non-members.",
      NOT_STARTED),
    F("flag-overlap", "Subscriptions", "Two plans doing the same job", "built",
      "Flags two paid plans in the same category, such as iCloud+ and Google One storage.",
      "Check it on real data; the list of categories is short.",
      "backend/clawback/pipeline/flags.py, backend/clawback/merchants.py"),
    F("trial-ending", "Subscriptions", "Free trial about to convert", "built",
      "Finds free trials in email before the first charge and warns before they turn into a paid plan.",
      "Run it on real trial emails.",
      "backend/clawback/pipeline/run.py, backend/clawback/pipeline/flags.py"),
    F("price-increase", "Subscriptions", "Subscription price went up", "built",
      "Spots a price change in the charges themselves, such as Netflix going from $15.49 to $17.99.",
      "Run it on real bank data.",
      "backend/clawback/pipeline/recurring.py, backend/clawback/pipeline/flags.py"),
    F("app-store-naming", "Subscriptions", "Name Apple and Google Play charges", "built",
      "Works out which app an APPLE.COM/BILL or GOOGLE * charge is by matching a receipt email with the same amount.",
      "Only the demo's receipts have been matched; the general version for real App Store and Google Play receipts is still missing.",
      "backend/clawback/pipeline/recurring.py, backend/clawback/pipeline/extract.py", "app-store-resolution"),
    F("unknown-charge-naming", "Subscriptions", "Name unknown recurring charges", "planned",
      "Names recurring charges the merchant list doesn't know, like \"SQ *SOME GYM 1234\".",
      "Grow the 9-entry merchant list and add a Nemotron 3.5 Lightning step for the rest.",
      NOT_STARTED),
    F("usage-learning", "Subscriptions", "Learn usage patterns over time", "planned",
      "Adjusts how often to ask and how much to trust each kind of evidence, person by person.",
      "Keep check-in history long enough to learn from, then add the rules that use it.",
      NOT_STARTED, "usage-learning"),
    F("usage-apis", "Subscriptions", "Usage data from service APIs", "planned",
      "Optional links to services that share usage, such as Spotify listening history.",
      "Pick one service and add an opt-in connection.",
      NOT_STARTED, "usage-apis"),
    F("browser-extension", "Subscriptions", "Browser extension for site visits", "planned",
      "Notices which subscribed sites a person actually visits.",
      "Deferred on purpose: it's the best usage signal but the biggest privacy cost.",
      NOT_STARTED, "browser-extension"),

    # --- Bills ----------------------------------------------------------------------------------------
    F("bill-detection", "Bills", "Recognise bills", "built",
      "Matches internet, phone, insurance, utility and gym charges to known providers and lists them as bills.",
      "Run it on real bank data.",
      "backend/clawback/findings/bills.py, backend/clawback/rules/bills.json"),
    F("bill-increase", "Bills", "Bill went up", "built",
      "Flags a bill whose last two charges are 10% or more above the earlier ones, but not normal utility swings.",
      "Run it on real bank data.",
      "backend/clawback/findings/bills.py"),
    F("promo-ending", "Bills", "Promotional rate ending", "built",
      "Reads \"your promotional rate ends\" emails and warns before the bill jumps.",
      "Run it on real provider emails.",
      "backend/clawback/findings/bills.py"),
    F("bill-negotiation", "Bills", "Script to lower a bill", "built",
      "Writes phone talking points and a chat message with the price now and before, plus the provider's own pages.",
      "Run it on a real bill.",
      "backend/clawback/findings/actions.py, backend/clawback/main.py"),
    F("bill-market-rates", "Bills", "Competitor offers for negotiating", "started",
      "Adds current offers from other providers, found with Tavily, to the negotiation script.",
      "The search step is written but has no test with fake results and has never run live.",
      "backend/clawback/findings/actions.py", "bill-market-rates"),

    # --- Bank charges ---------------------------------------------------------------------------------
    F("duplicate-charges", "Bank charges", "Charged twice", "built",
      "Finds the same charge twice within 3 days and writes a dispute letter citing the Fair Credit Billing Act or Regulation E.",
      "Run it on real bank data and receipts.",
      "backend/clawback/findings/charges.py, backend/clawback/findings/actions.py"),
    F("statement-dates", "Bank charges", "Real statement dates for disputes", "planned",
      "Uses the card's real statement date and card type for the 60-day dispute deadline instead of an estimate.",
      "Read statement dates from Plaid Statements or Liabilities.",
      NOT_STARTED, "statement-dates"),
    F("bank-fees", "Bank charges", "Bank fee refund request", "built",
      "Finds overdraft, ATM, foreign transaction and other bank fees and writes a polite one-time refund request.",
      "Run it on real bank data.",
      "backend/clawback/findings/charges.py, backend/clawback/rules/bank_fees.json"),

    # --- Refunds --------------------------------------------------------------------------------------
    F("price-drops", "Refunds", "Store price-drop refunds", "built",
      "Finds items whose price dropped $5 or more at stores that refund the difference, before the store's deadline.",
      "It runs on demo receipts with simulated prices; real use needs the live price check and real receipts.",
      "backend/clawback/findings/refunds.py, backend/clawback/rules/retailers.json"),
    F("live-price-check", "Refunds", "Live current-price checks", "started",
      "Looks up an item's price today on the store's own site with Tavily and Nemotron 3.5 Lightning.",
      "The code is written but has no test with fakes and has never run live.",
      "backend/clawback/tools/prices.py", "live-price-check"),
    F("purchase-extraction", "Refunds", "Model reads receipts and flight emails", "started",
      "Nemotron 3.5 Lightning reads purchases and flight details from real receipt and airline emails.",
      "The calls are written but lack the strict answer format, the Nano backup, fake-model tests and a live run.",
      "backend/clawback/findings/purchases.py, backend/clawback/findings/refunds.py", "purchase-extraction"),
    F("flight-refunds", "Refunds", "Flight refunds (US rule)", "built",
      "Reads airline cancellation and schedule-change emails and asks for a cash refund under the US DOT rule.",
      "Run it on real airline emails.",
      "backend/clawback/findings/refunds.py, backend/clawback/rules/flights.json"),
    F("flight-compensation", "Refunds", "EU and UK flight compensation", "built",
      "Works out EU261 or UK261 compensation from the flight's distance for late-notice cancellations.",
      "Run it on real airline emails; airports outside the built-in list get no distance yet.",
      "backend/clawback/findings/refunds.py, backend/clawback/findings/airports.py"),
    F("flight-status-check", "Refunds", "Check what happened to a flight", "planned",
      "Checks the real arrival delay and its cause with a flight-data service instead of trusting the airline's email.",
      "Pick a flight-data service and add it to the flight check.",
      NOT_STARTED, "flight-status-check"),

    # --- Settlements ----------------------------------------------------------------------------------
    F("settlements", "Settlements", "Class-action settlement matches", "built",
      "Matches charges and emails to verified open settlements and links only to the official claim site.",
      "Run it on real data; matching by merchant name can hit a settlement about a different product.",
      "backend/clawback/findings/settlements.py, backend/clawback/rules/settlements.json"),
    F("settlements-refresh", "Settlements", "Keep the settlement list current", "planned",
      "Adds new settlements and drops ones whose deadline has passed, without a manual re-check.",
      "Choose a source to refresh the list from; it was last checked by hand on 2026-10-22.",
      NOT_STARTED, "settlements-refresh"),

    # --- Actions --------------------------------------------------------------------------------------
    F("cancel-prep", "Actions", "Prepare a cancellation", "built",
      "Gathers the cancel link, the steps and an email; ClawBack never cancels anything itself.",
      "Run it with the Tavily key for a merchant that Apple or Google Play doesn't bill.",
      "backend/clawback/pipeline/cancel.py, backend/clawback/main.py"),
    F("cancel-lookup", "Actions", "Find the real cancel page", "started",
      "Finds the merchant's own cancel page or support email with Tavily and cites it.",
      "Today it shows unchecked search results; it needs a check that the page is the merchant's own, tests and a live run.",
      "backend/clawback/pipeline/cancel.py", "cancel-lookup"),
    F("cancel-email", "Actions", "Cancellation email by Nemotron 3 Ultra", "built",
      "Nemotron 3 Ultra writes a short cancellation email from facts the code worked out, with a template as backup.",
      "Only tested with a fake model; no live run is recorded, so press Prepare cancel once with the Token Factory key.",
      "backend/clawback/pipeline/cancel.py"),
    F("email-drafts", "Actions", "Save the email as a draft", "started",
      "Saves the cancellation email as a draft in the person's own mailbox, so they only press send.",
      "The route answers 501; it needs the Nylas drafts call and permission to write drafts.",
      "backend/clawback/sources/nylas.py, backend/clawback/main.py", "email-drafts"),
    F("find-cheaper", "Actions", "Find a cheaper plan", "built",
      "Tavily finds current plans, Nemotron 3 Super lists them, and Nemotron 3 Ultra picks the ones that fit how the person uses it.",
      "Notes say this chain ran live on 2026-10-22, but missing.py still lists it as open; confirm with one recorded run and close that item.",
      "backend/clawback/pipeline/recommend.py", "alternatives"),
    F("finding-actions", "Actions", "Prepared request for each finding", "built",
      "Every finding comes with the request, letter or script to send, the deadline and the official link.",
      "Check the prepared text on real findings.",
      "backend/clawback/findings/actions.py, backend/clawback/main.py"),
    F("finding-status", "Actions", "Dismiss, done and money recovered", "built",
      "Dismiss a finding or mark it done, and add what came back to a self-reported recovered total.",
      "Run it on real findings; the choices still reset when the server restarts.",
      "backend/clawback/main.py, backend/clawback/pipeline/run.py"),
    F("cancel-confirmation", "Actions", "Check the money came back", "planned",
      "Confirms from bank data that a cancelled charge stopped, or that a refund or settlement payment arrived.",
      "Match the expected credits and missing charges on the next sync.",
      NOT_STARTED, "cancel-confirmation"),
    F("legal-rules", "Actions", "State auto-renewal rules", "planned",
      "Adds state rules to requests, such as New York's partial refund after a price increase nobody agreed to.",
      "Ask for the person's state and turn the research notes into rules data.",
      NOT_STARTED, "legal-rules"),

    # --- Models and search ----------------------------------------------------------------------------
    # Live: `python -m clawback.llm --check` called all five tiers on 2026-10-22 and every one answered in strict
    # JSON (llm.py docstring, docs/token-factory-feedback.md, docs/ARCHITECTURE.md section 8).
    F("model-tiers", "Models and search", "Five Nemotron model tiers", "live",
      "Five Nemotron models on Token Factory, from Nemotron 3.5 Lightning for every email to Nemotron 3 Ultra for reasoning, checked live with one command.",
      None,
      "backend/clawback/llm.py"),
    F("model-fallbacks", "Models and search", "Backup model and code fallbacks", "built",
      "When a model fails, Nemotron 3 Nano or plain code takes over, so the app keeps working.",
      "Seen only with a fake model; the live check calls each tier on its own, so no real fallback is recorded yet.",
      "backend/clawback/llm.py, backend/clawback/pipeline/extract.py"),
    # Live: Ishani's model-tier work on 2026-10-22 ran it in the app on the demo emails. docs/token-factory-feedback.md
    # records 15 emails in ~2.4 s, a grocery receipt mislabelled (fixed with one prompt line) and merchant names
    # coming back as written; commit 59a896e fixed the name mapping after it "broke DashPass value math and the
    # trial card in the live app". tests/test_live.py repeats the check on demand (CLAWBACK_LIVE=1).
    F("email-extraction", "Models and search", "Email facts read by Lightning", "live",
      "Nemotron 3.5 Lightning reads each email once into facts, such as a price change or trial days left, with Nano and rules as backups.",
      "It has only read the demo emails live; run it on a real inbox once Zero Data Retention is on.",
      "backend/clawback/pipeline/extract.py, backend/tests/test_live.py"),
    # Live: a search with the shared team key returned results on 2026-10-22.
    F("tavily-search", "Models and search", "Tavily web search", "live",
      "Searches the web for the plan, cancel-page, bill-offer and store-price checks.",
      "Only search has run live; the page-reading call that price checks use hasn't.",
      "backend/clawback/tools/tavily.py"),
    F("triage-model", "Models and search", "Model check for unknown senders", "planned",
      "Sends emails the keyword rules can't place to Nemotron 3.5 Lightning to decide whether they matter.",
      "Add a Lightning yes or no step after the rules.",
      NOT_STARTED),
    F("email-classifier", "Models and search", "Trained email filter", "planned",
      "A small trained model (ModernBERT) that sorts large volumes of email more cheaply than Lightning.",
      "Only worth it above about 16,000 emails a day; label emails with Nemotron first.",
      NOT_STARTED, "email-classifier"),
    F("pdf-receipts", "Models and search", "Read receipt images and PDFs", "planned",
      "Nemotron 3.5 Super-VL reads receipts sent as PDFs or images.",
      "Turn attachments into page images and send them to the vision tier, which already answers live.",
      NOT_STARTED, "pdf-receipts"),
    F("self-hosted-model", "Models and search", "Host a Nemotron model ourselves", "planned",
      "Runs a Nemotron model on a Nebius endpoint the team hosts, next to the Token Factory calls.",
      "A stretch goal for after Oct 30; the Token Factory calls already meet the hackathon rules.",
      NOT_STARTED),

    # --- Trust and safety -----------------------------------------------------------------------------
    F("zdr", "Trust and safety", "Zero Data Retention turned on", "planned",
      "Stops Token Factory from keeping and logging prompts before any real email is sent to a model.",
      "Switch it on in the Token Factory profile settings.",
      NOT_STARTED, "zdr"),
    F("prompt-injection", "Trust and safety", "Prompt-injection guard", "started",
      "Screens email text for hidden instructions before a model reads it.",
      "Email is cut to 6,000 characters, wrapped in tags and marked untrusted, but nothing screens it yet.",
      "backend/clawback/pipeline/extract.py", "prompt-injection"),
    F("verified-rules", "Trust and safety", "Fact-checked rules with sources", "built",
      "Every refund window, fee, flight and settlement rule cites its official page, and only verified rows raise a finding.",
      "Use it on real bank and email data; rows older than about 3 months need a fresh check.",
      "backend/clawback/rules, backend/clawback/findings/rulebook.py"),
    F("cited-links", "Trust and safety", "Links checked against sources", "built",
      "Links shown to people come only from Tavily results or a short verified list, never from a model.",
      "Tested on fake search results; check it on live ones.",
      "backend/clawback/pipeline/recommend.py, backend/clawback/pipeline/cancel.py"),
    F("token-encryption", "Trust and safety", "Encrypted saved tokens", "planned",
      "Encrypts the saved Plaid token and Nylas grant id, which sit in plain text in a local file today.",
      "Encrypt them, or move them into the database, before any shared deploy.",
      NOT_STARTED, "token-encryption"),
    F("privacy-policy", "Trust and safety", "Privacy policy", "planned",
      "Says what ClawBack reads, that mail passes through Nylas, and that no one's data trains a model.",
      "Write it before real users connect, as Nylas and Google's Gmail rules require.",
      NOT_STARTED),

    # --- Accounts and storage -------------------------------------------------------------------------
    F("database", "Accounts and storage", "Real database (Supabase)", "planned",
      "Keeps each person's data in Supabase Postgres, walled off per person, instead of memory that resets on restart.",
      "Create the tables from the architecture doc and put them behind the current store.",
      NOT_STARTED, "database"),
    F("auth", "Accounts and storage", "Login and user accounts", "planned",
      "Lets each person sign in to their own data; today everyone is one built-in demo user.",
      "Add Supabase Auth and replace the hard-coded user.",
      NOT_STARTED, "auth"),
    F("saved-connections", "Accounts and storage", "Connections survive a restart", "built",
      "Keeps the connected email and bank details in a local file and syncs them again on startup.",
      "Restart once with a real Sandbox connection saved.",
      "backend/clawback/connections.py, backend/clawback/connect.py"),
    F("delete-my-data", "Accounts and storage", "Delete all my data", "planned",
      "Removes everything ClawBack holds about a person in one step.",
      "Needs the database first.",
      NOT_STARTED),

    # --- Dashboard ------------------------------------------------------------------------------------
    F("dashboard", "Dashboard", "Dashboard page", "built",
      "Shows monthly spend, money owed to you, subscriptions and bills in groups, and the action panels.",
      "It runs on demo data; it hasn't shown a real connection yet.",
      "frontend/app/dashboard, backend/clawback/main.py"),
    F("trace", "Dashboard", "Model trace with costs", "built",
      "Logs every step with its model tier, time, tokens and cost, and shows the list on the dashboard.",
      "Run the app with the keys and keep a trace of live calls for the demo video.",
      "backend/clawback/trace.py, frontend/app"),
    F("missing-banner", "Dashboard", "Missing pieces marked in place", "built",
      "Unbuilt routes answer with a MISSING message, and panels tag the part that isn't built, from the same list STATUS.md uses.",
      "Nothing outside to test; the tags go as MISSING items close.",
      "backend/clawback/missing.py, frontend/app/components"),
    F("front-page", "Dashboard", "Front page with a demo month", "built",
      "Explains ClawBack through one demo month of statement lines with notes in the margin, using live numbers from the backend.",
      "Nothing outside to test; it goes public with the demo URL.",
      "frontend/app/page.tsx"),
    F("build-board", "Dashboard", "Build status board", "built",
      "Lists every planned feature and how far along it is, from this list.",
      "Nothing outside to test; move a feature's phase here whenever its evidence changes.",
      "backend/clawback/features.py, backend/clawback/main.py, frontend/app/components/BuildStatus.tsx"),
    F("onboarding", "Dashboard", "Guided first scan", "planned",
      "Walks a new person through connecting their bank and email and running the first scan.",
      "Design it on top of the new dashboard.",
      NOT_STARTED),
    F("recovered-history", "Dashboard", "History of money recovered", "planned",
      "Shows each amount that came back and when.",
      "Needs the database and the check that money came back.",
      NOT_STARTED),
    F("settings-page", "Dashboard", "Settings page", "planned",
      "One place for the person's state, alert choices, disconnecting and deleting data.",
      "Add it once login exists.",
      NOT_STARTED),
    F("notifications", "Dashboard", "Alerts when something is flagged", "planned",
      "Sends an email digest or a push alert when ClawBack finds something.",
      "Pick email or push and add a daily check.",
      NOT_STARTED, "notifications"),

    # --- Submission -----------------------------------------------------------------------------------
    # Live: the model-tiers check and the live extraction runs on 2026-10-22 (see above).
    F("token-factory-runtime", "Submission", "Live Token Factory calls", "live",
      "The app calls NVIDIA Nemotron models on Nebius Token Factory while it runs, as the hackathon requires.",
      "Make sure the hosted demo makes these calls too.",
      "backend/clawback/llm.py, backend/clawback/pipeline/extract.py"),
    F("deploy", "Submission", "Public demo URL", "planned",
      "A public link to the app that keeps working until Dec 15.",
      "Host the frontend on Vercel and the backend somewhere reachable.",
      NOT_STARTED, "deploy"),
    F("judge-login", "Submission", "Judge demo login", "planned",
      "A seeded account judges can open without connecting their own email or bank.",
      "Needs login first, then seed it from the demo data.",
      NOT_STARTED),
    F("license-public", "Submission", "Open-source license and public repo", "planned",
      "An open-source license file and a public repo, both required to submit.",
      "Pick MIT or Apache-2.0, replace the shared test keys, then make the repo public.",
      NOT_STARTED, "license-public"),
    F("readme", "Submission", "README with setup and models", "built",
      "Explains how to run ClawBack and what each Nemotron model does in it.",
      "Add the demo URL and the license once they exist.",
      "README.md"),
    F("demo-video", "Submission", "Demo video under 3 minutes", "planned",
      "A short video that shows the DashPass money-losing card within the first 30 seconds.",
      "Record it once the hosted demo works.",
      NOT_STARTED),
    F("write-up", "Submission", "Write-up and model feedback", "started",
      "The submission write-up, including feedback on Token Factory and the Nemotron models.",
      "Feedback notes are started; finish them and write the project write-up.",
      "docs/token-factory-feedback.md"),
    F("tavily-bonus", "Submission", "Tavily bonus", "built",
      "Uses Tavily for current plans, cancel pages, bill offers and store prices, for the Tavily bonus prize.",
      "Find cheaper is built on it; the cancel page, bill offers and price checks are only started.",
      "backend/clawback/tools/tavily.py, backend/clawback/pipeline/recommend.py"),
    F("eval-set", "Submission", "Labelled test set and results", "planned",
      "Made-up inboxes and bank histories with known answers, to measure subscriptions found, false flags and cost per 1,000 emails.",
      "Build the test set, measure, and publish the failure cases.",
      NOT_STARTED, "eval-set"),
    F("own-accounts-run", "Submission", "Run on our own accounts", "planned",
      "Runs ClawBack on the team's own email and bank to report real money found.",
      "Needs the email and bank connections tested live and Zero Data Retention on.",
      NOT_STARTED),
)


def counts() -> dict[str, int]:
    tally = Counter(f.phase for f in FEATURES)
    return {p: tally.get(p, 0) for p in PHASE_IDS}


def features_payload() -> dict:
    """GET /api/features: the phases (lowest first), the areas in order, every feature, and counts per phase."""
    return {
        "phases": [dict(p) for p in PHASES],
        "areas": list(AREAS),
        "features": [asdict(f) for f in FEATURES],
        "counts": counts(),
        "updated": UPDATED,
    }


def as_markdown() -> str:
    labels = {p["id"]: p["label"] for p in PHASES}
    rows = ["| Area | Feature | Phase | Next |", "|---|---|---|---|"]
    for f in FEATURES:
        rows.append(f"| {f.area} | {f.name} | {labels[f.phase]} | {f.next or ''} |")
    total = ", ".join(f"{labels[p]} {n}" for p, n in counts().items())
    return "\n".join(rows) + f"\n\n{len(FEATURES)} features: {total}."


if __name__ == "__main__":
    print(as_markdown())
