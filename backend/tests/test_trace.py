from datetime import date

from clawback import demo_data
from clawback.pipeline.run import run
from clawback.store import store
from clawback.trace import record, start_run, view

TODAY = date(2026, 10, 22)


def seed_test_user():
    u = store.reset("test")
    u.transactions = demo_data.transactions(TODAY)
    u.emails = demo_data.emails(TODAY)


def test_run_keeps_on_click_rows():
    seed_test_user()
    record("test", "cancel_email", "nvidia/Nemotron-3-Ultra-550b-a55b")
    run("test", TODAY)
    stages = [s.stage for s in store.user("test").trace]
    assert "cancel_email" in stages and stages.count("triage") == 1


def test_on_click_rows_capped_at_20():
    store.reset("test")
    for i in range(25):
        record("test", "alternatives", "tavily", note=str(i))
    start_run("test")
    assert [s.note for s in store.user("test").trace] == [str(i) for i in range(5, 25)]


def test_view_puts_pipeline_first_then_newest_click():
    store.reset("test")
    record("test", "alternatives", "tavily", note="a")
    record("test", "triage", "rules")
    record("test", "cancel_email", "ultra", note="b")
    assert [s.stage for s in view("test")] == ["triage", "cancel_email", "alternatives"]


def test_run_keeps_sync_rows_and_click_rows_but_rebuilds_its_own():
    seed_test_user()
    record("test", "sync", "nylas", note="12 emails")
    record("test", "bill offers", "tavily")
    run("test", TODAY)
    run("test", TODAY)
    rows = [(s.stage, s.engine) for s in store.user("test").trace]
    assert ("sync", "nylas") in rows and ("bill offers", "tavily") in rows
    assert [s for s, _ in rows].count("recurring") == 1


def test_switching_to_real_data_drops_demo_rows_but_keeps_sync_rows():
    seed_test_user()
    record("test", "cancel_email", "nvidia/Nemotron-3-Ultra-550b-a55b")
    record("test", "sync", "plaid")
    store.use_real_data("test")
    assert [(s.stage, s.engine) for s in store.user("test").trace] == [("sync", "plaid")]
