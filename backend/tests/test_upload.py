"""Uploading a statement: it replaces the made-up demo month with your own data, and uploading the same CSV again
adds nothing (so it can't invent "charged you twice" findings)."""

from clawback.sources.statements import parse_csv

CSV = (
    "Date,Description,Amount\n"
    "2026-08-03,PLANET FITNESS,-24.99\n"
    "2026-09-03,PLANET FITNESS,-24.99\n"
    "2026-10-03,PLANET FITNESS,-24.99\n"
    "2026-10-05,WHOLE FOODS MARKET,-61.20\n"
    "2026-10-05,WHOLE FOODS MARKET,-61.20\n"  # two real, identical purchases on one day
    "2026-10-09,SHELL OIL 5544,-40.00\n"
)


def _upload(client, text=CSV, name="statement.csv"):
    r = client.post("/api/ingest/statement", files={"file": (name, text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_leaves_demo_mode(client):
    client.post("/api/demo/seed")
    _upload(client)
    assert client.get("/api/connections").json()["mode"] == "real"
    merchants = {s["merchant"] for s in client.get("/api/subscriptions").json()}
    assert "Hulu" not in merchants and "Netflix" not in merchants  # demo subscriptions are gone


def test_same_csv_twice_adds_nothing(client):
    client.post("/api/demo/seed")
    first = _upload(client)
    second = _upload(client)
    assert first["added_transactions"] == 6 and second["added_transactions"] == 0
    kinds = [f["kind"] for f in client.get("/api/findings").json()]
    assert kinds.count("duplicate_charge") <= 1  # at most the one real same-day pair, never one per re-upload


def test_identical_rows_in_one_file_both_count():
    txs = parse_csv(CSV)
    assert len(txs) == 6 and len({t.id for t in txs}) == 6


def test_csv_ids_dont_depend_on_row_order():
    rows = CSV.splitlines()
    shuffled = "\n".join([rows[0]] + rows[:0:-1]) + "\n"
    shell = lambda txs: next(t.id for t in txs if t.description.startswith("SHELL"))  # noqa: E731
    assert shell(parse_csv(CSV)) == shell(parse_csv(shuffled))
