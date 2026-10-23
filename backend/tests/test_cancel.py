import json

import pytest

from clawback.models import Subscription
from clawback.pipeline.cancel import write_email
from clawback.store import store

ULTRA = "nvidia/Nemotron-3-Ultra-550b-a55b"
HULU = Subscription(id="hulu", merchant="Hulu", category="video_streaming", monthly_cost=18.99)


@pytest.fixture(autouse=True)
def fresh_user():
    store.reset("t")


def test_cancel_email_from_ultra(fake_llm):
    fake_llm.script = {ULTRA: ['{"subject":"Cancel my Hulu","body":"Hi, please cancel. Account email: [your account email]"}']}
    mail = write_email("t", HULU)
    assert mail["written_by"] == ULTRA and mail["subject"] == "Cancel my Hulu"
    assert fake_llm.calls[0]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


@pytest.mark.parametrize("body", ["Cancel at https://evil.example [your account email]", "Cancel please, no placeholder"])
def test_bad_model_email_uses_template(fake_llm, body):
    fake_llm.script = {ULTRA: [json.dumps({"subject": "s", "body": body})]}
    assert write_email("t", HULU)["written_by"] == "template"


def test_template_without_key():
    assert write_email("t", HULU)["written_by"] == "template"


@pytest.mark.parametrize("body", [
    "Please cancel; manage it at www.hulu.com/account. [your account email]",
    "Please cancel; see hulu.com/cancel. [your account email]",
    "Please cancel account #48213 effective October 31. [your account email]",
])
def test_model_email_with_bare_link_or_invented_numbers_uses_template(fake_llm, body):
    fake_llm.script = {ULTRA: [json.dumps({"subject": "Cancel", "body": body})]}
    assert write_email("t", HULU)["written_by"] == "template"


def test_model_email_may_repeat_fact_numbers(fake_llm):
    body = "Please cancel my plan ($18.99 a month). [your account email]"
    fake_llm.script = {ULTRA: [json.dumps({"subject": "Cancel Hulu", "body": body})]}
    assert write_email("t", HULU)["written_by"] == ULTRA
