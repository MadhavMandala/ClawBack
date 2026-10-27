"""The price-drop workflow: a Best Buy purchase in the demo month against today's live bestbuy.com price, with a plain
"simulated" label when the live check can't run, and a "no drop today" record instead of a vanished card."""

from datetime import date

import pytest

from clawback import demo, demo_data
from clawback.findings.refunds import PriceCheck
from clawback.tools import prices

TODAY = date(2026, 10, 27)
URL = "https://www.bestbuy.com/product/apple-airpods-pro-2/JJGCQ88C8X"


@pytest.fixture(autouse=True)
def fresh():
    demo.clear()
    yield
    demo.clear()


def _airpods(u):
    return next((f for f in u.findings.values() if f.kind == "price_drop"), None)


def test_demo_has_one_best_buy_charge():
    best_buy = [t for t in demo_data.transactions(TODAY) if t.description.startswith("BEST BUY")]
    assert len(best_buy) == 1 and best_buy[0].amount == 249.00


def test_without_keys_the_price_is_simulated_and_says_so():
    f = _airpods(demo.template(TODAY))
    assert f.merchant == "Best Buy" and f.details["how"] == "simulated"
    assert "simulated" in f.title.lower()


def test_live_price_below_paid_is_a_live_finding(monkeypatch):
    monkeypatch.setattr(prices, "live_available", lambda: True)
    monkeypatch.setattr(prices, "live_price", lambda *a, **k: PriceCheck(price=164.99, how="live", url=URL))
    f = _airpods(demo.template(TODAY))
    assert f.details["how"] == "live" and f.details["price_url"] == URL and f.amount == 84.01
    assert "simulated" not in f.title.lower() and f.details["checked_on"] == TODAY.isoformat()


def test_live_price_not_below_paid_is_watched_not_dropped(monkeypatch):
    monkeypatch.setattr(prices, "live_available", lambda: True)
    monkeypatch.setattr(prices, "live_price", lambda *a, **k: PriceCheck(price=259.00, how="live", url=URL))
    u = demo.template(TODAY)
    assert _airpods(u) is None
    [w] = [x for x in u.price_watch if x["store"] == "Best Buy"]  # the fake answers every store the same
    assert (w["store"], w["paid"], w["price_now"], w["url"], w["how"]) == ("Best Buy", 249.00, 259.00, URL, "live")


@pytest.mark.parametrize("url", [
    "https://www.bestbuy.com/product/bose-quietcomfort-ultra/J7C5V6W7LP/sku/6642778/openbox",
    "https://www.bestbuy.com/product/sony-wh-1000xm5/J7XSRH5CXG/sku/11898759?ref=212&loc=marketplace",
])
def test_open_box_and_marketplace_listings_are_not_the_price(url):
    assert prices.other_condition("Sony WH-1000XM5 Headphones", {"title": "Headphones", "url": url})


def test_api_shows_the_price_check_but_not_the_private_details(client):
    client.post("/api/demo/seed")
    [drop] = [f for f in client.get("/api/findings").json() if f["kind"] == "price_drop"]
    pc = drop["price_check"]
    assert (pc["store"], pc["paid"], pc["how"]) == ("Best Buy", 249.0, "simulated") and pc["item"] == "Apple AirPods Pro 2"
    assert "details" not in drop and "order_number" not in pc


def test_a_failed_live_check_is_retried_after_ten_minutes(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(prices.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(prices, "live_available", lambda: True)
    answers = [None, PriceCheck(price=164.99, how="live", url=URL)]
    monkeypatch.setattr(prices, "_live_price", lambda *a, **k: answers.pop(0))
    prices._checked.clear()
    assert prices.live_price("u", "Best Buy", "Apple AirPods Pro 2", "bestbuy.com") is None
    assert prices.live_price("u", "Best Buy", "Apple AirPods Pro 2", "bestbuy.com") is None  # still cached
    clock["t"] += 11 * 60
    assert prices.live_price("u", "Best Buy", "Apple AirPods Pro 2", "bestbuy.com").price == 164.99


def test_demo_rebuilds_when_its_price_came_out_simulated(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(demo.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(prices, "live_available", lambda: True)
    live = {"ok": False}
    monkeypatch.setattr(prices, "live_price",
                        lambda *a, **k: PriceCheck(price=164.99, how="live", url=URL) if live["ok"] else None)
    assert _airpods(demo.template(TODAY)).price_check["how"] == "simulated"
    live["ok"] = True
    clock["t"] += 11 * 60
    assert _airpods(demo.template(TODAY)).price_check["how"] == "live"
