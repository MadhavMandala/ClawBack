import json
from datetime import date

import pytest

from clawback.models import Subscription, UsageSummary
from clawback.pipeline.recommend import alternatives
from clawback.store import store
from clawback.tools import tavily

TODAY = date(2026, 10, 22)
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
HULU = Subscription(
    id="hulu", merchant="Hulu", category="video_streaming", monthly_cost=18.99,
    usage=UsageSummary(level="none", evidence=["'We miss you' email 18 days ago"]),
)
RESULTS = [
    {"title": "Hulu plans", "url": "https://www.hulu.com/plans", "content": "Hulu (With Ads) $9.99/month. Hulu (No Ads) $18.99/month."},
    {"title": "Streaming deals", "url": "https://example.com/deals", "content": "Peacock Premium $7.99/month."},
]
PLANS_JSON = json.dumps({"plans": [{"name": "Hulu (With Ads)", "monthly_price": 9.99, "source": 0},
                                   {"name": "Peacock Premium", "monthly_price": 7.99, "source": 1}]})
OPTIONS_JSON = json.dumps({"options": [{"option": "Switch to Hulu (With Ads)", "monthly_price": 9.99,
                                        "why": "You barely watch; ads cost you little.", "source": 0}]})


def patch_tavily(monkeypatch, results):
    monkeypatch.setattr(tavily, "available", lambda: True)
    monkeypatch.setattr(tavily, "search", lambda *a, **k: results)


@pytest.fixture()
def tavily_results(monkeypatch):
    patch_tavily(monkeypatch, RESULTS)
    return RESULTS


@pytest.fixture(autouse=True)
def fresh_user():
    store.reset("t")


def test_super_then_ultra(fake_llm, tavily_results):
    fake_llm.script = {SUPER: [PLANS_JSON], ULTRA: [OPTIONS_JSON]}
    out = alternatives("t", HULU, TODAY)
    assert [c["model"] for c in fake_llm.calls] == [SUPER, ULTRA]
    assert fake_llm.calls[1]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True
    assert out["options"][0]["source_url"] == tavily_results[0]["url"]


def test_option_without_valid_source_dropped(fake_llm, tavily_results):
    fake_llm.script = {SUPER: [PLANS_JSON],
                       ULTRA: ['{"options":[{"option":"x","monthly_price":1,"why":"y","source":7}]}']}
    assert alternatives("t", HULU, TODAY)["options"] == []


def test_model_cannot_add_url_or_keys(fake_llm, tavily_results):
    fake_llm.script = {SUPER: [PLANS_JSON],
                       ULTRA: ['{"options":[{"option":"x","monthly_price":1,"why":"y","source":0,"url":"http://evil"}]}']}
    [opt] = alternatives("t", HULU, TODAY)["options"]
    assert set(opt) == {"option", "monthly_price", "why", "source", "source_url"}


def test_super_failure_sends_snippets_to_ultra(fake_llm, tavily_results):
    fake_llm.script = {SUPER: [RuntimeError("x")] * 2, ULTRA: [OPTIONS_JSON]}
    out = alternatives("t", HULU, TODAY)
    assert out["options"]
    assert tavily_results[0]["content"][:40] in fake_llm.calls[-1]["messages"][-1]["content"]


def test_ultra_failure_keeps_hints(fake_llm, tavily_results):
    fake_llm.script = {SUPER: [PLANS_JSON], ULTRA: [RuntimeError("x")] * 2}
    out = alternatives("t", HULU, TODAY)
    assert out["hints"] and out["options"] == [] and out["missing"]


def test_no_search_results_no_model_calls(fake_llm, monkeypatch):
    patch_tavily(monkeypatch, [])
    out = alternatives("t", HULU, TODAY)
    assert fake_llm.calls == [] and out["hints"] and out["missing"]
