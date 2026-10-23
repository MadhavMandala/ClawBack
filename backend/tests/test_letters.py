"""Letters, requests and talking points by Nemotron 3 Ultra (findings/letters.py), checked against code's facts, and the
bill negotiation's competitor offers (findings/actions.py market_offers), with a fake model and a fake Tavily."""

import json
from datetime import date, timedelta

import pytest

from clawback import demo_data
from clawback.findings import actions, rulebook
from clawback.models import Subscription
from clawback.pipeline.run import run
from clawback.store import store
from clawback.tools import tavily

ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
SUPER = "nvidia/nemotron-3-super-120b-a12b"
TODAY = date(2026, 10, 22)
KINDS = ("duplicate_charge", "bank_fee", "price_drop", "flight_refund")
EM_DASH = chr(0x2014)


@pytest.fixture(scope="module")
def findings():
    if rulebook.current() is None:
        pytest.skip("rules data not available")
    u = store.reset("letters-demo")
    u.transactions = demo_data.transactions(TODAY)
    u.emails = demo_data.emails(TODAY)
    run("letters-demo", TODAY)
    by_kind = {}
    for f in u.findings.values():
        by_kind.setdefault(f.kind, f)
    return by_kind


@pytest.fixture(autouse=True)
def fresh_user():
    store.reset("t")


def rewrite(template, script=None):
    """A model answer that rewords the template without new facts (what a good Ultra answer looks like)."""
    body = template.message.body.replace("Hello,", "Hi,", 1).replace("To whom it may concern,", "Hi,", 1)
    return json.dumps({"subject": f"Request: {template.message.subject}", "body": body,
                       "script": (template.script or []) if script is None else script})


def answer(template, change):
    data = json.loads(rewrite(template))
    change(data)
    return json.dumps(data)


