"""Unknown recurring charges: named by code from the descriptor, or by Lightning with code's checks."""

import json
from datetime import date, timedelta

import pytest

from clawback.models import Subscription, Transaction
from clawback.pipeline.naming import checked, clean_name, grounded, name_unknown
from clawback.pipeline.recurring import detect_series
from clawback.store import store

TODAY = date(2026, 10, 22)
LIGHTNING = "nvidia/Nemotron-3_5-Lightning"


def gym(desc="SQ *SOME GYM 1234 ATLANTA GA", amount=39.0):
    return [Transaction(id=f"g{k}", date=TODAY - timedelta(days=3 + 30 * k), description=desc, amount=amount)
            for k in range(4)]


def run_naming(user, txs):
    store.reset(user)
    subs, series = detect_series(txs, TODAY)
    name_unknown(user, subs, series)
    return subs


def answer(name, category="fitness", confidence=0.9):
    return json.dumps({"name": name, "category": category, "confidence": confidence})


def test_without_a_key_the_descriptor_is_cleaned_by_code():
    [s] = run_naming("n0", gym())
    assert s.merchant == "Some Gym Atlanta" and "bank descriptor" in s.matched_from
    trace = store.user("n0").trace
    assert any(t.stage == "naming" and t.status == "missing" for t in trace)


def test_lightning_names_it_with_a_strict_schema(fake_llm):
    fake_llm.script[LIGHTNING] = [answer("Some Gym")]
    [s] = run_naming("n1", gym())
    assert (s.merchant, s.category) == ("Some Gym", "fitness")
    assert "Nemotron 3.5 Lightning" in s.matched_from and "0.90" in s.matched_from
    call = fake_llm.calls[0]
    assert call["model"] == LIGHTNING and call["response_format"]["json_schema"]["strict"] is True
    assert "<descriptor>SQ *SOME GYM 1234 ATLANTA GA</descriptor>" in call["messages"][-1]["content"]
    assert "39" not in call["messages"][-1]["content"]  # the descriptor alone: no amount


def test_answer_is_cached_per_descriptor(fake_llm):
    fake_llm.script[LIGHTNING] = [answer("Some Gym")]
    store.reset("n2")
    subs, series = detect_series(gym(), TODAY)
    name_unknown("n2", subs, series)
    subs, series = detect_series(gym(), TODAY)
    name_unknown("n2", subs, series)
    assert len(fake_llm.calls) == 1 and subs[0].merchant == "Some Gym"


def test_low_confidence_keeps_the_descriptor(fake_llm):
    fake_llm.script[LIGHTNING] = [answer("Planet Gym Co", confidence=0.4)]
    [s] = run_naming("n3", gym())
    assert s.merchant == "Some Gym Atlanta" and "confidence 0.40" in s.matched_from


def test_a_name_that_does_not_come_from_the_descriptor_is_rejected(fake_llm):
    fake_llm.script[LIGHTNING] = [answer("Planet Fitness", confidence=0.95)]
    [s] = run_naming("n4", gym())
    assert s.merchant == "Some Gym Atlanta" and "doesn't come from the descriptor" in s.matched_from


def test_the_model_cannot_put_a_link_in_the_name(fake_llm):
    fake_llm.script[LIGHTNING] = [answer("Some Gym https://evil.example/pay www.evil.example evil.com", confidence=0.9)]
    [s] = run_naming("n5", gym())
    assert s.merchant == "Some Gym"
    assert "http" not in s.merchant and "." not in s.merchant


def test_unknown_category_becomes_other(fake_llm):
    fake_llm.script[LIGHTNING] = [answer("Some Gym", category="gyms and things")]
    [s] = run_naming("n6", gym())
    assert s.category == "other"


def test_model_outage_keeps_the_descriptor_and_retries_next_run(fake_llm):
    fake_llm.default = RuntimeError("down")
    [s] = run_naming("n7", gym())
    assert s.merchant == "Some Gym Atlanta"
    assert store.user("n7").merchant_names == {}  # not cached, so the next run asks again


def test_abbreviations_are_grounded():
    assert grounded("Netflix", "PP*NFLX 4029357733")
    assert grounded("Blue Bottle Coffee", "TST* BLUE BOTTLE CO 0042")
    assert not grounded("Planet Fitness", "SQ *SOME GYM 1234")


@pytest.mark.parametrize("raw, out", [
    ("Joe's Pizza", "Joe's Pizza"),
    ("Call 1-800-555-0100 now", "Call now"),
    ("x" * 80, "x" * 40),
    (12, None),
    ("   ", None),
])
def test_clean_name(raw, out):
    assert clean_name(raw) == out


def test_checked_handles_odd_values():
    assert checked(None, "SQ *GYM")[0] is None
    assert checked({"name": "Gym", "category": "fitness", "confidence": "high"}, "SQ *GYM")[0] is None
    assert checked({"name": "Gym", "category": "fitness", "confidence": 7}, "SQ *GYM")[2] == 1.0


def test_known_merchants_are_never_sent_to_the_model(fake_llm):
    netflix = [Transaction(id=f"n{k}", date=TODAY - timedelta(days=30 * k), description="NETFLIX.COM", amount=17.99)
               for k in range(3)]
    run_naming("n8", netflix)
    assert fake_llm.calls == []


def test_store_billed_app_outside_the_list_gets_a_category(fake_llm):
    from clawback.pipeline.naming import categorize_apps

    app = Subscription(id="sleep-sounds", merchant="Sleep Sounds Pro", category="unknown", billed_by="apple")
    unmatched = Subscription(id="apple-bill-4-27", merchant="Apple (unmatched)", category="unknown", billed_by="apple")
    fake_llm.script[LIGHTNING] = [answer("Sleep Sounds Pro", category="wellness", confidence=0.8)]
    store.reset("cat")
    categorize_apps("cat", [app, unmatched])
    assert app.merchant == "Sleep Sounds Pro" and app.category == "wellness"  # the receipt's name stays
    assert unmatched.category == "unknown" and len(fake_llm.calls) == 1
    categorize_apps("cat", [app.model_copy(update={"category": "unknown"})])
    assert len(fake_llm.calls) == 1  # cached
