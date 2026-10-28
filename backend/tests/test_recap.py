"""The monthly recap: an email to yourself, from your own inbox, with what ClawBack saved you. Off until turned on;
every number comes from the recovered-money history; the nightly job sends last month's once."""

from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import connect_both, new_session, user_of

from clawback import nightly, recap
from clawback.store import store


def _sign_in(client, purpose="send"):
    url = client.get("/api/connect/email", params={"purpose": purpose}).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    client.get("/api/connect/email/callback", params={"code": "good-code", "state": state}, follow_redirects=False)


@pytest.fixture()
def demo_client(client, fake):
    client.post("/api/demo/seed")
    return client


def test_off_until_turned_on_with_a_preview(demo_client):
    r = demo_client.get("/api/recap").json()
    assert r["enabled"] is False and r["next_send"] is None
    assert r["recap"]["subject"].startswith("[ClawBack demo] ")
    assert "<html" in r["recap"]["html"] and "Next up" in r["recap"]["text"]


def test_numbers_come_from_the_recovered_history(demo_client):
    totals = demo_client.get("/api/recovered").json()["totals"]
    r = recap.build("demo")
    assert r["saved_month"] == totals["cancelled_monthly"] > 0  # the demo's Calm, still cancelled
    assert r["saved_total"] == totals["cancelled_saved"]
    assert r["could_save_monthly"] == demo_client.get("/api/summary").json()["potential_monthly_savings"]
    assert any("Calm" in h["title"] for h in r["happened"])


def test_next_up_names_the_dashboards_three_cards(demo_client):
    show = demo_client.get("/api/showcase").json()
    subs = {s["id"]: s["merchant"] for s in demo_client.get("/api/subscriptions").json()}
    titles = " | ".join(n["title"] for n in recap.build("demo")["next_up"])
    assert subs[show["gym"]["sub_id"]] in titles and subs[show["streaming"]["sub_id"]] in titles
    if show["price"] and show["price"].get("finding_id"):
        assert "price drop" in titles


def test_a_past_month_only_counts_what_had_happened_by_then(demo_client):
    calm = next(e for e in store.user("demo").recovered.values() if e.kind == "cancelled_subscription")
    before = recap.previous_month(calm.on)
    r = recap.build("demo", before)
    assert r["saved_month"] == 0 and r["saved_total"] == 0 and r["partial"] is False
    assert recap.build("demo", recap.month_start(calm.on))["saved_total"] == calm.monthly  # its first month: one charge


def test_a_month_that_hasnt_started_is_refused(demo_client):
    nxt = recap.next_month(date.today())
    assert demo_client.get("/api/recap", params={"month": f"{nxt:%Y-%m}"}).status_code == 400
    assert demo_client.get("/api/recap", params={"month": "October"}).status_code == 400


def test_send_goes_to_yourself_as_html(demo_client, fake):
    _sign_in(demo_client)
    r = demo_client.post("/api/recap/send")
    assert r.status_code == 200, r.text
    assert r.json()["sent_to"] == "me@example.com"
    [msg] = fake.nylas.sent
    assert msg["to"] == [{"email": "me@example.com"}] and msg["is_plaintext"] is False
    assert msg["subject"].startswith("[ClawBack demo] ") and "<html" in msg["body"]


def test_send_without_an_inbox_is_refused(demo_client, fake):
    assert demo_client.post("/api/recap/send").status_code == 409 and fake.nylas.sent == []


def test_send_without_permission_says_reconnect(demo_client, fake):
    _sign_in(demo_client)
    fake.nylas.send_status = 403
    r = demo_client.post("/api/recap/send")
    assert r.status_code == 403 and "Reconnect email to allow sending" in r.text


def test_turning_it_on_waits_for_the_next_whole_month(demo_client, fake):
    _sign_in(demo_client)
    on = demo_client.post("/api/settings/recap", json={"enabled": True}).json()
    assert on["enabled"] is True and on["next_send"] == recap.next_month(date.today()).isoformat()
    assert recap.send_due("demo", date.today()) is False and fake.nylas.sent == []  # nothing back-dated
    assert recap.send_due("demo", recap.next_month(date.today())) is True  # this month, on the 1st of the next
    assert recap.send_due("demo", recap.next_month(date.today())) is False  # once
    assert len(fake.nylas.sent) == 1


def test_turning_it_off_stops_it(demo_client, fake):
    _sign_in(demo_client)
    demo_client.post("/api/settings/recap", json={"enabled": True})
    demo_client.post("/api/settings/recap", json={"enabled": False})
    assert recap.send_due("demo", recap.next_month(date.today())) is False and fake.nylas.sent == []


def test_the_choice_survives_a_demo_reset(demo_client):
    demo_client.post("/api/settings/recap", json={"enabled": True})
    demo_client.post("/api/demo/seed")
    assert demo_client.get("/api/recap").json()["enabled"] is True


def test_nightly_sends_last_months_recap_once(api, fake):
    h = new_session(api)
    connect_both(api, h)
    assert api.post("/api/settings/recap", json={"enabled": True}, headers=h).status_code == 200
    first = recap.next_month(date.today())

    code, line = nightly.run(today=first)
    assert code == 0 and "1 monthly recaps sent" in line, line
    [msg] = fake.nylas.sent
    assert msg["to"] == [{"email": "me@example.com"}] and msg["is_plaintext"] is False
    assert store.user(user_of(h)).recap_sent == recap.month_key(recap.previous_month(first))

    assert "0 monthly recaps sent" in nightly.run(today=first)[1]
    assert len(fake.nylas.sent) == 1
