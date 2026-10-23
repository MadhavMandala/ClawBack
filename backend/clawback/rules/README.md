# clawback/rules: reference data for money owed

Facts the detectors rely on: store price-adjustment windows, flight refund and compensation rules,
card and bank dispute deadlines, bank-fee patterns, bill providers, and open class-action settlements.
Load them through the typed helpers in `__init__.py`, not by reading the JSON directly.

```python
from datetime import date
from clawback import rules

rules.retailer_for("TARGET 00012345 MINNEAPOLIS")        # Retailer(store="Target", window_days=14, ...)
rules.bill_provider_for("COMCAST CABLE COMM")            # BillProvider(provider="Xfinity (Comcast)", ...)
rules.fee_kind_for("OVERDRAFT FEE")                      # "overdraft"
rules.open_settlements(date(2026, 10, 22))               # verified settlements still taking claims
rules.settlements_matching("AMAZON.COM*AB12", date.today())
rules.delay_compensation("eu261", 1200, 3.5)             # 250
rules.dispute_deadline("credit_card_billing_error", statement_sent_on)
```

## Files

| File | What it holds |
|---|---|
| `retailers.json` | 14 stores. Does the store refund the difference when its own price drops, the window in days, whether it counts from purchase or delivery, membership tiers, exclusions and how to claim. "No" stores (Walmart, Amazon) are included so they are never flagged. |
| `flights.json` | `us_dot`: 14 CFR 260 refund rules (significant change = 3 h domestic / 6 h international, 7 business days card / 20 days other, bag-fee refund at 12 h / 15 h / 30 h). Cash delay compensation is not required (the DOT withdrew that proposal on 2025-11-17). `eu261` / `uk261`: the compensation bands. `airlines`: refund and EU261/UK261 claim pages for 14 airlines. |
| `disputes.json` | Credit card billing errors (Reg Z 1026.13: written notice within 60 days, acknowledgement in 30 days, resolution within 2 billing cycles or 90 days at most). Also card unauthorized use (1026.12(b)), claims and defenses (1026.12(c)), debit/EFT errors (Reg E 1005.11: 60 days, phone OK, 10 business days or 45 days with provisional credit, 90 days for POS/foreign) and remittances (1005.33, 180 days). |
| `bank_fees.json` | 8 fee kinds (ATM, wire, foreign transaction, returned payment, late payment, overdraft, NSF, monthly maintenance). Each has regex `patterns`, a factual `rule`, a neutral `reversal_tip` and a CFPB/OCC/eCFR source. `exclude_patterns` skips refunds and reversals. |
| `bills.json` | 27 bill providers: 8 internet, 6 mobile, 5 insurance, 3 named utilities plus 1 generic utility, and 4 gyms. Each has its account page, change/cancel page and notes (cancellation method, ETF, equipment, gym cancellation rules). Utilities are `negotiable: false` and point to budget billing and assistance. |
| `settlements.json` | 23 open class-action settlements (22 verified) with claim deadlines from 2026-10-26 to 2027-02-10, each with the official claim site. There are no `ftc_refund` rows: the FTC's current refund programs all pay automatically. |

## How it was checked (2026-10-22)

- Every row records the official or primary page it was read from (`source_url`, `source_urls`,
  `extra_source_urls`) and `checked_on`. Regulations come from eCFR and consumerfinance.gov.
  EU and UK rules come from europa.eu (Your Europe), legislation.gov.uk and caa.co.uk. Store, airline,
  provider and settlement facts come from each company's or administrator's own site. Aggregators
  (classaction.org, topclassactions.com) were used only to find candidates.
- Where a site blocked automated fetches, the page was read with a plain HTTP request or from an
  official PDF or a recent Wayback Machine copy of the official page. The row's `notes` say so.
  If nothing official could be read, the row is `verified: false`, sorted last, and its text says why.
- Search-engine snippets never count as verification.
- `tests/test_rules.py` checks that every file loads through its model. It also checks that all URLs are https,
  dates parse, settlement deadlines are on or after `checked_on`, unverified rows come last, and match
  strings are UPPERCASE descriptors or lowercase domains. Finally it exercises the lookup helpers.

## Rules for using this data

- **Re-verify before relying on anything older than ~3 months** (`rules.is_stale(row.checked_on)`).
  Store policies, settlement deadlines and provider pages change without notice.
- Never act on a `verified: false` row. Show it as "unconfirmed", or don't show it at all.
- Settlements: claims are attested under penalty of perjury. Link to the official site only; never
  file or pre-fill for the user.
- Nordstrom refuses automated third-party price-adjustment requests (`no_automated_requests: true`).
  Remind the user to file it themselves.
- Descriptor matching is a hint: `match` entries are case-insensitive, must start at a word boundary,
  and the longest match wins (ties go to the earlier row). Confirm with amount, cadence or an email before
  telling a user they are owed money.

## Riskiest / least certain items

- **retailers.json**: Home Depot, Kohl's, Macy's and Old Navy are `verified: false` (the official
  pages blocked every fetch) and carry the values researched earlier, so don't use them until
  re-checked. Best Buy's window counts from *delivery*, its policy page is dated 2026-09-02, and
  some product categories have fixed windows. Apple's window also counts from delivery, and the claim must be made within 14 days of the price drop.
  Staples now adjusts in-store purchases only.
- **flights.json**: the DOT refunds page (403) and EUR-Lex (JS challenge) could not be read. The US
  rules come from the eCFR text and the EU amounts from europa.eu. An EU261 revision was politically agreed
  on 2026-06-15 and is not yet in force. It would apply 12 months after publication, so re-check then.
  Airline refund and claim URLs are the most likely to move. United is `verified: false` (bot wall,
  no links). Spirit is `verified: false` too: news reports say it stopped flying on 2026-05-02, and spirit.com no longer resolves.
  Several airline pages were read through curl or the r.jina.ai reader because WebFetch was blocked, and a few
  claim forms are JS apps whose URL rests on the official page's link.
- **disputes.json**: low risk (regulation text). "60 days" counts from when the statement was
  *sent*, which ClawBack approximates with the statement date.
- **bank_fees.json**: patterns are guesses at bank wording, not published formats, so expect misses.
  ATM patterns require FEE/CHARGE/SURCHARGE so that "NON-WF ATM WITHDRAWAL" (the cash itself) isn't
  flagged. Late-fee dollar caps are deliberately omitted: eCFR still prints the vacated 2024 $8 rule.
- **bills.json**: Spectrum and Planet Fitness are `verified: false` (bot walls; Planet Fitness rules are
  from a 2026-10-12 Wayback copy). Cox has become Spectrum and Google Fiber is now gFiber. Some descriptors
  are shared or generic: AT&T and Verizon cover both internet and mobile, and VISIBLE, SPECTRUM, OPTIMUM
  and EQUINOX can match other merchants. The generic utility entry matches loosely.
- **settlements.json**: the earliest deadlines are very close (TED 2026-10-26, Bestway and LiveHealth
  2026-10-30). Several classes are limited by state or venue (Nevada events, Missouri stores, California
  citizens, Washington, six Pulsz states, Capital One Arena). Navy Federal, Equifax, TED and
  LiveHealth mainly need the Claim ID/PIN from a mailed or emailed notice. Apple and Telmate were read
  from Wayback copies because of Cloudflare, and GoodRx from its official PDFs. MDLIVE is
  `verified: false` (court notice only). Aggregators list different dates than the official sites for High 5 and the ATM
  surcharge settlement; the official dates are used.
