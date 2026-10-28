"""The build-status board (clawback/features.py, GET /api/features): every MISSING item is on it, and it stays honest."""

import re
from pathlib import Path

from clawback.features import AREAS, FEATURES, NOT_STARTED, PHASE_IDS, features_payload
from clawback.missing import REGISTRY

REPO = Path(__file__).resolve().parents[2]
FIELDS = {"id", "area", "name", "phase", "summary", "next", "where", "missing_id", "priority"}


def test_ids_are_unique_and_kebab_case():
    ids = [f.id for f in FEATURES]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids)


def test_phases_and_areas_come_from_the_fixed_lists():
    assert PHASE_IDS == ("planned", "started", "built", "live")
    for f in FEATURES:
        assert f.phase in PHASE_IDS, f.id
        assert f.area in AREAS, f.id
    assert {f.area for f in FEATURES} == set(AREAS)  # no empty area on the board


def test_every_missing_item_is_linked_exactly_once_and_never_live():
    registry = {m["id"]: m for m in REGISTRY}
    linked = [f.missing_id for f in FEATURES if f.missing_id]
    assert sorted(linked) == sorted(registry)  # each MISSING id once, and no unknown ids
    for f in FEATURES:
        if f.missing_id:
            assert f.phase != "live", f"{f.id} is live but MISSING [{f.missing_id}] is still open"
            assert f.priority == registry[f.missing_id]["priority"], f.id
        else:
            assert f.priority is None, f.id


def test_where_paths_exist():
    for f in FEATURES:
        if f.where == NOT_STARTED:
            assert f.phase == "planned", f"{f.id} is {f.phase} but has no code"
            continue
        for part in f.where.split(", "):
            path = part.split(" ")[0]  # tolerate trailing route text such as "main.py POST /api/x"
            assert (REPO / path).exists(), f"{f.id}: {path} not found"


def test_every_unfinished_feature_says_what_is_next():
    for f in FEATURES:
        if f.phase != "live":
            assert f.next, f"{f.id} needs a next step"
        for text in (f.name, f.summary, f.next or ""):
            assert "—" not in text and "–" not in text, f"{f.id}: no dashes"
        assert len(f.name.split()) <= 6, f.id
        assert f.summary.endswith("."), f.id
        assert f.next is None or f.next.endswith("."), f.id


def test_features_route(client):
    body = client.get("/api/features").json()
    assert set(body) == {"phases", "areas", "features", "counts", "updated"}
    assert [p["id"] for p in body["phases"]] == ["planned", "started", "built", "live"]
    assert [p["label"] for p in body["phases"]] == ["Planned", "Started", "Built", "Live-tested"]
    assert all(set(p) == {"id", "label", "description"} and p["description"] for p in body["phases"])
    assert body["areas"] == list(AREAS)
    assert body["updated"] == "2026-10-27"
    assert len(body["features"]) == len(FEATURES)
    assert all(set(f) == FIELDS for f in body["features"])
    tally = {p: sum(1 for f in body["features"] if f["phase"] == p) for p in PHASE_IDS}
    assert body["counts"] == tally and sum(tally.values()) == len(FEATURES)
    assert body == features_payload()
