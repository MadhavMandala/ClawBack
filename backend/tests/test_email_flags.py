"""GET /api/email-flags: what the Gmail add-on marks. One flag per merchant with money in it, matched by sender
domain in the browser. No email text, and nothing for items you kept, cancelled or dismissed."""

from conftest import new_session

from clawback import sessions
from clawback.store import store


def _flags(client) -> dict[str, dict]:
    return {f["merchant"]: f for f in client.get("/api/email-flags").json()["flags"]}


def test_demo_month_flags(client):
    client.post("/api/demo/seed")
    flags = _flags(client)
    netflix = flags["Netflix"]
    assert netflix["domains"] == ["netflix.com"]
    assert netflix["amount"] == 17.99 and netflix["period"] == "month"
    assert any("$15.49 to $17.99" in line for line in netflix["lines"])
    assert netflix["link"].endswith("/dashboard?focus=sub:merchant-netflix")
    assert flags["Orangetheory Fitness"]["domains"] == ["orangetheory.com"]
    best_buy = flags["Best Buy"]
    assert best_buy["domains"] == ["bestbuy.com"] and best_buy["period"] == "once" and best_buy["amount"] > 0
    assert best_buy["target"].startswith("finding:price-drop-")


def test_biggest_first(client):
    client.post("/api/demo/seed")
    amounts = [f["amount"] for f in client.get("/api/email-flags").json()["flags"]]
    assert amounts == sorted(amounts, reverse=True)


def test_no_email_text_in_a_flag(client):
    client.post("/api/demo/seed")
    u = store.user("demo")
    texts = [x for e in u.emails for x in (e.subject, e.sender, e.body_text) if x and len(x) > 12]
    payload = client.get("/api/email-flags").text
    assert texts and not any(t in payload for t in texts)
    for f in client.get("/api/email-flags").json()["flags"]:
        assert set(f) == {"target", "merchant", "domains", "lines", "amount", "period", "link"}


def test_kept_cancelled_and_dismissed_give_no_flag(client):
    client.post("/api/demo/seed")
    flags = _flags(client)
    client.post(f"/api/subscriptions/{flags['Netflix']['target'][4:]}/keep")
    client.post(f"/api/subscriptions/{flags['Orangetheory Fitness']['target'][4:]}/cancelled")
    client.post(f"/api/findings/{flags['Best Buy']['target'][8:]}/dismiss")
    assert not {"Netflix", "Orangetheory Fitness", "Best Buy"} & set(_flags(client))


def test_bank_fees_have_no_flag(client):
    client.post("/api/demo/seed")
    assert "Your bank" not in _flags(client)


def test_token_sees_its_own_session(api):
    h = new_session(api)
    api.post("/api/demo/seed", headers=h)
    token = api.post("/api/addon-token", headers=h).json()["token"]
    r = api.get("/api/email-flags", headers={sessions.ADDON_HEADER: token})
    assert "Netflix" in {f["merchant"] for f in r.json()["flags"]}
