"""The gym workflow, part 2: the cancellation email is sent from the user's own inbox after a click, and never to a
real business from the demo. Connecting email from Send keeps the demo month; the Connect menu still leaves it."""

from urllib.parse import parse_qs, urlparse

import pytest

from clawback import connect, connections, gyms
from clawback.store import store

STUDIO = gyms.demo_gym()


def _sign_in(client, purpose=None):
    params = {"purpose": purpose} if purpose else {}
    url = client.get("/api/connect/email", params=params).json()["auth_url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    return client.get("/api/connect/email/callback", params={"code": "good-code", "state": state},
                      follow_redirects=False).headers["location"]


def _gym(client):
    return next(s for s in client.get("/api/subscriptions").json() if s["merchant"] == "Orangetheory Fitness")


@pytest.fixture()
def demo_client(client, fake):
    client.post("/api/demo/seed")
    return client


def test_send_sign_in_keeps_the_demo(demo_client):
    assert _sign_in(demo_client, "send").endswith("?connected=email-send")
    assert demo_client.get("/api/connections").json()["mode"] == "demo"
    assert _gym(demo_client)  # the demo month is still there
    assert connections.get("demo").email.send_only is True


def test_connect_menu_sign_in_still_leaves_the_demo(demo_client):
    assert _sign_in(demo_client).endswith("?connected=email")
    assert demo_client.get("/api/connections").json()["mode"] == "real"


def test_cancel_prep_for_the_gym_offers_send(demo_client):
    _sign_in(demo_client, "send")
    prep = demo_client.post(f"/api/subscriptions/{_gym(demo_client)['id']}/cancel-prep").json()
    send = prep["send"]
    assert send["to_shown"] == STUDIO["cancel"]["email"]
    assert (send["goes_to"], send["test"], send["connected"]) == ("me@example.com", True, True)
    assert prep["email"]["to"] == STUDIO["cancel"]["email"] and prep["email"]["subject"]
    assert any("30 days" in step for step in prep["how_to"])


def test_demo_send_goes_to_yourself_whatever_the_client_says(demo_client, fake):
    _sign_in(demo_client, "send")
    gym = _gym(demo_client)
    r = demo_client.post(f"/api/subscriptions/{gym['id']}/send-email",
                         json={"subject": "Cancel my membership", "body": "Please cancel.", "to": "owner@real-gym.com"})
    assert r.status_code == 200, r.text
    assert r.json()["sent_to"] == "me@example.com" and r.json()["test"] is True
    [msg] = fake.nylas.sent
    assert msg["to"] == [{"email": "me@example.com"}] and msg["subject"].startswith("[ClawBack test] ")
    assert _gym(demo_client)["status"] == "cancel_pending"


def test_send_without_an_inbox_is_refused(demo_client, fake):
    gym = _gym(demo_client)
    r = demo_client.post(f"/api/subscriptions/{gym['id']}/send-email", json={"subject": "s", "body": "b"})
    assert r.status_code == 409 and fake.nylas.sent == []
    assert _gym(demo_client)["status"] == gym["status"]


def test_send_without_permission_says_reconnect(demo_client, fake):
    _sign_in(demo_client, "send")
    fake.nylas.send_status = 403
    gym = _gym(demo_client)
    r = demo_client.post(f"/api/subscriptions/{gym['id']}/send-email", json={"subject": "s", "body": "b"})
    assert r.status_code == 403 and "Reconnect email to allow sending" in r.text
    assert _gym(demo_client)["status"] == gym["status"]


def test_restore_ignores_a_send_only_connection(demo_client):
    _sign_in(demo_client, "send")
    assert connect.restore("demo") is False
    assert store.user("demo").mode == "demo"
