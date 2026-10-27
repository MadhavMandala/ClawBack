"""Google Maps Timeline exports (Android: Settings > Location > Timeline > Export; iPhone: Maps > Settings > Personal
content > Export Timeline data). Google offers no API for location history any more, so this file is the source.

Two shapes are read: {"semanticSegments": [...]} and a bare array of segments. Only `visit` segments are used, with
their place's coordinates ("40.51°, -74.41°" or "geo:40.51,-74.41") and the visit's start date. Everything else in
the file (paths, raw signals, other places) is ignored, and the caller keeps only the dates of gym visits.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Visit:
    lat: float
    lng: float
    start: date


def _latlng(place) -> tuple[float, float] | None:
    text = place.get("latLng") if isinstance(place, dict) else place
    if not isinstance(text, str):
        return None
    nums = _NUM.findall(text)
    if len(nums) < 2:
        return None
    lat, lng = float(nums[0]), float(nums[1])
    return (lat, lng) if -90 <= lat <= 90 and -180 <= lng <= 180 else None


def parse(raw: bytes) -> list[Visit]:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("That isn't a Google Maps Timeline export (not JSON).") from exc
    segments = data.get("semanticSegments") if isinstance(data, dict) else data
    if not isinstance(segments, list):
        raise ValueError("That isn't a Google Maps Timeline export (no semanticSegments).")
    out: list[Visit] = []
    for seg in segments:
        if not isinstance(seg, dict) or not isinstance(seg.get("visit"), dict):
            continue
        cand = seg["visit"].get("topCandidate") or {}
        where = _latlng(cand.get("placeLocation")) if isinstance(cand, dict) else None
        start = str(seg.get("startTime") or "")[:10]
        try:
            day = date.fromisoformat(start)
        except ValueError:
            continue
        if where:
            out.append(Visit(lat=where[0], lng=where[1], start=day))
    return out
