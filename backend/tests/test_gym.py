"""The gym workflow, part 1: Orangetheory in the rules data, Google Maps Timeline parsing that keeps only gym visits,
and the rule that flags a gym you stopped going to."""

import json
from datetime import date, timedelta

import pytest

from clawback import demo, demo_data, gyms
from clawback.models import Subscription
from clawback.pipeline.run import run
from clawback.sources import timeline
from clawback.store import serialize, store

TODAY = date(2026, 10, 27)
STUDIO = gyms.demo_gym()


def _seg(lat, lng, start):
    return {"startTime": f"{start}T18:00:00.000-04:00", "endTime": f"{start}T19:00:00.000-04:00",
            "visit": {"topCandidate": {"placeLocation": {"latLng": f"{lat}°, {lng}°"}}}}


def test_demo_gym_is_in_the_rules():
    assert STUDIO["chain"] == "Orangetheory Fitness" and STUDIO["cancel"]["method"] == "email"
    assert STUDIO["cancel"]["email"].endswith(".test")  # never a real studio's address in the demo


def test_parse_both_shapes_and_skip_bad_segments():
    segs = [_seg(STUDIO["lat"], STUDIO["lng"], "2026-09-01"), {"visit": {}}, {"timelinePath": []},
            {"startTime": "nope", "visit": {"topCandidate": {"placeLocation": {"latLng": "x"}}}}]
    for raw in (json.dumps({"semanticSegments": segs}), json.dumps(segs)):
        visits = timeline.parse(raw.encode())
        assert [(round(v.lat, 4), v.start) for v in visits] == [(round(STUDIO["lat"], 4), date(2026, 9, 1))]


def test_parse_geo_form_and_rejects_non_json():
    raw = json.dumps([{"startTime": "2026-09-02T07:00:00Z",
                       "visit": {"topCandidate": {"placeLocation": f"geo:{STUDIO['lat']},{STUDIO['lng']}"}}}])
    assert len(timeline.parse(raw.encode())) == 1
    with pytest.raises(ValueError):
        timeline.parse(b"not json")


def test_visits_near_keeps_only_the_gym():
    near = timeline.Visit(lat=STUDIO["lat"] + 0.0005, lng=STUDIO["lng"], start=date(2026, 9, 1))  # ~55 m
    far = timeline.Visit(lat=STUDIO["lat"] + 0.01, lng=STUDIO["lng"], start=date(2026, 9, 2))  # ~1.1 km
    assert gyms.visits_near([near, far], STUDIO) == [date(2026, 9, 1)]


def _gym_sub():
    return Subscription(id="orangetheory", merchant="Orangetheory Fitness", category="fitness", monthly_cost=169.0)


@pytest.mark.parametrize("visits, level", [
    ([TODAY - timedelta(days=63), TODAY - timedelta(days=65)], "none"),       # nothing in 30 days, 0 in 60
    ([TODAY - timedelta(days=45)], "none"),                                    # nothing in 30 days, 1 in 60
    ([TODAY - timedelta(days=40), TODAY - timedelta(days=45)], "normal"),     # 2 in the last 60: still going
    ([TODAY - timedelta(days=3)], "normal"),
])
def test_visit_rule(visits, level):
    from clawback.pipeline.usage import gym_usage
    summary = gym_usage(_gym_sub(), STUDIO, visits, TODAY)
    assert summary.level == level


def test_demo_flags_the_gym():
    demo.clear()
    u = demo.template(TODAY)
    gym = next(s for s in u.subscriptions.values() if s.merchant == "Orangetheory Fitness")
    flag = next(f for f in gym.flags if f.kind == "unused")
    assert "no visits to orangetheory" in flag.message.lower() and "$169.00" in flag.message
    assert gym.monthly_cost == 169.0


def test_upload_keeps_only_gym_visit_dates(client):
    client.post("/api/demo/seed")
    segs = [_seg(STUDIO["lat"], STUDIO["lng"], "2026-08-20"), _seg(40.7128, -74.0060, "2026-08-21")]  # gym, then NYC
    r = client.post("/api/ingest/timeline", files={"file": ("Timeline.json", json.dumps(segs).encode(), "application/json")})
    assert r.status_code == 200, r.text
    assert client.get("/api/connections").json()["mode"] == "real"
    u = store.user("demo")
    assert u.gym_visits == {STUDIO["id"]: [date(2026, 8, 20)]}
    assert "40.7128" not in json.dumps(serialize(u), default=str)