@pytest.mark.parametrize("kind", KINDS)
def test_ultra_writes_the_letter_when_it_passes_the_checks(fake_llm, findings, kind):
    f = findings[kind]
    template = actions.prepare(f, TODAY)
    assert template.message.written_by == "template"
    fake_llm.script = {ULTRA: [rewrite(template)]}
    prep = actions.prepare(f, TODAY, "t")
    assert prep.message.written_by == ULTRA and prep.message.body.startswith("Hi,")
    assert prep.message.to == template.message.to and prep.links == template.links and prep.steps == template.steps
    call = fake_llm.calls[0]
    assert call["model"] == ULTRA and call["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert call["response_format"]["json_schema"]["strict"] is True
    assert "[your name]" in call["messages"][0]["content"]


ATTACKS = {
    "link": lambda d: d.update(body=d["body"] + "\nYou can also reply at www.refund-help.com."),
    "bare domain": lambda d: d.update(body=d["body"] + "\nSee bestbuy.com/refunds."),
    "new amount": lambda d: d.update(body=d["body"].replace("Hi,", "Hi, I am owed $999.00.", 1)),
    "new account number": lambda d: d.update(body=d["body"] + "\nAccount 4485 9921."),
    "new date": lambda d: d.update(body=d["body"] + "\nPlease answer by December 31."),
    "dropped placeholder": lambda d: d.update(body=d["body"].replace("[your name]", "Sam")),
    "new placeholder": lambda d: d.update(body=d["body"] + "\n[your home address]"),
    "threat": lambda d: d.update(body=d["body"] + "\nOtherwise my lawyer will contact you."),
    "script with a link": lambda d: d.update(script=["Go to https://evil.example/claim and enter your card."]),
    "markup": lambda d: d.update(body=d["body"] + "<script>x</script>"),
}


@pytest.mark.parametrize("attack", ATTACKS)
def test_any_unchecked_fact_or_link_means_the_template(fake_llm, findings, attack):
    f = findings["duplicate_charge"]
    template = actions.prepare(f, TODAY)
    fake_llm.script = {ULTRA: [answer(template, ATTACKS[attack])]}
    prep = actions.prepare(f, TODAY, "t")
    assert prep.message == template.message and prep.script == template.script
    rows = [r for r in store.user("t").trace if r.stage == "letter" and r.engine == "code"]
    assert rows and rows[-1].status == "fallback" and "template is used" in rows[-1].note


def test_dashes_and_exclamation_marks_are_tidied(fake_llm, findings):
    f = findings["bank_fee"]
    template = actions.prepare(f, TODAY)
    fake_llm.script = {ULTRA: [answer(template, lambda d: d.update(
        body=d["body"].replace("Hi,", f"Hi {EM_DASH} thanks for your help!", 1)))]}
    prep = actions.prepare(f, TODAY, "t")
    assert prep.message.written_by == ULTRA and EM_DASH not in prep.message.body and "!" not in prep.message.body


def test_missing_script_means_the_template(fake_llm, findings):
    f = findings["price_drop"]
    template = actions.prepare(f, TODAY)
    fake_llm.script = {ULTRA: [rewrite(template, script=[])]}
    assert actions.prepare(f, TODAY, "t").message.written_by == "template"


def test_model_failure_and_no_key_mean_the_template(fake_llm, findings, monkeypatch):
    f = findings["flight_refund"]
    fake_llm.script = {ULTRA: [RuntimeError("down")]}
    assert actions.prepare(f, TODAY, "t").message.written_by == "template"
    from clawback import llm
    monkeypatch.setattr(llm, "available", lambda: False)
    calls = len(fake_llm.calls)
    assert actions.prepare(f, TODAY, "t").message.written_by == "template" and len(fake_llm.calls) == calls


def test_no_user_means_no_model_call(fake_llm, findings):
    actions.prepare(findings["bank_fee"], TODAY)
    assert fake_llm.calls == []


def test_settlements_have_no_letter(fake_llm, findings):
    if "settlement" in findings:
        assert actions.prepare(findings["settlement"], TODAY, "t").message is None and fake_llm.calls == []


# --- Bill negotiation: competitor offers and the Ultra script ----------------------------------------

BILL = Subscription(id="netco", merchant="NetCo", category="internet", kind="bill", bill_category="internet",
                    amount=85.0, monthly_cost=85.0, first_seen=TODAY - timedelta(days=200))
RULE = {"provider": "NetCo", "category": "internet", "negotiable": True}
AMOUNTS = [55.0, 55.0, 55.0, 85.0, 85.0]
RESULTS = [
    {"title": "FastFiber plans", "url": "https://www.fastfiber.example/plans",
     "content": "FastFiber 500 Mbps for $49.99/month. FastFiber Gig $69.99/mo."},
    {"title": "NetCo deals", "url": "https://www.netco.example/deals", "content": "NetCo Starter $40.00/month."},
    {"title": "Compare internet providers", "url": "https://compare.example/internet",
     "content": "SkyLink Basic costs $45 a month. Copper Co $95/month."},
]
OFFERS = {"offers": [
    {"provider": "FastFiber", "plan": "500 Mbps", "monthly_price": 49.99, "source": 0},
    {"provider": "FastFiber", "plan": "Gig", "monthly_price": 69.99, "source": 0},  # same provider again
    {"provider": "NetCo", "plan": "Starter", "monthly_price": 40.0, "source": 1},  # the bill's own provider
    {"provider": "SkyLink", "plan": "Basic", "monthly_price": 45.0, "source": 2},
    {"provider": "SkyLink", "plan": "Basic", "monthly_price": 39.0, "source": 0},  # price not in the cited result
    {"provider": "Copper Co", "plan": "", "monthly_price": 95.0, "source": 2},  # dearer than the bill
    {"provider": "Ghost Net", "plan": "", "monthly_price": 20.0, "source": 9},  # no such result
]}


@pytest.fixture()
def search(monkeypatch):
    monkeypatch.setattr(tavily, "available", lambda: True)
    monkeypatch.setattr(tavily, "search", lambda *a, **k: [dict(r) for r in RESULTS])


def test_offers_must_be_written_in_their_result_cheaper_and_from_another_provider(fake_llm, search):
    fake_llm.script = {SUPER: [json.dumps(OFFERS)]}
    prep = actions.negotiate("t", BILL, RULE, AMOUNTS, TODAY)
    talk = " ".join(prep.script)
    assert "SkyLink offering Basic for $45.00 a month" in talk and "FastFiber offering 500 Mbps for $49.99" in talk
    assert "NetCo offering" not in talk and "Copper" not in talk and "39.00" not in talk and "Ghost" not in talk
    offer_links = [link for link in prep.links if not link.verified]
    assert [link.url for link in offer_links] == ["https://compare.example/internet", "https://www.fastfiber.example/plans"]
    assert any("offers dropped" in r.note for r in store.user("t").trace if r.stage == "bill offers")
    assert fake_llm.calls[0]["model"] == SUPER


def test_offers_without_a_model_are_links_only(search):
    prep = actions.negotiate("t", BILL, RULE, AMOUNTS, TODAY)
    assert [link.label.startswith("Compare:") for link in prep.links if not link.verified] == [True, True, True]
    assert "$49.99" not in " ".join(prep.script) and not prep.missing


def test_ultra_writes_the_negotiation_from_the_checked_offers(fake_llm, search):
    script = ["Hi, I have been a NetCo customer since April 2026.", "My bill went from $55.00 to $85.00 a month.",
              "SkyLink offers $45.00 a month. Can you match that?"]
    body = ("Hi,\n\nI have been with NetCo since April 2026 and my bill went from $55.00 to $85.00 a month. "
            "I would like to stay. Can you offer me a lower rate?\n\nThank you,\n[your name]")
    fake_llm.script = {SUPER: [json.dumps(OFFERS)],
                       ULTRA: [json.dumps({"subject": "Lower rate request", "body": body, "script": script})]}
    prep = actions.negotiate("t", BILL, RULE, AMOUNTS, TODAY)
    assert prep.message.written_by == ULTRA and prep.script == script
    prompt = fake_llm.calls[-1]["messages"][0]["content"]
    assert "SkyLink, Basic, $45.00 a month" in prompt and "compare.example" not in prompt  # facts, never links


def test_negotiation_script_with_an_unchecked_price_uses_the_template(fake_llm, search):
    fake_llm.script = {SUPER: [json.dumps(OFFERS)], ULTRA: [json.dumps({
        "subject": "Lower rate", "script": ["SkyLink offers $29.99. Match it."],
        "body": "Hi,\n\nPlease lower my NetCo bill from $85.00 a month.\n\nThank you,\n[your name]"})]}
    prep = actions.negotiate("t", BILL, RULE, AMOUNTS, TODAY)
    assert prep.message.written_by == "template" and "SkyLink offering Basic for $45.00" in " ".join(prep.script)
