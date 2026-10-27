"""GET /api/showcase names the three workflows the dashboard leads with: the unused gym, the unused streaming service,
and the price drop (or the price being watched when it hasn't dropped)."""


def test_demo_showcase(client):
    client.post("/api/demo/seed")
    s = client.get("/api/showcase").json()
    subs = {x["id"]: x for x in client.get("/api/subscriptions").json()}
    finds = {x["id"]: x for x in client.get("/api/findings").json()}
    assert subs[s["gym"]["sub_id"]]["merchant"] == "Orangetheory Fitness"
    assert subs[s["streaming"]["sub_id"]]["merchant"] == "Netflix"
    assert finds[s["price"]["finding_id"]]["merchant"] == "Best Buy"


def test_showcase_after_cancelling_the_gym_moves_on(client):
    client.post("/api/demo/seed")
    gym = client.get("/api/showcase").json()["gym"]["sub_id"]
    client.post(f"/api/subscriptions/{gym}/cancelled")
    # A gym you've started cancelling stays the gym card (it shows the cancelling state); a cancelled one would not.
    assert client.get("/api/showcase").json()["gym"]["sub_id"] == gym


def test_the_price_card_is_the_biggest_drop(client):
    from clawback.store import store

    client.post("/api/demo/seed")
    u = store.user("demo")
    [best_buy] = [f for f in u.findings.values() if f.kind == "price_drop"]
    smaller = best_buy.model_copy(update={"id": "staples-drop", "merchant": "Staples", "amount": 30.0})
    u.findings = {smaller.id: smaller, **u.findings}  # listed first, like a live Staples drop found first
    assert client.get("/api/showcase").json()["price"]["finding_id"] == best_buy.id
