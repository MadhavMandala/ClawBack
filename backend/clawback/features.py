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
    "Phone app",
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
      "Loads six months of fake bank charges and emails, so every check has something to find; each visitor gets a copy.",
      "Nothing outside to test: it is the fake data the demo and the judges see.",
      "backend/clawback/demo_data.py, backend/clawback/demo.py"),
    F("demo-real-switch", "Data sources", "Demo and real data kept apart", "built",
      "The first real connection drops the demo data, and Reset switches back, so fake and real data never mix.",
      "Run it once with a real email or bank connection.",
      "backend/clawback/store.py, backend/clawback/connect.py"),
    F("bank-connection", "Data sources", "Bank connection (Plaid Link + sync)", "built",
      "Connects a bank through Plaid and pulls 180 days of transactions, including changed and removed ones.",
      "Plaid Sandbox issued a link token; run Link through to a first sync with the user_good test login.",
      "backend/clawback/sources/plaid.py, backend/clawback/connect.py"),
    F("plaid-webhook", "Data sources", "Automatic bank updates", "built",
      "Plaid tells ClawBack when new transactions arrive, and ClawBack checks Plaid's signature before it syncs.",
      "Set PUBLIC_API_URL on the hosted backend so new Links carry the webhook, then fire a sandbox test webhook.",
      "backend/clawback/sources/plaid.py, backend/clawback/connect.py, backend/clawback/main.py"),
    F("plaid-production", "Data sources", "Real banks through Plaid", "planned",
      "Lets people connect real banks, including big banks such as Chase that only connect through their own sign-in page.",
      "Not planned before Oct 30: the team chose Plaid's test bank on 2026-10-23, and real banks need Plaid's approval.",
      "backend/clawback/config.py", "plaid-production"),
    F("email-connection", "Data sources", "Email connection, any provider (Nylas)", "built",
      "One Connect email button signs in to Gmail, Outlook, Yahoo, iCloud or other inboxes and reads 180 days of subscription mail.",
      "The Nylas key, app and callback address are verified; connect one Sandbox inbox end to end.",
      "backend/clawback/sources/nylas.py, backend/clawback/connect.py"),
    F("email-webhooks", "Data sources", "Automatic email updates", "built",
      "Nylas tells ClawBack when new mail arrives; ClawBack checks the signature and reads just that message.",
      "Create the webhook in Nylas once the backend has a public URL; the challenge and signature checks are tested offline.",
      "backend/clawback/sources/nylas.py, backend/clawback/connect.py, backend/clawback/main.py"),
    F("nylas-production", "Data sources", "Email for real users", "planned",
      "A paid Nylas plan, since the free Sandbox allows only 5 inboxes and isn't meant for real users.",
      "Choose a Nylas plan and, for Gmail, either Google's own app review or Nylas's verified Google app.",
      NOT_STARTED, "nylas-production"),
    F("statement-upload", "Data sources", "Bank statement upload (CSV)", "built",
      "Reads a bank statement file, so transactions come in without any bank approval.",
      "Upload one real bank's statement and check that the columns and signs come out right.",
      "backend/clawback/sources/statements.py, backend/clawback/main.py"),
    F("ofx-upload", "Data sources", "OFX bank file upload", "built",
      "Reads OFX and QFX files, the other common format banks offer, and uploading the same file twice adds nothing.",
      "Upload one real bank's OFX or QFX file.",
      "backend/clawback/sources/statements.py, backend/clawback/main.py"),
    F("forwarding-address", "Data sources", "Forwarding address for receipts", "planned",
      "A ClawBack email address that people forward receipts to when their inbox can't be connected.",
      "Skipped for the hackathon: it needs a Cloudflare domain with Email Routing and a small worker.",
      NOT_STARTED, "forwarding-address"),
    F("sync-now", "Data sources", "Sync now button", "built",
      "Pulls new mail and transactions from every connected source, then runs every check again.",
      "Run it against a connected Sandbox inbox and bank.",
      "backend/clawback/connect.py, backend/clawback/main.py"),
    F("disconnect", "Data sources", "Disconnect email or bank", "built",
      "Forgets a connection, tells Nylas or Plaid to drop it, and removes that source's data.",
      "Run it once on a real Sandbox connection.",
      "backend/clawback/connect.py"),
    F("grant-check", "Data sources", "Nightly email connection check", "built",
      "Checks every night that each email connection still works, and asks for a reconnect when it doesn't.",
      "Run it on the hosted backend's timer; one real call to Nylas with an unknown grant came back as gone, as it should.",
      "backend/clawback/nightly.py, backend/clawback/sources/nylas.py"),
    F("nightly-job", "Data sources", "Nightly sync and re-check job", "built",
      "One job syncs every connected inbox and bank, re-runs the checks and price lookups, and records alerts; it is safe to run twice.",
      "Turn on its systemd timer on the hosted backend (deploy/vm has the unit files).",
      "backend/clawback/nightly.py, deploy/vm"),

    # --- Subscriptions --------------------------------------------------------------------------------
    F("recurring-detection", "Subscriptions", "Find recurring charges", "built",
      "Finds weekly, monthly, quarterly and yearly charges, survives one-off charges and renamed descriptors, and sets aside rent, loans, copays and transfers.",
      "Run it on real bank data.",
      "backend/clawback/pipeline/recurring.py, backend/clawback/pipeline/annual.py, backend/clawback/rules/not_subscriptions.json"),
    F("email-triage", "Subscriptions", "Pick out subscription emails", "built",
      "Keeps emails from known senders or with words like receipt, trial, renew or \"we miss you\".",
      "Run it on a real inbox and count what it drops by mistake.",
      "backend/clawback/pipeline/triage.py"),
    F("usage-evidence", "Subscriptions", "Usage evidence from email", "built",
      "Counts order receipts, usage summaries and \"we miss you\" emails, matched to the right charge even when the names differ a little.",
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
    F("membership-value-more", "Subscriptions", "Value math for more memberships", "built",
      "The same saved-versus-paid math for Uber One, Instacart+, Walmart+, Grubhub+ and Prime, from each service's published fees, and it says so when it can't tell.",
      "Check the order-email patterns against real receipts; no service publishes its receipt wording.",
      "backend/clawback/pipeline/value.py, backend/clawback/rules/memberships.json"),
    F("flag-overlap", "Subscriptions", "Two plans doing the same job", "built",
      "Flags two paid plans in the same category, such as two cloud storage plans or two AI assistants.",
      "Check it on real data.",
      "backend/clawback/pipeline/flags.py, backend/clawback/rules/merchants.json"),
    F("trial-ending", "Subscriptions", "Free trial about to convert", "built",
      "Finds free trials in email, whether they give days left or an end date, and warns before they turn into a paid plan.",
      "Run it on real trial emails.",
      "backend/clawback/pipeline/run.py, backend/clawback/pipeline/flags.py"),
    F("price-increase", "Subscriptions", "Subscription price went up", "built",
      "Spots a price change in the charges themselves, such as Netflix going from $15.49 to $17.99.",
      "Run it on real bank data.",
      "backend/clawback/pipeline/recurring.py, backend/clawback/pipeline/flags.py"),
    F("app-store-naming", "Subscriptions", "Name Apple and Google Play charges", "built",
      "Names each APPLE.COM/BILL and GOOGLE * charge from Apple and Google Play receipt emails, including bundles, tax and several apps in one series.",
      "Check it against a real Apple and Google Play inbox; the Lightning fallback for odd receipt layouts ran live.",
      "backend/clawback/pipeline/store_billing.py, backend/clawback/pipeline/extract.py"),
    # Live: 4 bank descriptors and 1 app category named correctly by Nemotron 3.5 Lightning on 2026-10-23
    # (synthetic descriptors, $0.00012); a cryptic one was kept as written at 0.30 confidence.
    F("unknown-charge-naming", "Subscriptions", "Name unknown recurring charges", "live",
      "A list of 153 US subscriptions and bills names most charges; Nemotron 3.5 Lightning names the rest from the descriptor alone.",
      "Grow the list from real statements; low-confidence names keep the bank's own descriptor.",
      "backend/clawback/merchants.py, backend/clawback/rules/merchants.json, backend/clawback/pipeline/naming.py"),
    F("usage-learning", "Subscriptions", "Learn usage patterns over time", "built",
      "Two \"no\" answers make unused certain, three \"yes\" answers ask less often, and a \"no\" after Keep raises it again.",
      "Watch it over a few months of real check-ins.",
      "backend/clawback/pipeline/usage.py"),
    F("usage-apis", "Subscriptions", "Usage data from service APIs", "planned",
      "Optional links to services that share usage, such as Spotify listening history.",
      "Skipped for the hackathon: it needs an OAuth app registered with each service.",
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
    # Live: Nemotron 3 Ultra wrote the Xfinity talking points on the demo bill on 2026-10-23 and passed the checks.
    F("bill-negotiation", "Bills", "Script to lower a bill", "live",
      "Nemotron 3 Ultra writes phone talking points and a chat message with the price now and before, checked against the facts, with a template as backup.",
      "Run it on a real bill.",
      "backend/clawback/findings/actions.py, backend/clawback/findings/letters.py"),
    # Live: Tavily + Nemotron 3 Super on 2026-10-23 for the demo Xfinity bill kept EarthLink $49.95 and Mint
    # Mobile $30, each priced on the page it cites, and dropped one offer that failed the checks.
    F("bill-market-rates", "Bills", "Competitor offers for negotiating", "live",
      "Adds up to three current offers from other providers, each priced on the page it cites, to the negotiation script.",
      "Prefer pages about the same kind of service; a mobile carrier can still show up on an internet comparison page.",
      "backend/clawback/findings/actions.py"),

    # --- Bank charges ---------------------------------------------------------------------------------
    F("duplicate-charges", "Bank charges", "Charged twice", "built",
      "Finds the same charge twice within 3 days, skips it once the extra charge is refunded, and writes a dispute letter citing the Fair Credit Billing Act or Regulation E.",
      "Run it on real bank data and receipts.",
      "backend/clawback/findings/charges.py, backend/clawback/findings/actions.py"),
    F("statement-dates", "Bank charges", "Real statement dates for disputes", "built",
      "Uses the card's real statement date from Plaid for the 60-day dispute deadline, and falls back to a plain estimate.",
      "Run Link once with the sandbox credit card to read a real statement date.",
      "backend/clawback/findings/charges.py, backend/clawback/sources/plaid.py"),
    F("bank-fees", "Bank charges", "Bank fee refund request", "built",
      "Finds overdraft, ATM, foreign transaction and other bank fees and writes a polite one-time refund request.",
      "Run it on real bank data.",
      "backend/clawback/findings/charges.py, backend/clawback/rules/bank_fees.json"),

    # --- Refunds --------------------------------------------------------------------------------------
    F("price-drops", "Refunds", "Store price-drop refunds", "built",
      "Finds items whose price dropped $5 or more at stores that refund the difference, before the store's deadline.",
      "The demo uses simulated prices; run it on real receipts now that the live price check works for most stores.",
      "backend/clawback/findings/refunds.py, backend/clawback/rules/retailers.json"),
    # Live: on 2026-10-23 a Best Buy search returned $69.99 for the demo MX Master 3S from a bestbuy.com page that
    # passed every check; Target gave no price (it loads prices in the browser), and the check correctly kept none.
    F("live-price-check", "Refunds", "Live current-price checks", "live",
      "Looks up an item's price today on the store's own site with Tavily and Nemotron 3.5 Lightning, and keeps it only if the cited page shows it.",
      "Stores that load prices in the browser, such as Target, give no price yet; they need a product API.",
      "backend/clawback/tools/prices.py"),
    # Live: on 2026-10-23 Lightning read all 10 demo receipts correctly (Target $199.99, Best Buy $129.99, Walmart
    # $89.00) and the United UA 1532 cancellation, for about $0.0004.
    F("purchase-extraction", "Refunds", "Model reads receipts and flight emails", "live",
      "Nemotron 3.5 Lightning reads purchases and flight details in strict JSON, and code keeps a value only if the email writes it.",
      "Run it on a real inbox.",
      "backend/clawback/findings/purchases.py, backend/clawback/findings/refunds.py"),
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
      "Skipped for the hackathon: it needs a paid flight-data API.",
      NOT_STARTED, "flight-status-check"),

    # --- Settlements ----------------------------------------------------------------------------------
    F("settlements", "Settlements", "Class-action settlement matches", "built",
      "Matches a settlement only when a purchase falls in the class period, names the product and fits any state limit, and links only to the official claim site.",
      "Run it on real data.",
      "backend/clawback/findings/settlements.py, backend/clawback/rules/settlements.json"),
    # Live: on 2026-10-23 five Tavily searches plus Nemotron 3 Super ($0.012) found 0 clean candidates and rejected
    # 19 (mostly passed deadlines, one Canadian class), so nothing was added to the list.
    F("settlements-refresh", "Settlements", "Keep the settlement list current", "live",
      "Searches for open US settlements, checks each deadline and claim site, and writes candidates for a person to review.",
      "A person still reviews the candidates; the official-site check rejects some legitimate custom domains.",
      "backend/clawback/findings/settlements_refresh.py, backend/clawback/rules/settlements.json"),

    # --- Actions --------------------------------------------------------------------------------------
    # Live: on 2026-10-23 the Hulu cancel panel on the merged code showed help.hulu.com's own cancel page (checked),
    # the federal auto-renewal line and an email written by Nemotron 3 Ultra.
    F("cancel-prep", "Actions", "Prepare a cancellation", "live",
      "Gathers the merchant's own cancel page, the steps, the person's rights and an email; ClawBack never cancels anything itself.",
      "Run it on a real subscription.",
      "backend/clawback/pipeline/cancel.py, backend/clawback/main.py"),
    # Live: on 2026-10-23 six demo merchants (Netflix, Hulu, Spotify, DashPass, Adobe, ChatGPT Plus) all got a page
    # on their own domain; five also got steps quoted from the page.
    F("cancel-lookup", "Actions", "Find the real cancel page", "live",
      "Tavily finds the merchant's own cancel page, code checks it's on the merchant's domain, and the steps must be quoted from that page.",
      "When a page can't be read (Hulu), fall back to the search snippet for steps.",
      "backend/clawback/pipeline/cancel_lookup.py, backend/clawback/rules/merchant_sites.json"),
    # Live: Nemotron 3 Ultra wrote cancel emails on 2026-10-23 (the per-session cap test on port 8001 and the Hulu
    # panel), and each passed the number and link checks.
    F("cancel-email", "Actions", "Cancellation email by Nemotron 3 Ultra", "live",
      "Nemotron 3 Ultra writes a short cancellation email from facts the code worked out, with a template as backup.",
      "Run it on a real subscription.",
      "backend/clawback/pipeline/cancel.py"),
    F("email-drafts", "Actions", "Save the email as a draft", "built",
      "Saves the cancellation email or a letter as a draft in the person's own mailbox, so they only press send.",
      "Save one draft in a connected Sandbox inbox; Gmail may need the gmail.compose scope on the Nylas connector.",
      "backend/clawback/drafts.py, backend/clawback/sources/nylas.py, backend/clawback/main.py"),
    # Live: on 2026-10-23 Tavily, Nemotron 3 Super and Nemotron 3 Ultra (thinking on) ran on the demo Hulu
    # subscription for about $0.004, and every option cited a returned page.
    F("find-cheaper", "Actions", "Find a cheaper plan", "live",
      "Tavily finds current plans, Nemotron 3 Super lists them, and Nemotron 3 Ultra picks the ones that fit how the person uses it.",
      "Rank the merchant's own plan pages first; an option can still cite a weak news page.",
      "backend/clawback/pipeline/recommend.py"),
    F("finding-actions", "Actions", "Prepared request for each finding", "built",
      "Every finding comes with the request, letter or script to send, the deadline and the official link.",
      "Check the prepared text on real findings.",
      "backend/clawback/findings/actions.py, backend/clawback/main.py"),
    # Live: on 2026-10-23 Nemotron 3 Ultra wrote all five finding letters and the bill negotiation on the demo data
    # (about $0.005); in earlier runs a dropped [account number] sent it back to the template, as designed.
    F("ultra-letters", "Actions", "Ultra writes letters and scripts", "live",
      "Nemotron 3 Ultra writes the dispute, fee, price-adjustment and flight letters; code rejects any number, date or link not in the facts.",
      "Run it on real findings.",
      "backend/clawback/findings/letters.py"),
    F("finding-status", "Actions", "Dismiss, done and money recovered", "built",
      "Dismiss a finding or mark it done; a finding marked done stays listed, and its refund is checked on the next sync.",
      "Run it on real findings.",
      "backend/clawback/main.py, backend/clawback/pipeline/run.py, backend/clawback/pipeline/confirm.py"),
    F("cancel-confirmation", "Actions", "Check the money came back", "built",
      "Confirms from bank data that a cancelled charge stopped, flags a charge after cancelling, and matches refund credits to findings.",
      "Confirm one cancellation and one refund on a real bank feed.",
      "backend/clawback/pipeline/confirm.py, backend/clawback/pipeline/run.py"),
    F("legal-rules", "Actions", "State auto-renewal rules", "built",
      "Adds the person's state rule, or the federal one, to cancel steps, from 12 state laws checked against their official pages.",
      "Have someone with legal training read the state rows; every row cites its source.",
      "backend/clawback/pipeline/rights.py, backend/clawback/rules/auto_renewal.json"),

    # --- Models and search ----------------------------------------------------------------------------
    # Live: `python -m clawback.llm --check` called all five tiers on 2026-10-22 and again on 2026-10-23, and every
    # one answered in strict JSON (llm.py docstring, docs/token-factory-feedback.md, docs/ARCHITECTURE.md section 8).
    F("model-tiers", "Models and search", "Five Nemotron model tiers", "live",
      "Five Nemotron models on Token Factory, from Nemotron 3.5 Lightning for every email to Nemotron 3 Ultra for reasoning, checked live with one command.",
      None,
      "backend/clawback/llm.py"),
    F("model-fallbacks", "Models and search", "Backup model and code fallbacks", "built",
      "When a model fails, Nemotron 3 Nano or plain code takes over, so the app keeps working.",
      "Seen only with a fake model; the live check calls each tier on its own, so no real fallback is recorded yet.",
      "backend/clawback/llm.py, backend/clawback/pipeline/extract.py"),
    # Live: Ishani's model-tier work on 2026-10-22 ran it in the app on the demo emails (docs/token-factory-feedback.md),
    # and the eval harness ran it three times on 109 synthetic emails on 2026-10-23 (docs/EVAL.md).
    F("email-extraction", "Models and search", "Email facts read by Lightning", "live",
      "Nemotron 3.5 Lightning reads each email once into facts, such as a price change or trial end date, with Nano and rules as backups.",
      "Run it on a real inbox; Zero Data Retention is on.",
      "backend/clawback/pipeline/extract.py, backend/tests/test_live.py"),
    # Live: searches since 2026-10-22, and page reads (extract) for the cancel lookup and price checks on 2026-10-23.
    F("tavily-search", "Models and search", "Tavily web search", "live",
      "Searches the web and reads pages for the plan, cancel-page, bill-offer, settlement and store-price checks.",
      "Watch credit use on the hosted demo; cancel pages are cached for 30 days.",
      "backend/clawback/tools/tavily.py"),
    # Live: on 2026-10-23 seven unknown demo senders cost $0.00009; United, Comcast, Best Buy and Walmart were kept,
    # LinkedIn, Medium and GitHub dropped.
    F("triage-model", "Models and search", "Model check for unknown senders", "live",
      "Sends emails the keyword rules can't place to Nemotron 3.5 Lightning for a cached yes or no, at most 200 a run.",
      "Count what it keeps and drops on a real inbox.",
      "backend/clawback/pipeline/triage.py"),
    F("email-classifier", "Models and search", "Trained email filter", "planned",
      "A small trained model (ModernBERT) that sorts large volumes of email more cheaply than Lightning.",
      "Only worth it above about 16,000 emails a day; Lightning triage covers the hackathon.",
      NOT_STARTED, "email-classifier"),
    F("pdf-receipts", "Models and search", "Read receipt images and PDFs", "built",
      "Reads PDF receipts with pypdf and Lightning, and image receipts with Nemotron 3.5 Super-VL, checked against the totals.",
      "Download one real attachment from a connected Sandbox inbox; the model reads ran live on made-up receipts.",
      "backend/clawback/findings/receipts.py, backend/clawback/sources/nylas.py"),
    F("self-hosted-model", "Models and search", "Host a Nemotron model ourselves", "planned",
      "Runs a Nemotron model on a Nebius endpoint the team hosts, next to the Token Factory calls.",
      "A stretch goal for after Oct 30; the Token Factory calls already meet the hackathon rules.",
      NOT_STARTED),

    # --- Trust and safety -----------------------------------------------------------------------------
    # Live: the team confirmed on 2026-10-23 that Zero Data Retention is on in the Token Factory profile settings.
    F("zdr", "Trust and safety", "Zero Data Retention turned on", "live",
      "Token Factory keeps and logs no prompts for ClawBack, so email text sent to a model isn't stored.",
      "Check the setting again before real users connect.",
      "docs/PRIVACY.md"),
    # Live: on 2026-10-23 Lightning flagged a money-request email and cleared an ordinary mention of an AI assistant;
    # a quiet attack that passed the screen still couldn't change the $9.99 amount.
    F("prompt-injection", "Trust and safety", "Prompt-injection guard", "live",
      "Screens email for hidden instructions before any model reads it; a flagged email goes to the rules only, and model output must match the email.",
      "Text hidden with CSS classes or white on white still counts as visible.",
      "backend/clawback/pipeline/guard.py, backend/clawback/pipeline/grounded.py, backend/clawback/sources/text.py"),
    F("verified-rules", "Trust and safety", "Fact-checked rules with sources", "built",
      "Every refund window, fee, flight, settlement and state rule cites its official page, and only verified rows raise a finding.",
      "Use it on real bank and email data; rows older than about 3 months need a fresh check.",
      "backend/clawback/rules, backend/clawback/findings/rulebook.py"),
    # Live: the cancel lookup on 2026-10-23 dropped look-alike and third-party pages from real Tavily results and
    # kept only pages on each merchant's own domain.
    F("cited-links", "Trust and safety", "Links checked against sources", "live",
      "Links shown to people come only from checked search results or a short verified list, never from a model.",
      "Keep the merchant domain list growing with the merchant list.",
      "backend/clawback/pipeline/recommend.py, backend/clawback/pipeline/cancel_lookup.py"),
    F("token-encryption", "Trust and safety", "Encrypted saved tokens", "built",
      "Encrypts each saved Plaid token and Nylas grant, and every stored row, with a key kept outside the database.",
      "Set CLAWBACK_SECRET_KEY on the server and save one real token encrypted.",
      "backend/clawback/crypto.py, backend/clawback/connections.py, backend/clawback/store.py"),
    # Live: on 2026-10-23 the per-session cap on port 8001 allowed one Ultra cancel email ($0.00048) and skipped the
    # second, and the app fell back to its template.
    F("spend-caps", "Trust and safety", "Daily model spend limits", "live",
      "Caps model spend per session ($0.25 a day) and overall ($5 a day); past a cap, ClawBack uses rules and templates.",
      "Tune the limits once judges use the hosted demo.",
      "backend/clawback/budget.py, backend/clawback/llm.py"),
    F("privacy-policy", "Trust and safety", "Privacy policy", "built",
      "Says what ClawBack reads, who processes it, what's stored and how to delete it, as a page and a doc.",
      "Fill in the contact email and server region before the demo goes public.",
      "docs/PRIVACY.md, frontend/app/privacy/page.tsx"),

    # --- Accounts and storage -------------------------------------------------------------------------
    # Live: on 2026-10-23 a keep decision survived a restart of the backend on port 8001, and the database file held
    # no plaintext merchant names.
    F("database", "Accounts and storage", "Saved data in SQLite", "live",
      "Keeps each visitor's data in one encrypted SQLite database, so a restart loses nothing; real email text is never written to disk.",
      "Put the database on the server's data disk and back it up nightly (deploy/vm/update.sh keeps 7 copies).",
      "backend/clawback/db.py, backend/clawback/store.py"),
    # Live: on 2026-10-23 the backend on port 8001 refused requests without a session, built the demo once with live
    # Lightning calls, and gave each later session its own copy in about 0.3 s.
    F("auth", "Accounts and storage", "Own session for each visitor", "live",
      "Each browser gets its own private session and demo month, with no login or password, as the team chose on 2026-10-23.",
      "Check it on the hosted URL from two browsers.",
      "backend/clawback/sessions.py, backend/clawback/demo.py, frontend/app/api.ts"),
    F("saved-connections", "Accounts and storage", "Connections survive a restart", "built",
      "Keeps the connected email and bank in the encrypted database and syncs them again on startup.",
      "Restart once with a real Sandbox connection saved.",
      "backend/clawback/connections.py, backend/clawback/connect.py"),
    F("delete-my-data", "Accounts and storage", "Delete all my data", "built",
      "Removes the email and bank connections at Nylas and Plaid, and everything ClawBack holds for the session, in one step.",
      "Delete one session with a Sandbox connection and check Nylas and Plaid dropped it.",
      "backend/clawback/sessions.py, backend/clawback/main.py, frontend/app/settings/page.tsx"),

    # --- Dashboard ------------------------------------------------------------------------------------
    F("dashboard", "Dashboard", "Dashboard page", "built",
      "Shows monthly spend, money owed to you, subscriptions and bills in groups, cancellations, money back and the action panels.",
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
    F("onboarding", "Dashboard", "First-visit guide", "built",
      "Three short lines on the first visit say it's a demo month, where to look and how to try it on your own data.",
      "Watch a first-time visitor use it and cut what they skip.",
      "frontend/app/dashboard/page.tsx"),
    F("recovered-history", "Dashboard", "History of money recovered", "built",
      "Lists each cancellation and refund that came back, marked as confirmed in bank data or told to us.",
      "Confirm one refund from a real bank credit.",
      "backend/clawback/pipeline/recovered.py, backend/clawback/main.py, frontend/app/dashboard/page.tsx"),
    F("settings-page", "Dashboard", "Settings page", "built",
      "One page for this browser's session, connections, state, what's stored, today's model use and deleting everything.",
      "Nothing outside to test; it goes public with the demo URL.",
      "frontend/app/settings"),
    F("notifications", "Dashboard", "Alerts for new finds", "built",
      "Background runs (new mail, the nightly job) record new flags and findings, and the dashboard shows them until marked seen.",
      "Email or push alerts aren't planned for the hackathon; alerts stay in the app.",
      "backend/clawback/alerts.py, frontend/app/dashboard/page.tsx", "notifications"),

    # --- Phone app (docs/MOBILE.md) ------------------------------------------------------------------
    F("installable-app", "Phone app", "Install on your phone", "built",
      "Installs on a phone's home screen and opens full screen with its own icon, from Chrome's install button or Safari's Add to Home Screen.",
      "Install it on an Android phone and an iPhone, and check the icons and the notch padding.",
      "frontend/app/manifest.ts, frontend/app/components/InstallApp.tsx, frontend/public/icons, frontend/app/layout.tsx"),
    F("shared-api-types", "Phone app", "Shared API types", "planned",
      "TypeScript types generated from the backend's OpenAPI schema, shared by the website and the phone app instead of copied by hand.",
      "Generate them with openapi-typescript into a small package both apps import.",
      NOT_STARTED),
    F("native-app", "Phone app", "Native phone app", "planned",
      "A React Native app built with Expo on the same API and sessions, with five screens: your month, to do, details, money back and your data.",
      "Build the five screens on the demo session, after the shared types (docs/MOBILE.md, stage 2).",
      NOT_STARTED, "mobile-app"),
    F("app-sign-in", "Phone app", "Sign-ins that return to the app", "planned",
      "Email and bank sign-ins that come back to the phone app through an app link instead of the website.",
      "Add an allowed list of return targets to the email callback, and the Plaid React Native SDK.",
      NOT_STARTED),
    F("push-alerts", "Phone app", "Push notifications", "planned",
      "New alerts from the nightly check and the webhooks reach the phone as push notifications.",
      "Add routes to register a device's push token, and send each new alert through the Expo push service.",
      NOT_STARTED),
    F("app-store-release", "Phone app", "App store release", "planned",
      "Publishing the native app on the App Store and Google Play.",
      "Get production email and bank access first, then fill in the store privacy forms from docs/PRIVACY.md.",
      NOT_STARTED),
    # --- Submission -----------------------------------------------------------------------------------
    # Live: the model-tiers check and the live extraction runs on 2026-10-22 and 2026-10-23 (see above).
    F("token-factory-runtime", "Submission", "Live Token Factory calls", "live",
      "The app calls NVIDIA Nemotron models on Nebius Token Factory while it runs, as the hackathon requires.",
      "Make sure the hosted demo makes these calls too.",
      "backend/clawback/llm.py, backend/clawback/pipeline/extract.py"),
    F("deploy", "Submission", "Public demo URL", "started",
      "A public link to the app that keeps working until Dec 15.",
      "Create the Nebius VM and the Vercel project with the team, then follow docs/DEPLOY.md.",
      "docs/DEPLOY.md, deploy/vm, backend/Dockerfile", "deploy"),
    # Live: every visitor gets their own seeded demo month with no login (see auth above).
    F("judge-login", "Submission", "Judge demo with no login", "live",
      "Judges open the link and get their own seeded demo month, without connecting an inbox or a bank.",
      "Check it on the hosted URL.",
      "backend/clawback/sessions.py, backend/clawback/demo.py"),
    F("license-public", "Submission", "Open-source license and public repo", "started",
      "An MIT license file and a public repo, both required to submit.",
      "The license is added; rotate every key, clean the history and make the repo public (docs/DEPLOY.md section 13).",
      "LICENSE, docs/DEPLOY.md", "license-public"),
    F("readme", "Submission", "README with setup and models", "built",
      "Explains how to run ClawBack and what each Nemotron model does in it.",
      "Add the demo URL once it exists.",
      "README.md"),
    F("demo-video", "Submission", "Demo video under 3 minutes", "started",
      "A short video that shows the DashPass money-losing card within the first 30 seconds.",
      "The shot list is written; record it once the hosted demo works.",
      "docs/VIDEO.md", "demo-video"),
    F("write-up", "Submission", "Write-up and model feedback", "started",
      "The submission write-up, including feedback on Token Factory and the Nemotron models.",
      "Fill the eval numbers and the demo URL into the draft.",
      "docs/WRITEUP.md, docs/token-factory-feedback.md", "write-up"),
    # Live: find cheaper, the cancel lookup, bill offers, price checks and the settlements refresh all called
    # Tavily live on 2026-10-22 and 2026-10-23.
    F("tavily-bonus", "Submission", "Tavily bonus", "live",
      "Uses Tavily for current plans, cancel pages, bill offers, store prices and new settlements, for the Tavily bonus prize.",
      "Name Tavily plainly in the video and the write-up.",
      "backend/clawback/tools/tavily.py, backend/clawback/pipeline/recommend.py, backend/clawback/pipeline/cancel_lookup.py"),
    # Live: models-on ran three times and an all-Ultra sample on 24 emails on 2026-10-23 (about $0.05 in all).
    F("eval-set", "Submission", "Labelled test set and results", "live",
      "Three made-up people with 109 emails and known answers measure subscriptions found, false flags and cost per 1,000 emails, with every failure listed.",
      "Re-run it on the merged code and score a held-out set before quoting numbers.",
      "backend/evals, docs/EVAL.md"),
    F("own-accounts-run", "Submission", "Run on our own accounts", "planned",
      "Runs ClawBack on the team's own email and bank to report real money found.",
      "Connect the team's own inbox once the hosted demo works; Zero Data Retention is on.",
      NOT_STARTED, "own-accounts-run"),
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
