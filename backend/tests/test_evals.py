"""The synthetic eval set (backend/evals) loads, its labels hang together, and the harness runs end to end with
rules only. Offline and quick (about a second); the live run is `python -m evals.run --models on`."""

import copy
import json

import pytest

from evals import dataset, report, score
from evals import run as eval_run

pytestmark = pytest.mark.evals


@pytest.fixture(scope="module")
def people():
    return dataset.load()


def test_dataset_is_synthetic_and_big_enough(people):
    stats = dataset.stats(people)
    assert stats["people"] == 3
    assert stats["emails"] >= 100
    assert all(p["synthetic"] is True for p in people)
    assert (dataset.DATA_DIR / "README.md").read_text(encoding="utf-8").count("synthetic") >= 1
    # No real people: every person's own address is a reserved example domain.
    assert all(p["person"]["address"].split("@")[1].startswith("example.") for p in people)


def test_labels_are_consistent(people):
    assert [msg for p in people for msg in dataset.problems(p)] == []


def test_every_labelled_subscription_has_something_behind_it(people):
    for p in people:
        for s in p["labels"]["subscriptions"]:
            if s["bank"]:
                assert dataset._bank_charges(p, s), f"{s['id']}: no transactions"
            else:
                assert s["evidence_emails"], f"{s['id']}: email-only but no email"


def test_problems_catches_a_broken_label(people):
    broken = copy.deepcopy(people[0])
    broken["labels"]["subscriptions"][0]["amount"] += 5
    broken["labels"]["findings"][0]["evidence"]["transactions"] = ["no-such-id"]
    found = dataset.problems(broken)
    assert any("latest charge" in m for m in found)
    assert any("no-such-id" in m for m in found)


def test_name_and_amount_matching():
    assert score.names_match(["max"], "Max Com")
    assert score.names_match(["xfinity", "comcast"], "Xfinity (Comcast)")
    assert score.names_match(["t mobile"], "T-Mobile")
    assert not score.names_match(["max"], "Maxwell House")
    fixed = {"amount": 20.00, "variable": False, "status": "active"}
    assert score.amount_gap(fixed, {"amount": 20.50, "monthly_cost": 20.5}) == pytest.approx(0.5)
    assert score.amount_gap(fixed, {"amount": 20.61, "monthly_cost": 20.61}) is None
    trial = {"amount": 7.99, "variable": False, "status": "trial"}
    assert score.amount_gap(trial, {"amount": None, "monthly_cost": 0.0}) == 0.0


def test_harness_runs_rules_only_end_to_end(people, tmp_path):
    result = eval_run.evaluate("off", people)
    assert result["mode"] == "models-off"
    assert result["dataset"]["synthetic"] is True
    assert result["cost"]["model_calls"] == 0 and result["cost"]["cost_usd"] == 0
    tot = result["totals"]
    assert tot["emails"]["total"] == dataset.stats(people)["emails"]
    assert tot["subscriptions"]["labelled"] == sum(len(p["labels"]["subscriptions"]) for p in people)
    assert 0 < tot["subscriptions"]["named_recall"] <= 1
    assert tot["injection"]["emails"] == 1
    assert all(p["facts_hooked"] for p in result["per_person"])
    # Every failure says what was expected and what happened.
    assert result["failures"] and all(f["expected"] and f["got"] for f in result["failures"])

    (tmp_path / "2099-01-01-models-off.json").write_text(json.dumps(result, default=str), encoding="utf-8")
    doc = report.build(tmp_path, doc=tmp_path / "EVAL.md")
    text = doc.read_text(encoding="utf-8")
    assert "synthetic" in text and "python -m evals.run" in text and "Every failure" in text
