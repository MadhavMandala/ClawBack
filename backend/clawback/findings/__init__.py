"""One-time money in the user's own bank and email data, and the bill checks.

- charges.py: duplicate charges and bank fees.
- refunds.py: store price drops inside the price-adjustment window, and flight refunds / compensation.
- settlements.py: open class-action settlements that match the user's merchants.
- bills.py: bill price hikes, promo endings and "you could ask for less".
- actions.py: the request, letter or script for each finding (ClawBack never sends, files or calls anything).
- detect.py: runs the detectors for one user and records a trace row for each.

Every rule a finding relies on comes from backend/clawback/rules (see rulebook.py), never from memory.
All date and money math is code; models only read text (purchase and flight emails) or write wording.
"""
