from fastapi.testclient import TestClient

from clawback.main import app


def test_api_smoke(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["ok"] is True
        assert len(client.get("/api/missing").json()) > 10
        summary = client.post("/api/demo/seed").json()
        assert summary["subscriptions"] >= 9 and summary["potential_monthly_savings"] > 0

        subs = client.get("/api/subscriptions").json()
        hulu = next(s for s in subs if s["merchant"] == "Hulu")
        prep = client.post(f"/api/subscriptions/{hulu['id']}/cancel-prep").json()
        assert prep["primary_link"] and prep["missing"]

        alt = client.get(f"/api/subscriptions/{hulu['id']}/alternatives").json()
        assert alt["hints"] and alt["missing"]

        # Unconfigured integrations answer 501 with a MISSING message instead of pretending to work.
        r = client.get("/api/connect/email")
        assert r.status_code == 501 and "MISSING" in r.json()["missing"]
        assert client.get("/api/trace").json()


def test_cancel_email_row_survives_rerun(fake_llm, monkeypatch):
    from clawback.pipeline import cancel_lookup

    # A merchant that takes cancellations by email, so Ultra writes one.
    monkeypatch.setattr(cancel_lookup, "lookup", lambda *a, **k: {
        "links": [{"label": "Cancel Hulu", "url": "https://help.hulu.com/cancel", "verified": True}],
        "steps": [], "steps_url": None, "support_email": "cancel@hulu.com", "checked_on": "2026-10-23",
        "verified": True, "from_cache": True})
    with TestClient(app) as client:
        client.post("/api/demo/seed")
        hulu = next(s for s in client.get("/api/subscriptions").json() if s["merchant"] == "Hulu")
        client.post(f"/api/subscriptions/{hulu['id']}/cancel-prep")
        client.post(f"/api/subscriptions/{hulu['id']}/cancelled")  # re-runs the pipeline
        assert "cancel_email" in [r["stage"] for r in client.get("/api/trace").json()]
