"""Real card statement dates for dispute deadlines: Plaid /liabilities/get (fake, over httpx.MockTransport), the
statement that first shows a charge, and the estimate when no date is known."""

import json
from datetime import date, timedelta

import httpx
import pytest
from conftest import plaid_tx, sync_page

from clawback.findings.actions import prepare
from clawback.findings.charges import add_months, duplicate_charges, first_statement
from clawback.models import BankAccount, Transaction
from clawback.sources import net, plaid
from clawback.store import store

TODAY = date(2026, 10, 23)
DISPUTES = {
    "credit": {"name": "Credit card billing errors (Regulation Z)", "summary": "Write within 60 days.",
               "source_url": "https://www.ecfr.gov/current/title-12/section-1026.13", "days": 60},
    "debit": {"name": "Debit card errors (Regulation E)", "summary": "Tell the bank within 60 days.",
              "source_url": "https://www.ecfr.gov/current/title-12/section-1005.11", "days": 60},
}
CARD = BankAccount(account_id="card-1", kind="credit", subtype="credit card", mask="3333",
                   last_statement_issue_date=date(2026, 10, 12), checked_on=TODAY)
CHECKING = BankAccount(account_id="chk-1", kind="depository", subtype="checking", mask="0000", checked_on=TODAY)


def twice(on: date, account: str | None, amount: float = 89.99) -> list[Transaction]:
    return [Transaction(id=f"a{on}", date=on, description="BEST BUY 00012345", amount=amount, account_id=account),
            Transaction(id=f"b{on}", date=on + timedelta(days=1), description="BEST BUY 00012345", amount=amount,
                        account_id=account)]


def dup(txs, accounts=None):
    found = duplicate_charges(txs, set(), [], DISPUTES, TODAY, accounts)
    assert len(found) == 1
    return found[0]


# --- Which statement first shows a charge -------------------------------------------------------------

@pytest.mark.parametrize("charged, last, statement, how", [
    (date(2026, 10, 1), date(2026, 10, 12), date(2026, 10, 12), "exact"),
    (date(2026, 10, 12), date(2026, 10, 12), date(2026, 10, 12), "exact"),  # the earliest possible statement
    (date(2026, 9, 12), date(2026, 10, 12), date(2026, 9, 12), "cycle"),
    (date(2026, 8, 20), date(2026, 10, 12), date(2026, 9, 12), "cycle"),
    (date(2026, 10, 13), date(2026, 10, 12), date(2026, 11, 12), "next"),
    (date(2026, 2, 20), date(2026, 3, 31), date(2026, 2, 28), "cycle"),  # day 31 clamps to the month's end
])
def test_first_statement(charged, last, statement, how):
    assert first_statement(charged, last) == (statement, how)


def test_add_months():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert add_months(date(2026, 1, 15), -1) == date(2025, 12, 15)


# --- Deadlines on duplicate charges -------------------------------------------------------------------

def test_credit_card_with_a_statement_date():
    f = dup(twice(date(2026, 10, 1), "card-1"), {"card-1": CARD})
    assert f.deadline == date(2026, 10, 12) + timedelta(days=60)
    assert f.deadline_label == "Dispute window closes"
    assert ("Your card ending 3333's statement of Oct 12, 2026 first shows this charge (statement date from your "
            "bank, through Plaid), so the 60-day dispute window ends Dec 11, 2026.") in f.evidence
    assert f.details["statement_source"] == "plaid_exact" and f.details["card"] == "credit"
    prep = prepare(f, TODAY)
    assert "(estimated)" not in prep.summary and prep.missing == []
    assert any("comes from your card's statement date" in s for s in prep.steps)


def test_charge_after_the_last_statement_uses_the_next_one():
    f = dup(twice(date(2026, 10, 15), "card-1"), {"card-1": CARD})
    assert f.deadline == date(2026, 11, 12) + timedelta(days=60)
    assert f.deadline_label == "Dispute window closes (from your statement day)"
    assert any(e.startswith("This charge came after your card ending 3333's last statement (Oct 12, 2026)")
               for e in f.evidence)


def test_older_charge_on_an_earlier_cycle():
    f = dup(twice(date(2026, 9, 1), "card-1"), {"card-1": CARD})
    assert f.deadline == date(2026, 9, 12) + timedelta(days=60)
    assert any("issued around day 12 of the month" in e for e in f.evidence)


def test_closed_window_from_real_dates_is_not_flagged():
    # Aug 1 charge: the Aug 12 statement showed it, so the window closed Oct 11, before today.
    assert duplicate_charges(twice(date(2026, 8, 1), "card-1"), set(), [], DISPUTES, TODAY, {"card-1": CARD}) == []


@pytest.mark.parametrize("accounts, account", [
    (None, None),  # CSV, demo data or no Plaid dates
    ({"card-1": CARD.model_copy(update={"last_statement_issue_date": None})}, "card-1"),
])
def test_unknown_statement_date_falls_back_to_the_estimate(accounts, account):
    f = dup(twice(date(2026, 10, 1), account), accounts)
    assert f.deadline == date(2026, 10, 31) + timedelta(days=60)
    assert f.deadline_label == "Dispute window closes (estimated)"
    assert ("Statement date unknown: assumed it closed Oct 31, 2026, so the 60-day dispute window is an estimate."
            in f.evidence)
    prep = prepare(f, TODAY)
    assert "(estimated)" in prep.summary and prep.missing and "MISSING" not in prep.missing[0]


