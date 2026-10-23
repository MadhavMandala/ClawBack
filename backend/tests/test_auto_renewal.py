"""State auto-renewal rules (rules/auto_renewal.json): the data, which line a cancellation gets, and the state
setting. Same checks as tests/test_rules.py for the other rules files."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from clawback import rules
from clawback.models import Cadence, PriceChange, Subscription
from clawback.pipeline import rights
from clawback.pipeline.cancel import cancel_prep
from clawback.store import store

RULES_DIR = Path(rules.__file__).parent
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I)
TODAY = date(2026, 10, 23)
HULU = Subscription(id="hulu", merchant="Hulu", category="video_streaming", monthly_cost=18.99,
                    cadence=Cadence.monthly)
SPOTIFY = Subscription(id="spotify", merchant="Spotify", category="music", monthly_cost=11.99, cadence=Cadence.monthly)


def _strings(node, key=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, k)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, key)
    elif isinstance(node, str):
        yield key, node


@pytest.fixture(autouse=True)
def fresh():
    rules.auto_renewal.cache_clear()
    store.reset("t")


# --- The data ------------------------------------------------------------------------------------------

def test_file_loads_through_its_model():
    data = rules.auto_renewal()
    assert data.note and data.checked_on <= date.today()
    codes = [s.state for s in data.states]
    assert len(codes) == len(set(codes)) and set(codes) <= set(rights.US_STATES)
    assert {"CA", "NY", "CO", "IL", "MN", "VA", "OR"} <= set(codes)


def test_every_url_is_https():
    raw = json.loads((RULES_DIR / "auto_renewal.json").read_text(encoding="utf-8"))
    for key, value in _strings(raw):
        if key.endswith("url") or key.endswith("urls"):
            assert value.startswith("https://"), (key, value)
        for url in URL.findall(value):
            assert url.startswith("https://"), (key, url)


def test_rows_are_sourced_dated_and_plain():
    for s in rules.auto_renewal().states:
        assert s.verified and s.quote and s.source_url and s.checked_on <= date.today(), s.state
        assert s.effective is None or s.effective <= date.today(), s.state  # only laws already in force
        assert len(s.user_right.split()) <= 32, s.state
        for text in filter(None, (s.user_right, s.price_increase_right)):
            assert "—" not in text and "–" not in text, (s.state, text)  # no em or en dashes
            assert len(text.split()) <= 40 and text.endswith(".") and text[0].isupper(), (s.state, text)
            assert s.name in text or s.state == "DC" and "DC" in text, (s.state, text)  # says whose law it is
            assert not re.search(r"\b(guarantee|always|must refund you|you will get)\b", text, re.I), text
            assert "FTC" not in text and "click-to-cancel" not in text.lower(), text


def test_the_vacated_ftc_rule_is_never_cited_as_law():
    fed = rules.auto_renewal().federal
    assert fed.ftc_negative_option_rule.in_force is False
    assert "vacated" in fed.ftc_negative_option_rule.status
    assert "FTC" not in fed.rosca.user_right and "8403" in fed.rosca.law and fed.rosca.verified


def test_colorado_is_not_described_as_requiring_online_cancellation():
    co = rules.auto_renewal_for("co")
    assert "online" not in co.user_right.lower()


# --- Which line a cancellation gets --------------------------------------------------------------------

def test_unknown_state_gets_only_the_federal_line():
    for state in (None, "", "TX"):  # Texas: no row, so nothing state-specific
        out = rights.rights_for(state, HULU)
        assert [r["scope"] for r in out] == ["federal"]
        assert out[0]["text"].startswith("If you signed up online, federal law says")


def test_state_line_with_its_source():
    out = rights.rights_for("CA", HULU)
    assert len(out) == 1 and out[0]["scope"] == "state" and out[0]["state"] == "CA"
    assert out[0]["text"].startswith("If you signed up online, California law says")
    assert out[0]["source_url"].startswith("https://leginfo.legislature.ca.gov/") and out[0]["checked_on"]


def test_new_york_price_increase_line_only_after_an_increase():
    assert len(rights.rights_for("NY", SPOTIFY)) == 1
    raised = SPOTIFY.model_copy(update={"price_change": PriceChange(old_amount=10.99, new_amount=11.99,
                                                                    changed_on=date(2026, 9, 1))})
    lines = [r["text"] for r in rights.rights_for("NY", raised)]
    assert len(lines) == 2 and "14 days" in lines[1] and "refund" in lines[1]
    cut = raised.model_copy(update={"price_change": PriceChange(old_amount=12.99, new_amount=11.99,
                                                                changed_on=date(2026, 9, 1))})
    assert len(rights.rights_for("NY", cut)) == 1


def test_limits_in_the_data():
    # Connecticut exempts national video streaming: fall back to the federal line.
    assert [r["scope"] for r in rights.rights_for("CT", HULU)] == ["federal"]
    assert [r["state"] for r in rights.rights_for("CT", SPOTIFY)] == ["CT"]
    # Vermont covers yearly contracts only.
    assert [r["scope"] for r in rights.rights_for("VT", SPOTIFY)] == ["federal"]
    yearly = SPOTIFY.model_copy(update={"cadence": Cadence.annual})
    assert [r["state"] for r in rights.rights_for("VT", yearly)] == ["VT"]
    # DC's line is about free trials, so only while one runs.
    assert [r["scope"] for r in rights.rights_for("DC", SPOTIFY)] == ["federal"]
    trial = SPOTIFY.model_copy(update={"status": "trial"})
    assert [r["state"] for r in rights.rights_for("DC", trial)] == ["DC"]


def test_regulated_bills_get_no_line_but_gyms_do():
    internet = Subscription(id="x", merchant="Xfinity (Comcast)", category="internet", kind="bill",
                            bill_category="internet", monthly_cost=80.0)
    assert rights.rights_for("CA", internet) == [] and rights.rights_for(None, internet) == []
    gym = internet.model_copy(update={"merchant": "LA Fitness", "category": "gym", "bill_category": "gym"})
    assert [r["state"] for r in rights.rights_for("CA", gym)] == ["CA"]


@pytest.mark.parametrize("value, code", [("ca", "CA"), (" ny ", "NY"), ("DC", "DC"), (None, None), ("", None)])
def test_normalize_state(value, code):
    assert rights.normalize_state(value) == code


@pytest.mark.parametrize("value", ["XX", "California", "C", "PR1"])
def test_normalize_state_rejects(value):
    with pytest.raises(ValueError, match="US state code"):
        rights.normalize_state(value)


def test_cancel_prep_adds_the_line_and_source():
    store.user("t").state = "IL"
    prep = cancel_prep("t", HULU, TODAY)
    assert "If you signed up online, Illinois law says the company must let you cancel online." in prep["steps"]
    law = [l for l in prep["links"] if l["label"].startswith("The law: ")]
    assert law == [{"label": "The law: Illinois Automatic Contract Renewal Act", "verified": True,
                    "url": "https://www.ilga.gov/Legislation/ILCS/Articles?ActID=2363&ChapterID=67"}]
    assert prep["rights"][0]["law"].startswith("815 ILCS 601")


# --- The setting ---------------------------------------------------------------------------------------

def test_state_setting_routes(client):
    client.post("/api/demo/seed")
    view = client.get("/api/settings").json()
    assert view["state"] is None and view["state_rule"] is None
    assert len(view["states"]) == 51 and {"code": "CA", "name": "California", "has_rule": True} in view["states"]
    assert {"code": "TX", "name": "Texas", "has_rule": False} in view["states"]

    view = client.post("/api/settings/state", json={"state": "ca"}).json()
    assert view["state"] == "CA" and view["state_name"] == "California"
    assert view["state_rule"]["title"] == "California Automatic Renewal Law"

    hulu = next(s for s in client.get("/api/subscriptions").json() if s["merchant"] == "Hulu")
    prep = client.post(f"/api/subscriptions/{hulu['id']}/cancel-prep").json()
    assert any(s.startswith("If you signed up online, California law says") for s in prep["steps"])

    client.post("/api/demo/seed")  # reseeding keeps the setting
    assert client.get("/api/settings").json()["state"] == "CA"

    bad = client.post("/api/settings/state", json={"state": "XX"})
    assert bad.status_code == 400 and bad.json()["detail"] == "That isn't a US state code. Use two letters, like CA."
    assert client.post("/api/settings/state", json={"state": None}).json()["state"] is None
