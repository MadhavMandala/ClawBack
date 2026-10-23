"""Validates the reference data in clawback/rules/ through its loaders, plus the lookup helpers."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from clawback import rules

RULES_DIR = Path(rules.__file__).parent
FILES = ["retailers.json", "flights.json", "disputes.json", "bank_fees.json", "bills.json", "settlements.json"]
LOADERS = [rules.retailers, rules.flights, rules.disputes, rules.bank_fees, rules.bills, rules.settlements]
CHECKED_ON = date(2026, 10, 22)  # the day this data was researched; fixed so the tests don't age out
DOMAIN = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}")
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)


def _raw(name):
    return json.loads((RULES_DIR / name).read_text(encoding="utf-8"))


def _strings(node, key=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, key)
    elif isinstance(node, str):
        yield key, node


def _all_match_lists():
    for r in rules.retailers().retailers:
        yield r.store, r.match, r.exclude
    for a in rules.flights().airlines:
        yield a.name, a.match, a.exclude
    for b in rules.bills().providers:
        yield b.provider, b.match, b.exclude
    for s in rules.settlements().settlements:
        yield s.id, s.match, s.exclude


@pytest.mark.parametrize("loader", LOADERS, ids=FILES)
def test_every_file_loads_through_its_model(loader):
    loader.cache_clear()
    data = loader()
    assert data.note
    assert data.checked_on <= date.today()


@pytest.mark.parametrize("name", FILES)
def test_every_url_is_https(name):
    for key, value in _strings(_raw(name)):
        if key.endswith("url") or key.endswith("urls"):
            assert value.startswith("https://"), (name, key, value)
        for url in URL.findall(value):  # URLs quoted inside notes too
            assert url.startswith("https://"), (name, key, url)


@pytest.mark.parametrize("name", FILES)
def test_dates_parse(name):
    for key, value in _strings(_raw(name)):
        if key in {"checked_on", "claim_deadline", "start", "end", "withdrawn_on"}:
            date.fromisoformat(value)


@pytest.mark.parametrize("name", FILES)
def test_no_phone_number_without_a_cited_page(name):
    # Phone numbers are only allowed in prose fields, never as structured data.
    for key, value in _strings(_raw(name)):
        if key.endswith("url"):
            assert not re.search(r"\d{3}[-.) ]\d{3}[-.]\d{4}", value), (name, key, value)


def test_rows_are_dated_and_verified_rows_have_sources():
    rows = [*rules.retailers().retailers, *rules.flights().airlines, *rules.bills().providers,
            *rules.settlements().settlements]
    for row in rows:
        assert row.checked_on == CHECKED_ON, row
        assert row.source_url.startswith("https://")


def test_match_lists_are_uppercase_descriptors_or_domains():
    for owner, match, exclude in _all_match_lists():
        assert match, owner
        for m in (*match, *exclude):
            assert m.strip() == m and m, (owner, m)
            assert m == m.upper() or DOMAIN.fullmatch(m), (owner, m)
            assert len(m) >= 3, (owner, m)


def test_settlements_are_open_on_the_check_date_and_well_formed():
    s = rules.settlements()
    assert "penalty of perjury" in s.note
    ids = [x.id for x in s.settlements]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids)
    for x in s.settlements:
        assert x.claim_deadline >= x.checked_on, x.id
        if x.class_period.start and x.class_period.end:
            assert x.class_period.start <= x.class_period.end, x.id
    flags = [x.verified for x in s.settlements]
    assert flags == sorted(flags, reverse=True), "unverified settlements must come last"
    assert sum(flags) >= 15
    assert sum(not f for f in flags) <= 5


def test_unverified_items_are_few():
    for name, rows in [("retailers", rules.retailers().retailers), ("bills", rules.bills().providers),
                       ("airlines", rules.flights().airlines)]:
        unverified = [r for r in rows if not r.verified]
        assert len(unverified) <= len(rows) // 2, name


def test_open_settlements_respects_today():
    open_now = rules.open_settlements(CHECKED_ON)
    assert open_now and all(x.verified for x in open_now)
    assert [x.claim_deadline for x in open_now] == sorted(x.claim_deadline for x in open_now)
    assert rules.open_settlements(date(2030, 1, 1)) == []
    everything = rules.open_settlements(CHECKED_ON, include_unverified=True)
    assert len(everything) == len(rules.settlements().settlements)


def test_settlements_matching():
    amazon = rules.settlements_matching("AMAZON.COM*AB12CD345 SEATTLE WA", CHECKED_ON)
    assert amazon and amazon[0].defendant.startswith("Amazon")
    assert rules.settlements_matching("AMAZON.COM*AB12CD345", date(2030, 1, 1)) == []
    assert rules.settlements_matching("JOE'S DINER 1234", CHECKED_ON) == []


@pytest.mark.parametrize("text, store", [
    ("TARGET 00012345 MINNEAPOLIS MN", "Target"),
    ("BESTBUYCOM806543212345", "Best Buy"),
    ("COSTCO WHSE #0123", "Costco"),
    ("orders@costco.com", "Costco"),
    ("Your order from oe.target.com", "Target"),
])
def test_retailer_for(text, store):
    r = rules.retailer_for(text)
    assert r is not None and r.store == store


def test_retailer_for_unknown_and_policy_flags():
    assert rules.retailer_for("SHELL OIL 57444") is None
    assert rules.retailer_for("") is None
    walmart = rules.retailer_for("WAL-MART #1234")
    assert walmart and walmart.adjusts is False
    best_buy = rules.retailer_for("BEST BUY 00001234")
    assert best_buy.window_for("plus") == 60 and best_buy.window_for() == 15
    nordstrom = rules.retailer_for("NORDSTROM #0427")
    assert nordstrom.no_automated_requests
    # exclude lists veto look-alikes: App Store billing isn't an Apple Store purchase, Rack isn't Nordstrom
    assert rules.retailer_for("APPLE.COM/BILL 866-712-7753 CA") is None
    assert rules.retailer_for("APPLE STORE #R102").store == "Apple"
    assert rules.retailer_for("NORDSTROM RACK #0123") is None
    assert rules.bill_provider_for("SPECTRUM HEALTH GRAND RAPIDS") is None


@pytest.mark.parametrize("text, provider", [
    ("COMCAST CABLE COMM 800-COMCAST", "Xfinity"),
    ("billing@xfinity.com", "Xfinity"),
    ("GEICO *AUTO 800-841-3000", "GEICO"),
    ("PGANDE WEB ONLINE", "PG&E"),
    ("PLANET FITNESS 123456", "Planet Fitness"),
    ("CITY OF SPRINGFIELD WATER UTIL", "utility"),
])
def test_bill_provider_for(text, provider):
    p = rules.bill_provider_for(text)
    assert p is not None and provider.lower() in p.provider.lower(), (text, p)


def test_bill_provider_rules():
    assert rules.bill_provider_for("STARBUCKS STORE 1234") is None
    for p in rules.bills().providers:
        if p.category == "utility":
            assert p.negotiable is False and p.variable_amount is True, p.provider
            assert p.assistance_url, p.provider
    generic = [p for p in rules.bills().providers if p.generic]
    assert len(generic) == 1 and generic[0].category == "utility"
    assert {p.category for p in rules.bills().providers} == {"internet", "mobile", "insurance", "utility", "gym"}


@pytest.mark.parametrize("description, kind", [
    ("OVERDRAFT FEE", "overdraft"),
    ("OVERDRAFT ITEM FEE FOR ITEM 1234", "overdraft"),
    ("NSF FEE", "nsf"),
    ("INSUFFICIENT FUNDS FEE", "nsf"),
    ("FOREIGN TRANSACTION FEE", "foreign_transaction"),
    ("INTL TRANSACTION FEE", "foreign_transaction"),
    ("ATM FEE", "atm"),
    ("NON-WF ATM TRANSACTION FEE", "atm"),
    ("MONTHLY SERVICE FEE", "monthly_maintenance"),
    ("MAINTENANCE FEE", "monthly_maintenance"),
    ("LATE FEE", "late_payment"),
    ("RETURNED PAYMENT FEE", "returned_payment"),
    ("OUTGOING WIRE FEE", "wire"),
    ("INTL WIRE TRANSFER FEE", "wire"),
])
def test_fee_kind_for(description, kind):
    assert rules.fee_kind_for(description) == kind


@pytest.mark.parametrize("description", [
    "NETFLIX.COM 866-579-7172 CA",
    "ATM FEE REFUND",
    "OVERDRAFT FEE REVERSAL",
    "NON-WF ATM WITHDRAWAL AUTHORIZED ON 01/15",
    "ONLINE TRANSFER TO SAVINGS",
    "",
])
def test_fee_kind_for_non_fees(description):
    assert rules.fee_kind_for(description) is None


def test_fee_patterns_compile_and_kinds_unique():
    fees = rules.bank_fees()
    assert "heuristic" in fees.note.lower()
    kinds = [f.kind for f in fees.fees]
    assert len(kinds) == len(set(kinds))
    assert {"overdraft", "nsf", "atm", "foreign_transaction", "monthly_maintenance", "late_payment",
            "returned_payment", "wire"} <= set(kinds)
    for f in fees.fees:
        for p in f.patterns:
            re.compile(p)
        assert "guarantee" not in f.reversal_tip.lower()


def test_flight_rules():
    f = rules.flights()
    dot = f.us_dot
    assert dot.significant_change.domestic_hours == 3 and dot.significant_change.international_hours == 6
    assert dot.refund_deadline.credit_card_business_days == 7
    assert dot.refund_deadline.other_payment_calendar_days == 20
    assert (dot.bag_fee_refund.domestic_hours, dot.bag_fee_refund.international_hours,
            dot.bag_fee_refund.international_long_haul_hours) == (12, 15, 30)
    assert dot.delay_compensation.required is False
    assert dot.delay_compensation.withdrawn_on == date(2025, 11, 17)
    assert [b.amount for b in f.eu261.bands] == [250, 400, 600]
    assert [b.amount for b in f.uk261.bands] == [220, 350, 520]
    assert f.eu261.cancellation_notice_days == 14 and f.eu261.delay_threshold_hours == 3


@pytest.mark.parametrize("scheme, km, hours, intra_eu, expected", [
    ("eu261", 1000, 3.0, False, 250),
    ("eu261", 1000, 2.9, False, None),
    ("eu261", 2500, 5, False, 400),
    ("eu261", 3600, 3.5, True, 400),
    ("eu261", 6000, 3.5, False, 300),
    ("eu261", 6000, 4.0, False, 600),
    ("uk261", 1200, 3, False, 220),
    ("uk261", 2000, 3, False, 350),
    ("uk261", 5500, 3.5, False, 260),
    ("uk261", 5500, 6, False, 520),
])
def test_delay_compensation(scheme, km, hours, intra_eu, expected):
    assert rules.delay_compensation(scheme, km, hours, intra_eu) == expected


@pytest.mark.parametrize("name, url_part", [("United", "united.com"), ("Ryanair", "ryanair.com")])
def test_airlines(name, url_part):
    airline = next(a for a in rules.flights().airlines if a.name.startswith(name))
    assert airline.refund_url is None or url_part in airline.refund_url or airline.verified is False
    assert {a.region for a in rules.flights().airlines} == {"US", "EU", "UK"}


def test_airline_for():
    a = rules.airline_for("DELTA AIR 0062345678901")
    assert a is not None and a.name.startswith("Delta")
    assert rules.airline_for("FRONTIER COMMUNICATIONS") is None or rules.airline_for(
        "FRONTIER COMMUNICATIONS").name != "Frontier Airlines"


def test_disputes():
    cc = rules.dispute_rule("credit_card_billing_error")
    assert (cc.notice_deadline_days, cc.acknowledge_within_days, cc.resolve_within_billing_cycles,
            cc.resolve_within_days_max) == (60, 30, 2, 90)
    assert cc.oral_notice_ok is False
    debit = rules.dispute_rule("debit_card_error")
    assert (debit.notice_deadline_days, debit.investigate_business_days, debit.investigate_days_max) == (60, 10, 45)
    assert debit.oral_notice_ok is True
    assert rules.dispute_deadline("credit_card_billing_error", date(2026, 10, 1)) == date(2026, 11, 30)
    with pytest.raises(KeyError):
        rules.dispute_rule("nope")
    for r in rules.disputes().rules:
        assert any("ecfr.gov" in u or "consumerfinance.gov" in u for u in r.source_urls), r.kind


def test_is_stale():
    assert not rules.is_stale(CHECKED_ON, date(2026, 12, 1))
    assert rules.is_stale(CHECKED_ON, date(2027, 2, 1))


def test_matching_respects_word_starts():
    assert rules.match_strength("KLM ROYAL DUTCH", ("KLM",)) == 3
    assert rules.match_strength("BKLM HOLDINGS", ("KLM",)) == 0
    assert rules.match_strength("no-reply@aa.com", ("aa.com",)) == 6
    assert rules.match_strength("hello@kaa.com", ("aa.com",)) == 0
    assert rules.match_strength("x@aa.community.org", ("aa.com",)) == 0
