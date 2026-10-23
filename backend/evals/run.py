"""Run the ClawBack eval and write results.

    cd backend
    python -m evals.run --models off                      # rules only: no key, no network
    python -m evals.run --models on                       # live Nemotron tiers, as the pipeline uses them
    python -m evals.run --models both --all-ultra 24      # both, plus the all-Ultra counterfactual on 24 emails
    python -m evals.run --report                          # rebuild docs/EVAL.md from the saved results

Writes backend/evals/results/<date>-<mode>.json and rebuilds docs/EVAL.md from the newest result of each mode.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from . import adapter, costs, dataset, report, score

RESULTS_DIR = Path(__file__).resolve().parent / "results"
REPO = Path(__file__).resolve().parents[2]


@contextmanager
def models_mode(mode: str):
    """Rules only ("off") or live models ("on"). Tavily, Nylas and Plaid are never called by the eval: current
    prices come from the dataset, and the data is loaded directly instead of synced."""
    from clawback.config import settings

    names = ("nebius_api_key", "tavily_api_key", "nylas_client_id", "nylas_api_key", "plaid_client_id",
             "plaid_secret")
    saved = {n: getattr(settings, n) for n in names}
    try:
        for n in names:
            if n != "nebius_api_key" or mode == "off":
                setattr(settings, n, None)
        if mode == "on" and not settings.nebius_api_key:
            raise SystemExit("--models on needs NEBIUS_API_KEY (backend/.env or the environment).")
        yield
    finally:
        for n, v in saved.items():
            setattr(settings, n, v)


def git_info() -> dict:
    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return ""
    return {"commit": git("rev-parse", "--short", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "product_code_uncommitted": bool(git("status", "--porcelain", "--", "backend/clawback"))}


def injection_emails(person: dict) -> list[str]:
    return [c["email"] for t in person["labels"]["traps"] for c in t["checks"] if c["type"] == "injection"]


def headline(tot: dict, cost: dict, wall: float) -> dict:
    s, f, fi, e = tot["subscriptions"], tot["flags"], tot["findings"], tot["emails"]
    return {
        "subscriptions_named_recall": s["named_recall"], "subscriptions_charge_recall": s["charge_recall"],
        "subscriptions_precision": s["precision"], "false_subscriptions": s["false"],
        "flags_recall": f["recall"], "flags_precision": f["precision"], "flag_false_alarms": f["false_alarms"],
        "findings_recall": fi["recall"], "findings_precision": fi["precision"], "false_findings": fi["false"],
        "finding_amounts_exact": f"{fi['amount_exact']}/{fi['amount_scored']}",
        "email_accuracy": e["accuracy"], "email_signal_accuracy": e["signal_accuracy"],
        "false_signals": e["false_signals"],
        "injection_resisted": tot["injection"]["all_resisted"],
        "traps_passed": f"{tot['traps']['passed']}/{tot['traps']['total']}",
        "cost_usd": cost["cost_usd"], "cost_per_1000_emails_usd": cost["cost_per_1000_emails_usd"],
        "pipeline_s": round(wall, 2),
    }


def evaluate(mode: str, people: list[dict], repeat: int = 1) -> dict:
    """Run every person `repeat` times in one mode; details come from the first run, headline numbers from all."""
    n_emails = sum(len(p["emails"]) for p in people)
    runs = []
    with models_mode(mode):
        for r in range(repeat):
            adapter.clear_module_caches()
            people_out = []
            for person in people:
                pid = person["person"]["id"]
                uid = f"eval-{pid}-{mode}-{r}"
                out = adapter.run_person(person, uid)
                ablation = {eid: adapter.rerun_without(person, uid, {eid}) for eid in injection_emails(person)}
                people_out.append((person, out, score.score_person(person, out, ablation)))
            tot = score.totals([s for _, _, s in people_out])
            trace = [row for _, out, _ in people_out for row in out["trace"]]
            cost = costs.summarize(trace, n_emails)
            wall = sum(out["wall_s"] for _, out, _ in people_out)
            runs.append({"people": people_out, "totals": tot, "cost": cost, "wall": wall,
                         "headline": headline(tot, cost, wall)})
    first = runs[0]
    per_person = []
    for person, out, sc in first["people"]:
        pt = score.totals([sc])
        pc = costs.summarize(out["trace"], len(person["emails"]))
        per_person.append({
            "person": person["person"]["id"], "name": person["person"]["name"], "emails": len(person["emails"]),
            "transactions": len(person["transactions"]), "wall_s": out["wall_s"], "facts_hooked": out["facts_hooked"],
            "headline": headline(pt, pc, out["wall_s"]), "cost": {k: pc[k] for k in ("model_calls", "cost_usd",
                                                                                      "input_tokens", "output_tokens")},
            "pipeline_steps": pc["pipeline_steps"],
            "subscriptions": sc["subscriptions"], "false_subscriptions": sc["false_subscriptions"],
            "findings": sc["findings"], "false_findings": sc["false_findings"], "emails_detail": sc["emails"],
            "traps": sc["traps"], "injection": sc["injection"], "flags": sc["flags"],
            "info_prompts": sc["info_prompts"],
        })
    return {
        "mode": f"models-{mode}",
        "run_date": date.today().isoformat(),
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_info(),
        "dataset": {**dataset.stats(people), "fingerprint": dataset.fingerprint(), "synthetic": True},
        "settings": _settings(mode, repeat),
        "headline": first["headline"],
        "totals": first["totals"],
        "cost": first["cost"],
        "repeats": [r["headline"] for r in runs],
        "per_person": per_person,
        "failures": [f for _, _, sc in first["people"] for f in sc["failures"]],
    }


def _settings(mode: str, repeat: int) -> dict:
    from clawback import llm

    return {
        "models": "rules only (no NEBIUS_API_KEY)" if mode == "off" else "live Nemotron tiers on Nebius Token Factory",
        "tiers": dict(llm.MODELS), "prices_usd_per_1m_tokens": {m: list(p) for m, p in llm.PRICES.items()},
        "zero_data_retention": "on (Token Factory account setting)" if mode == "on" else "not applicable",
        "tavily": "not called: current prices come from each person's simulated price table",
        "repeat": repeat,
        "amount_tolerance": "max($0.50, 3%) of the labelled charge; variable bills 50% of their average",
    }


def write(result: dict, name: str | None = None) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name or result['run_date'] + '-' + result['mode']}.json"
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path


def print_headline(result: dict) -> None:
    h = result["headline"]
    print(f"\n{result['mode']}  ({result['dataset']['emails']} emails, {result['dataset']['people']} people, "
          f"commit {result['git']['commit']})")
    for k, v in h.items():
        print(f"  {k:<30} {v}")
    if len(result["repeats"]) > 1:
        print(f"  repeats: {len(result['repeats'])} (see the JSON for each)")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", choices=("off", "on", "both"), default="off")
    ap.add_argument("--repeat", type=int, default=1, help="runs per mode (live results vary a little run to run)")
    ap.add_argument("--all-ultra", type=int, nargs="?", const=24, default=0, metavar="N",
                    help="also send a sample of N emails (default 24) straight to Ultra, skipping triage")
    ap.add_argument("--ultra-thinking", choices=("on", "off"), default="on")
    ap.add_argument("--report", action="store_true", help="only rebuild docs/EVAL.md from saved results")
    ap.add_argument("--no-report", action="store_true", help="don't rebuild docs/EVAL.md")
    args = ap.parse_args(argv)

    if not args.report:
        people = dataset.load()
        bad = [p for person in people for p in dataset.problems(person)]
        if bad:
            print("The dataset has problems:\n  " + "\n  ".join(bad))
            return 2
        modes = ("off", "on") if args.models == "both" else (args.models,)
        for mode in modes:
            result = evaluate(mode, people, max(1, args.repeat))
            path = write(result)
            print_headline(result)
            print(f"  -> {path.relative_to(REPO)}")
        if args.all_ultra:
            from . import ultra

            with models_mode("on"):
                u = ultra.run(people, args.all_ultra, args.ultra_thinking == "on")
            u.update({"mode": "all-ultra", "run_date": date.today().isoformat(),
                      "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git": git_info(),
                      "dataset": {"fingerprint": dataset.fingerprint(), "synthetic": True}})
            path = write(u)
            print(f"\nall-ultra: {u['sample_size']} emails, ${u['cost_usd']:.4f} "
                  f"(extrapolated ${u['extrapolated_cost_per_1000_emails_usd']} per 1,000 emails), "
                  f"accuracy {u['accuracy']}\n  -> {path.relative_to(REPO)}")
    if not args.no_report:
        path = report.build(RESULTS_DIR)
        print(f"\nReport: {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
