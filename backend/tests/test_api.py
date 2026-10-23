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
        assert prep["email"]["subject"] and prep["missing"]

        alt = client.get(f"/api/subscriptions/{hulu['id']}/alternatives").json()
        assert alt["hints"] and alt["missing"]

        # Unconfigured integrations answer 501 with a MISSING message instead of pretending to work.
        r = client.get("/api/connect/email")
        assert r.status_code == 501 and "MISSING" in r.json()["missing"]
        assert client.get("/api/trace").json()
