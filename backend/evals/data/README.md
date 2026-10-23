# ClawBack eval set (synthetic)

**Everything in this folder is synthetic.** The ClawBack team wrote it, with AI help, to test the product. No
real person's email or bank data is in it.

- The three people (Maya Chen, Sam Okafor, Lucía Romero), their addresses (`example.com`, `example.net`,
  `example.org`), their banks (`*.example` domains), order numbers, booking codes and amounts are invented.
- Merchant names, bank descriptors and sender domains are real companies (Netflix, `no_reply@email.apple.com`,
  `DeltaAirLines@e.delta.com`...) so the data looks like a real statement and inbox. The email texts are written
  for this set; none is copied from a real message. Prices are illustrative, not quotes of current prices.
- The phishing email uses a look-alike domain (`netf1ix-billing.com`) and the prompt-injection email an invented
  one. Neither link is real.

## Files

| File | Person | Transactions | Emails |
|---|---|---|---|
| `p1_maya.json` | Product designer, Atlanta: many subscriptions, Apple-billed apps, a family plan | 214 | 38 |
| `p2_sam.json` | Parent in Columbus: delivery and ride memberships, storage overlap, a cancelled flight | 202 | 40 |
| `p3_lucia.json` | Graduate student in Houston: Spanish receipts, an HTML-heavy trial email, EU261 | 173 | 31 |

The JSON files are the dataset of record. `../build_data.py` generated them and holds the same data and labels in
a more readable form; edit it and run `python -m evals.build_data` (from `backend/`) to regenerate.

## Shape of one file

- `today`: the fixed date the pipeline runs on (2026-10-20), so deadlines and windows never drift.
- `transactions`: `{id, date, description, amount}`. Positive amounts are money out.
- `emails`: `{id, received_at, from, from_name, subject, body, format, label}`. `format` is `text` or `html`
  (the body is then raw HTML, converted the way the Nylas source converts it). `label` is never shown to the
  product.
- `simulated_prices`: the "current price" the price-drop check sees for an item, by store and a phrase in the
  item name.
- `labels`:
  - `subscriptions`: every subscription and bill the person pays: merchant, the `names` a matcher accepts,
    `kind` (subscription or bill), cadence, current amount, `billed_by` (apple / google_play), `status`
    (active or trial), the `flags` it should get and why (`note`), and the descriptors (`bank`) or emails
    behind it.
  - `findings`: the one-time money to find: kind, merchant, amount (null when a settlement has no fixed
    payout), currency, and the transaction and email ids behind it.
  - `not_subscriptions`: recurring or frequent charges that are not subscriptions (rent, loans, copays,
    groceries...), used to explain false subscriptions.
  - `traps`: named hard cases, each with declarative checks (see `evals/score.py`).

Email `label.kind` is one of `delivery_order`, `inactivity`, `engagement`, `price_change`, `trial`,
`store_receipt` (App Store or Google Play receipts only), `other` (money-related but no subscription signal:
merchant receipts, bills, newsletters from subscribed merchants) or `irrelevant`.

## How the labels were decided

The labels say what a careful person reading the whole statement and inbox would conclude, not what the product
outputs. Choices worth knowing:

- `price_increase` means the bank already shows a higher charge. An increase that is announced but not charged
  yet (Disney+) is labelled `price_change` on the email and gets no flag.
- `overlap` follows the product's idea of waste: two plans in the same category of cloud storage, music or AI
  assistant.
- `unused` needs evidence in the data (an inactivity email). A subscription with no evidence either way is
  labelled `usage: unknown` and gets no flag.
- Ride receipts that show Uber One savings are labelled `delivery_order`: they are per-use receipts for the
  membership, which is how the product's usage rules describe them.
- Newsletters and promotions from subscribed merchants are `other`, including Netflix's "Because you watched"
  recommendations: they are not a usage summary.
- A settlement is labelled only when the data shows the person qualifies (a purchase inside the class period
  from a nationwide class). Low-confidence "might apply" settlement hints count as false findings.
- Rent, mortgages, car loans, savings transfers and prescription copays are not subscriptions, even when the
  amount repeats every month.
