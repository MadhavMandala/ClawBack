"""Gyms ClawBack can check visits for (rules/gyms.json), and the distance check for Google Maps Timeline visits.

A gym in this file is the only kind of business a cancellation email is ever sent to, and only in real mode.
"""

from __future__ import annotations

import json
import math
from datetime import date
from functools import cache
from pathlib import Path

from .models import Subscription

RADIUS_M = 150  # a Timeline visit this close to the studio counts as a visit


@cache
def _book() -> dict:
    return json.loads((Path(__file__).parent / "rules" / "gyms.json").read_text())


def all_gyms() -> list[dict]:
    return _book()["gyms"]


def by_id(gym_id: str) -> dict | None:
    return next((g for g in all_gyms() if g["id"] == gym_id), None)


def demo_gym() -> dict:
    return next(g for g in all_gyms() if g.get("demo"))


def for_subscription(sub: Subscription, demo: bool = True) -> dict | None:
    """The studio for a gym subscription: by chain name. In real mode the demo studio never matches."""
    name = sub.merchant.lower()
    return next((g for g in all_gyms() if g["chain"].lower() in name and (demo or not g.get("demo"))), None)


def _meters(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def visits_near(visits, gym: dict, meters: float = RADIUS_M) -> list[date]:
    """The dates of visits within `meters` of the studio, oldest first, one per day."""
    return sorted({v.start for v in visits if _meters(v.lat, v.lng, gym["lat"], gym["lng"]) <= meters})
