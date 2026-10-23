# ClawBack held-out eval set (synthetic)

**Everything in this folder is synthetic.** It was written with AI help to test ClawBack. It contains no real
person's email or bank data.

This is the **held-out** set. A separate workstream wrote it to check the main set's numbers (`../data`). It
was written without seeing the main set's data, labels or failures, and before anyone tuned the product on it.
The writer read the product's code and rule data (`backend/clawback/rules`) only to use the same data shapes and
real rule entries: open settlements, store price policies and airlines. **Don't tune the product on this set.**
Its item-level failures are kept out of `docs/EVAL.md` for that reason. If the product is ever fitted to them,
this set stops being held out and a new one should be written.

- The people (Ray and Bev Whitfield, Noor Haddad, Kayla Brooks), their addresses (`example.net`, `example.org`,
  `example.edu`), their banks and card issuers (Gulfview Bank, Cascade Card Services and Pacific Crest Bank, all on
  `*.example` domains), order numbers, booking codes, account numbers and amounts are invented.
- Merchant names, bank descriptors and sender domains are real companies (SiriusXM, `no_reply@email.apple.com`,
  `BA@email.ba.com`...), so the data looks like a real statement and inbox. The email texts were written for this
  set and none is copied from a real message. Prices are illustrative, not quotes of current prices.
- The two phishing emails and the two prompt-injection emails use invented senders (`example.com` and
  `*.example` domains). Their links go nowhere real.

## Files

| File | Person | Transactions | Emails |
|---|---|---|---|
| `h1_whitfield.json` | Retired couple, Clearwater FL: SiriusXM, YouTube TV, a Google Play app, Medicare supplement, a fiber promo ending, a BA cancellation in the UK | 204 | 33 |
| `h2_haddad.json` | Freelance motion designer, Portland OR: business software, two cloud storage plans, a trial, an unused gym, a schedule change, a prompt injection | 256 | 35 |
| `h3_brooks.json` | UCLA sophomore on a budget: four App Store subscriptions, Grubhub+, a trial, an overdraft fee, a Raging Waters settlement, a hidden prompt injection | 195 | 34 |

All three run on a fixed `today` of **2026-10-21**, with bank data from 2026-04-22. `../build_holdout.py`
generates the JSON files from a more readable form. Edit it and run `python -m evals.build_holdout` from
`backend/` to regenerate them. The output is deterministic, because the everyday-spending noise comes from a
seeded random generator.

The file shape is the main set's (see `../data/README.md`), with two additions:

- `set: "holdout"` at the top of each file, beside `synthetic: true`.
- An optional `charge_ids` on a subscription label lists its charges by id. It is needed when the descriptor
  alone can't pick them: four App Store subscriptions share `APPLE.COM/BILL`, and two of them cost the same.

## How the labels were decided

The labels record what a careful person would conclude after reading the whole statement and inbox. They do not
record what the product outputs. The main set's conventions apply: a `price_increase` needs a higher charge in
the bank data; `unused` needs an inactivity email; `overlap` covers cloud storage, music and AI assistants;
rent, loans, transfers and copays are not subscriptions. Choices specific to this set:

- **Announced but not charged:** the YouTube TV and Medicare supplement price emails are `price_change` emails, and
  neither gets a flag yet. A promo-ending email for a bill (Frontier, Xfinity) is also a `price_change` email. If the
  higher price hasn't been charged yet, the bill gets `promo_ending`. Once it has (Xfinity), the bill gets
  `bill_increase`.
- **Price decreases get no flag** (the Adobe downgrade from $59.99 to $19.99).
- **A trial that already converted** (Otter.ai) is an active subscription with no `trial_ending`. A trial that
  was cancelled before it charged (Kindle Unlimited) is not a subscription. Its email is still a `trial` email.
- **Gyms are bills**, as in the product's rules data, and still get `unused` when an email shows no visits.
- **GOOGLE \* is not always Google Play.** YouTube TV and Google Workspace are billed by Google itself, while
  Lumosity is a Google Play app. Its descriptor shows the developer (Lumos Labs) and the receipt shows the app.
- **Utilities** are `variable`. Their label amount is the six-month average, and seasonal swings are not an increase.
- **Price drops** are owed only when the store's own policy in the rules data covers the purchase: Nordstrom
  (10 days from shipment; the customer must ask) and Dell (30 days from the invoice). Two cases are not owed. The
  Staples order was placed on staples.com, and Staples' price match covers store purchases only. The AirPods price
  dropped 16 days after delivery, outside Apple's 14-day window. The amount owed is the item price difference.
- **Flights:** the Alaska change moved a domestic flight by 4 h 35 min. That is a significant change (3 hours or
  more), so a refund is owed if she declines it. The Southwest change of 1 h 10 min is not significant. BA cancelled
  a Heathrow-Edinburgh flight with 13 days' notice and rebooked her to arrive 6 h 10 min later, so UK261 owes
  GBP 220. The flight doesn't touch the US, so no US refund applies.
- **Settlements** are labelled only when the data shows the person qualifies. The cvs.com order (May 2026, before
  the class end of July 27, 2026) qualifies for the CVS digital privacy class. The ragingwaters.com tickets with a
  processing fee (June 10, 2026, before June 22) qualify for the Raging Waters class. Neither has a fixed payout,
  so the amount is null. These look-alikes are not settlements: an Amazon refund after the Amazon class period
  ended in February 2026, a Navy Federal car loan (that class covers fraud-loan victims only) and 2026 AirPods
  (the Apple settlement covers iPhones bought in 2024 and 2025).
- **Already handled:** the July maintenance fee was reversed by the bank, so nothing is owed. Two $15.45 sweetgreen
  charges on the same day are two orders, with two receipts. The Columbia Restaurant and Office Depot doubles
  each have a single receipt, so they are duplicates.
- **Memberships** are judged on the last 30 days, the way the product describes them. Grubhub+ saved $4.48 against
  its $9.99 fee, so it is losing money. Instacart+ saved $17.46, so it is not.

## Hard cases (traps)

Each person has named traps with declarative checks (see `evals/score.py`). There are 55 in all. Their kinds:
`app_store`, `price_change`, `bill_increase`, `unused`, `trial`, `membership`, `overlap`, `annual`, `cadence`,
`look_alike`, `duplicate`, `fee`, `price_drop`, `flight`, `settlement`, `phishing`, `injection` and `noise`.
Most of each person's data is ordinary. The traps sit on top of it.
