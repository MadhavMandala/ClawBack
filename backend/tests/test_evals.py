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


# --- The held-out set (evals/holdout) ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def holdout():
    return dataset.load(dataset.HOLDOUT_DIR)


def test_holdout_is_synthetic_separate_and_big_enough(holdout, people):
    stats = dataset.stats(holdout)
    assert stats["people"] == 3
    assert stats["emails"] >= 90
    assert all(p["synthetic"] is True and p["set"] == "holdout" for p in holdout)
    assert all(len(p["transactions"]) >= 150 for p in holdout)
    readme = (dataset.HOLDOUT_DIR / "README.md").read_text(encoding="utf-8")
    assert "synthetic" in readme and "held-out" in readme
    assert all(p["person"]["address"].split("@")[1].startswith("example.") for p in holdout)
    # Different people from the main set, and the main set's files are not picked up as held-out ones.
    assert {p["person"]["id"] for p in holdout}.isdisjoint({p["person"]["id"] for p in people})
    assert {p["person"]["address"] for p in holdout}.isdisjoint({p["person"]["address"] for p in people})
    assert dataset.files(dataset.HOLDOUT_DIR) and all(f.name.startswith("h") for f in dataset.files(dataset.HOLDOUT_DIR))
    assert dataset.fingerprint(dataset.HOLDOUT_DIR) != dataset.fingerprint()


def test_holdout_labels_are_consistent(holdout):
    assert [msg for p in holdout for msg in dataset.problems(p)] == []
    for p in holdout:
        for s in p["labels"]["subscriptions"]:
            if s["bank"]:
                assert dataset._bank_charges(p, s), f"{s['id']}: no transactions"
            else:
                assert s["evidence_emails"], f"{s['id']}: email-only but no email"


def test_holdout_files_match_the_builder(holdout):
    from evals import build_holdout

    built = build_holdout.build()
    on_disk = {f.name: f.read_text(encoding="utf-8").replace("\r\n", "\n") for f in dataset.files(dataset.HOLDOUT_DIR)}
    assert set(built) == set(on_disk)
    assert all(build_holdout.dump(person) == on_disk[name] for name, person in built.items())


def test_charge_ids_pick_a_labels_own_charges(holdout):
    kayla = next(p for p in holdout if p["person"]["id"] == "h3")
    subs = {s["id"]: s for s in kayla["labels"]["subscriptions"]}
    duo, head = dataset._bank_charges(kayla, subs["duolingo"]), dataset._bank_charges(kayla, subs["headspace"])
    # Same descriptor, same price, different charges.
    assert {t["amount"] for t in duo} == {t["amount"] for t in head} == {12.99}
    assert not {t["id"] for t in duo} & {t["id"] for t in head}
    broken = copy.deepcopy(kayla)
    broken["labels"]["subscriptions"][1]["charge_ids"] = ["no-such-id"]
    assert any("no-such-id" in m for m in dataset.problems(broken))


def test_harness_runs_holdout_rules_only_and_report_keeps_sets_apart(people, holdout, tmp_path):
    held = eval_run.evaluate("off", holdout, set_name="holdout")
    assert held["set"] == "holdout" and held["dataset"]["set"] == "holdout"
    assert held["dataset"]["fingerprint"] == dataset.fingerprint(dataset.HOLDOUT_DIR)
    assert held["totals"]["emails"]["total"] == dataset.stats(holdout)["emails"]
    assert held["totals"]["injection"]["emails"] == 2
    assert held["cost"]["model_calls"] == 0
    assert eval_run.result_name(held) == f"{held['run_date']}-holdout-models-off"
    main = eval_run.evaluate("off", people)
    assert eval_run.result_name(main) == f"{main['run_date']}-models-off"

    only_main, both = tmp_path / "main", tmp_path / "both"
    for d in (only_main, both):
        d.mkdir()
        (d / "2099-01-01-models-off.json").write_text(json.dumps(main, default=str), encoding="utf-8")
    (both / "2099-01-01-holdout-models-off.json").write_text(json.dumps(held, default=str), encoding="utf-8")
    assert [r["_file"] for r in report.latest(both).values()] == ["2099-01-01-models-off.json"]
    assert [r["_file"] for r in report.latest(both, "holdout").values()] == ["2099-01-01-holdout-models-off.json"]

    main_doc = report.build(only_main, doc=tmp_path / "main.md").read_text(encoding="utf-8")
    both_doc = report.build(both, doc=tmp_path / "both.md").read_text(encoding="utf-8")
    main_unchanged = both_doc.startswith(main_doc)
    assert main_unchanged, "the main set's section changed when held-out results were added"
    held_part = both_doc[len(main_doc):]
    assert f"## {report.HOLDOUT_TITLE}" in held_part and "synthetic" in held_part
    # Totals only: no item-level failures or trap names for the held-out set.
    assert "Every failure" not in held_part
    trap_ids = [t["id"] for p in holdout for t in p["labels"]["traps"]]
    assert not any(t in held_part for t in trap_ids)


def test_run_set_option_writes_holdout_results(monkeypatch, tmp_path):
    monkeypatch.setattr(eval_run, "RESULTS_DIR", tmp_path)
    assert eval_run.main(["--set", "holdout", "--models", "off", "--no-report"]) == 0
    files = [f.name for f in tmp_path.glob("*.json")]
    assert len(files) == 1 and files[0].endswith("-holdout-models-off.json")
