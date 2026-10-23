"""A duplicate charge that already came back (a matching credit from the same merchant afterwards) isn't flagged."""

from datetime import date, timedelta

import pytest

from clawback.findings.charges import duplicate_charges
from clawback.models import Transaction

TODAY = date(2026, 10, 23)
DAY = date(2026, 10, 1)
DISPUTES = {"credit": {"name": "Credit card billing errors", "summary": "60 days.",
                       "source_url": "https://www.ecfr.gov/current/title-12/section-1026.13", "days": 60}}


def tx(i: int, on: date, desc: str, amount: float) -> Transaction:
    return Transaction(id=f"t{i}", date=on, description=desc, amount=amount, source="plaid")


def charges(n: int = 2, amount: float = 89.99) -> list[Transaction]:
    return [tx(i, DAY + timedelta(days=i), "BEST BUY 00012345", amount) for i in range(n)]


def found(txs):
    return duplicate_charges(txs, set(), [], DISPUTES, TODAY)


@pytest.mark.parametrize("credit", [
    "BEST BUY 00012345",
    "REFUND BEST BUY 00012345",
    "BEST BUY RETURN 00012345",
    "Best Buy",
])
def test_refunded_duplicate_is_not_flagged(credit):
    assert len(found(charges())) == 1
    assert found(charges() + [tx(9, DAY + timedelta(days=6), credit, -89.99)]) == []


def test_partly_refunded_triple_charge_counts_only_what_is_still_owed():
    [f] = found(charges(3) + [tx(9, DAY + timedelta(days=5), "REFUND BEST BUY", -89.99)])
    assert f.amount == 89.99
    assert any("already came back" in e and "isn't counted" in e for e in f.evidence)
    assert "you can get $89.99 back" in f.message


@pytest.mark.parametrize("credit", [
    tx(9, DAY - timedelta(days=3), "BEST BUY 00012345", -89.99),  # before the first charge
    tx(9, DAY + timedelta(days=6), "BEST BUY 00012345", -49.99),  # a different amount
    tx(9, DAY + timedelta(days=6), "TARGET 00012345", -89.99),  # a different merchant
    tx(9, DAY + timedelta(days=200), "BEST BUY 00012345", -89.99),  # too long after
])
def test_credits_that_dont_match_leave_the_duplicate(credit):
    [f] = found(charges() + [credit])
    assert f.amount == 89.99


def test_one_credit_covers_one_duplicate_only():
    two_pairs = charges() + [tx(5, DAY + timedelta(days=20), "BEST BUY 00012345", 89.99),
                             tx(6, DAY + timedelta(days=21), "BEST BUY 00012345", 89.99),
                             tx(9, DAY + timedelta(days=4), "BEST BUY REFUND", -89.99)]
    [f] = found(two_pairs)  # the first pair was refunded; the second pair still stands
    assert f.details["charges"] == [(DAY + timedelta(days=20)).isoformat(), (DAY + timedelta(days=21)).isoformat()]