def test_debit_card_uses_regulation_e():
    f = dup(twice(date(2026, 10, 1), "chk-1"), {"chk-1": CHECKING})
    assert f.rule.name == "Debit card errors (Regulation E)" and f.details["card"] == "debit"
    assert f.deadline_label == "Dispute window closes (estimated)"
    assert "This is a debit card account, so the debit card error rule (Regulation E) applies." in f.evidence


# --- Plaid -------------------------------------------------------------------------------------------

LIABILITIES = {
    "accounts": [
        {"account_id": "card-1", "type": "credit", "subtype": "credit card", "mask": "3333", "name": "Plaid Credit Card",
         "balances": {"current": 410.0}},
        {"account_id": "chk-1", "type": "depository", "subtype": "checking", "mask": "0000", "name": "Plaid Checking"},
    ],
    "liabilities": {"credit": [{"account_id": "card-1", "is_overdue": False, "last_statement_issue_date": "2026-10-12",
                                "last_statement_balance": 410.0, "minimum_payment_amount": 20.0}],
                    "mortgage": [], "student": []},
    "item": {"item_id": "item-1"}, "request_id": "r",
}


class FakeLiabilities:
    def __init__(self, inner, reply=(200, LIABILITIES)) -> None:
        self.inner, self.reply, self.calls = inner, reply, 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "sandbox.plaid.com" and request.url.path == "/liabilities/get":
            body = json.loads(request.content)
            assert body["access_token"] == "access-sandbox-1" and body["client_id"] == "plaid-id"
            self.calls += 1
            return httpx.Response(self.reply[0], json=self.reply[1])
        return self.inner(request)


def test_link_token_asks_for_liabilities_as_optional(client, fake):
    client.post("/api/connect/plaid/link-token")
    _, body = fake.plaid.calls[-1]
    assert body["products"] == ["transactions"] and body["optional_products"] == ["liabilities"]
    assert not set(body["products"]) & set(body["optional_products"])  # Plaid: no product in two lists


def test_fetch_accounts(configured, monkeypatch):
    monkeypatch.setattr(net, "transport", httpx.MockTransport(FakeLiabilities(lambda r: httpx.Response(404))))
    store.reset("t")
    accounts = plaid.fetch_accounts("t", "access-sandbox-1", TODAY)
    assert accounts["card-1"].last_statement_issue_date == date(2026, 10, 12) and accounts["card-1"].kind == "credit"
    assert accounts["chk-1"].kind == "depository" and accounts["chk-1"].last_statement_issue_date is None
    assert store.user("t").trace[-1].note == "2 accounts; statement dates for 1 credit card"


@pytest.mark.parametrize("code", ["PRODUCTS_NOT_SUPPORTED", "NO_LIABILITY_ACCOUNTS", "PRODUCT_NOT_READY",
                                  "ADDITIONAL_CONSENT_REQUIRED"])
def test_fetch_accounts_never_raises(configured, monkeypatch, code):
    reply = (400, {"error_type": "ITEM_ERROR", "error_code": code, "error_message": "not available"})
    monkeypatch.setattr(net, "transport", httpx.MockTransport(FakeLiabilities(lambda r: httpx.Response(404), reply)))
    store.reset("t")
    assert plaid.fetch_accounts("t", "access-sandbox-1", TODAY) is None
    row = store.user("t").trace[-1]
    assert row.status == "missing" and code in row.note and "estimated" in row.note


def test_sync_brings_statement_dates_into_findings(client, fake, monkeypatch):
    wrapped = FakeLiabilities(fake)
    monkeypatch.setattr(net, "transport", httpx.MockTransport(wrapped))
    last = (date.today() - timedelta(days=2)).isoformat()  # the charges below are 5 and 4 days old
    charges = [dict(plaid_tx(f"bb{i}", 5 - i, 89.99, "BEST BUY 00012345", "Best Buy"), account_id="card-1")
               for i in range(2)]
    fake.plaid.sync_pages = [sync_page(added=charges)]
    monkeypatch.setitem(LIABILITIES["liabilities"]["credit"][0], "last_statement_issue_date", last)
    r = client.post("/api/connect/plaid/exchange", json={"public_token": "public-sandbox-1", "institution": "Bank"})
    assert r.status_code == 200 and wrapped.calls == 1
    u = store.user("demo")
    assert u.bank_accounts["card-1"].last_statement_issue_date.isoformat() == last
    assert {t.account_id for t in u.transactions} == {"card-1"}
    f = next(f for f in client.get("/api/findings").json() if f["kind"] == "duplicate_charge")
    assert f["deadline"] == (date.fromisoformat(last) + timedelta(days=60)).isoformat()
    assert f["deadline_label"] == "Dispute window closes"
    trace = client.get("/api/trace").json()
    assert any("dispute deadlines from card statement dates" in t["note"] for t in trace)
    assert any(t["stage"] == "plaid: statement dates" and t["status"] == "ok" for t in trace)

    client.post("/api/connect/plaid/disconnect")
    assert store.user("demo").bank_accounts == {}
