"""rules/merchants.json and the matchers in merchants.py."""

import json
from pathlib import Path

import pytest

from clawback import merchants
from clawback.merchants import (MerchantsFile, by_name, clean_descriptor, display_descriptor, find_in_text,
                                match_bank, match_sender)
from clawback.pipeline.recurring import classify, detect
from clawback.models import Transaction

RULES = Path(merchants.__file__).parent / "rules" / "merchants.json"


def test_file_loads_and_is_the_right_size():
    data = MerchantsFile.model_validate(json.loads(RULES.read_text(encoding="utf-8")))
    assert 80 <= len(data.merchants) <= 160
    assert data.note and data.checked_on
    names = [m.name for m in data.merchants]
    assert len(names) == len(set(names))
    cats = {m.category for m in data.merchants}
    assert {"video_streaming", "music", "news", "software", "cloud_storage", "ai_assistant", "fitness",
            "delivery_membership", "mobile", "internet", "insurance"} <= cats
    assert sum(m.bill for m in data.merchants) >= 20


def test_fragments_are_uppercase_and_domains_lowercase():
    for m in merchants_file_rows():
        assert all(f == f.upper() for f in m.match + m.exclude), m.name
        assert all(d == d.lower() and "." in d and "/" not in d for d in m.domains), m.name
        assert m.source_url is None or m.source_url.startswith("https://")
        assert (m.evidence == "official") == bool(m.source_url), m.name
        if m.billed_by == "apple":
            assert m.match == ()  # Apple's own services bill as APPLE.COM/BILL only


def test_no_fragment_belongs_to_two_merchants():
    seen: dict[str, str] = {}
    for m in merchants_file_rows():
        for f in m.match:
            assert seen.setdefault(f, m.name) == m.name, f


def merchants_file_rows():
    return merchants.merchants_file().merchants


@pytest.mark.parametrize("description, name", [
    ("NETFLIX.COM 866-579-7172 CA", "Netflix"),
    ("DISNEY PLUS 888-905-7888 CA", "Disney+"),
    ("HBO MAX HELP.MAX.COM NY", "HBO Max"),
    ("Spotify USA 877-778-1161", "Spotify"),
    ("GOOGLE *YouTube Premium g.co/helppay#", "YouTube Premium"),
    ("GOOGLE *Google One g.co/helppay#", "Google One"),
    ("AMAZON PRIME*2K4LP0 AMZN.COM/BILL WA", "Amazon Prime"),
    ("AMAZON PRIME VIDEO CHANNELS", "Prime Video (channels & add-ons)"),
    ("UBER *ONE HELP.UBER.COM", "Uber One"),
    ("DOORDASH DASHPASS SAN FRANCISCO", "DoorDash DashPass"),
    ("OPENAI *CHATGPT SUBSCR SAN FRANCISCO", "ChatGPT Plus"),
    ("ANTHROPIC CLAUDE.AI SUBSCRIPTION", "Claude (Anthropic)"),
    ("MICROSOFT*MICROSOFT 365 P 425-6816830 WA", "Microsoft 365"),
    ("NYTIMES*NYTDIGITAL 800-698-4637 NY", "The New York Times"),
    ("PLANET FITNESS 844-880-7180", "Planet Fitness"),
    ("T-MOBILE*AUTO PAY 800-937-8997 WA", "T-Mobile"),
    ("STARLINK INTERNET HAWTHORNE CA", "Starlink"),
    ("LEMONADE INS 844-733-8666 NY", "Lemonade"),
])
def test_match_bank(description, name):
    m = match_bank(description)
    assert m is not None and m.name == name


@pytest.mark.parametrize("description", [
    "UBER *TRIP HELP.UBER.COM", "UBER *EATS PENDING", "DOORDASH*CHIPOTLE SAN FRANCISCO", "AMAZON MKTPL*2K4LP0",
    "PEACOCK INN PRINCETON NJ", "STATE FARM ARENA ATLANTA", "FRONTIER AIRLINES DENVER", "PANDORA JEWELRY #123",
    "TIDAL WAVE AUTO SPA", "APPLE.COM/BILL 866-712-7753 CA", "KROGER #0412 ATLANTA GA", "ATTORNEY AT LAW",
])
def test_lookalikes_do_not_match(description):
    assert match_bank(description) is None


def test_bills_in_the_list_are_bills():
    key, rule = classify(Transaction(id="1", date="2026-10-01", description="STARLINK INTERNET", amount=120.0))
    assert key == "bill:Starlink" and rule["category"] == "internet"
    # rules/bills.json (verified providers) wins over the merchant list
    book_rule = {"provider": "Verizon Wireless", "category": "mobile"}
    key, rule = classify(Transaction(id="2", date="2026-10-01", description="VERIZON WIRELESS", amount=80.0),
                         lambda d: book_rule if "VERIZON" in d else None)
    assert key == "bill:Verizon Wireless" and rule is book_rule


def test_list_bill_is_detected_as_a_bill():
    from datetime import date, timedelta
    today = date(2026, 10, 22)
    txs = [Transaction(id=str(k), date=today - timedelta(days=30 * k), description="LEMONADE INS 844-733-8666",
                       amount=24.0 + (k % 2)) for k in range(4)]
    [s] = detect(txs, today)
    assert s.kind == "bill" and s.merchant == "Lemonade" and s.bill_category == "insurance"


def test_match_sender_needs_one_owner():
    assert match_sender("no-reply@doordash.com").name == "DoorDash DashPass"
    assert match_sender("hello@hulumail.com").name == "Hulu"
    assert match_sender("info@account.netflix.com").name == "Netflix"
    assert match_sender("no_reply@email.apple.com") is None  # iCloud+, Apple Music, Apple TV ... share it
    assert match_sender("noreply@stranger.example") is None


def test_find_in_text_whole_words_longest_first():
    assert find_in_text("iCloud+ with 200 GB (Monthly)").name == "iCloud+"
    assert find_in_text("Super Duolingo (Monthly)").name == "Super Duolingo"
    assert find_in_text("YouTube Premium (YouTube)").name == "YouTube Premium"
    assert find_in_text("Calm: Sleep & Meditation").name == "Calm"
    assert find_in_text("stay calm and match the inbox at maximum") is None  # ordinary words, not names
    assert find_in_text("Your toolbox") is None


def test_clean_descriptor():
    assert clean_descriptor("SQ *SOME GYM 1234 ATLANTA GA") == "SOME GYM ATLANTA"
    assert clean_descriptor("TST* BLUE BOTTLE COFFEE 0042") == "BLUE BOTTLE COFFEE"
    assert clean_descriptor("GOOGLE *Sleep Sounds g.co/payhelp#CA") == "Sleep Sounds"
    assert clean_descriptor("PAYPAL *SOMEAPP.COM 4029357733") == "SOMEAPP"
    assert clean_descriptor("APPLE.COM/BILL 866-712-7753 CA") == ""
    assert display_descriptor("SQ *SOME GYM 1234") == "Some Gym"


def test_existing_demo_names_are_kept():
    for name in ("Netflix", "Hulu", "Spotify", "DoorDash DashPass", "Google One", "iCloud+", "Adobe Creative Cloud",
                 "ChatGPT Plus", "Super Duolingo"):
        assert by_name(name) is not None
    assert by_name("iCloud+").known_cancel_url == merchants.APPLE_SUBSCRIPTIONS_URL
