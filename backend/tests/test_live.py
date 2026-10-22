"""Opt-in live checks against Token Factory. Run with:  CLAWBACK_LIVE=1 .venv/bin/python -m pytest tests/test_live.py -v"""

import os
from datetime import date

import pytest

from clawback import demo_data, llm
from clawback.config import settings
from clawback.pipeline.extract import _extract_rules, extract_all
from clawback.pipeline.triage import triage
from clawback.store import store

pytestmark = pytest.mark.skipif(os.environ.get("CLAWBACK_LIVE") != "1", reason="live: set CLAWBACK_LIVE=1")

TODAY = date(2026, 10, 22)
NUMBERS = ("amount", "saved_amount", "old_price", "new_price")


@pytest.fixture()
def live(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: bool(settings.nebius_api_key))


def test_lightning_matches_rules_on_demo_emails(live):
    store.reset("live")
    emails = triage("live", demo_data.emails(TODAY))
    facts = extract_all("live", emails)
    problems = []
    for email, fact in zip(emails, facts):
        rule = _extract_rules(email)
        if rule.merchant and fact.merchant != rule.merchant:
            problems.append(f"{email.subject!r}: merchant {fact.merchant} != {rule.merchant}")
        if fact.kind != rule.kind:
            problems.append(f"{email.subject!r}: kind {fact.kind} != {rule.kind}")
        for field in NUMBERS:
            if getattr(rule, field) is not None and getattr(fact, field) != getattr(rule, field):
                problems.append(f"{email.subject!r}: {field} {getattr(fact, field)} != {getattr(rule, field)}")
        if rule.trial_end and fact.trial_end != rule.trial_end:
            problems.append(f"{email.subject!r}: trial_end {fact.trial_end} != {rule.trial_end}")
    assert not problems, "\n".join(problems)
