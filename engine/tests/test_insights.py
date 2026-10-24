# Network insights: honest "not available" on the in-memory store; on Tiger Data / TimescaleDB, seeded history flows
# through compression, continuous aggregates and the aggregate-vs-raw benchmark.
#   TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/atollcare_test uv run pytest tests/test_insights.py
import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ON_TIGER = bool(os.environ.get("TEST_DATABASE_URL"))


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        c.post("/api/demo/reset")
        c.patch("/api/demo/state", json={"region_id": "maldives", "speed_multiplier": 1})
        yield c


def ok(resp, status=200):
    assert resp.status_code == status, resp.text
    return resp.json()


def test_meta_reports_infrastructure_facts(client):
    infra = ok(client.get("/api/meta"))["infra"]
    assert infra["host"] in ("Local", "Vultr")
    assert infra["database"] == ("TimescaleDB" if ON_TIGER else "In-memory") or infra["database"] == "Tiger Cloud"


@pytest.mark.skipif(ON_TIGER, reason="memory-store behaviour")
def test_memory_store_says_insights_need_tiger(client):
    r = ok(client.get("/api/insights"))
    assert r["available"] is False and "Tiger" in r["reason"]
    assert client.get("/api/insights/benchmark").status_code == 409
    assert client.post("/api/demo/history?days=7&per_day=1").status_code == 409


@pytest.mark.skipif(not ON_TIGER, reason="needs TEST_DATABASE_URL (TimescaleDB / Tiger Cloud)")
def test_seeded_history_flows_through_compression_and_aggregates(client):
    seeded = ok(client.post("/api/demo/history?days=10&per_day=2"))
    assert seeded["transfers"] == 20 and seeded["readings"] > 1000 and seeded["notes"] >= 20
    assert seeded["compressed_chunks"] >= 1  # chunks older than 7 days are columnar-compressed

    r = ok(client.get("/api/insights?days=30"))
    assert r["available"] and r["seeded_transfers"] == 20
    assert r["kpis"]["accepted"] == 20 and r["kpis"]["median_min_to_accept"] > 0
    assert sum(d["readings"] for d in r["daily"]) == seeded["readings"]
    # per-transfer randomness really is per transfer (a classic Postgres trap: uncorrelated random() runs once)
    assert sum(d["questions"] for d in r["daily"]) > 0 and sum(d["alerts"] for d in r["daily"]) > 0
    assert len({d["transfers"] for d in r["daily"]}) > 1
    assert {"vitals_1m", "network_vitals_1h", "network_events_1d"} <= set(r["aggregates"])
    vitals = next(s for s in r["storage"] if s["name"] == "vitals_readings")
    assert vitals["compressed_chunks"] >= 1 and vitals["bytes_after_compression"] < vitals["bytes_before_compression"]
    assert all(q["ms"] >= 0 for q in r["queries"]) and any("continuous aggregate" in q["source"] for q in r["queries"])

    b = ok(client.get("/api/insights/benchmark?days=30"))
    assert b["rows_scanned"] == seeded["readings"] and b["aggregate_ms"] > 0 and b["raw_ms"] > 0

    # seeded history never reaches the clinical screens, and a demo reset leaves it in place
    assert ok(client.get("/api/transfers")) == []
    client.post("/api/demo/reset")
    assert ok(client.get("/api/insights?days=30"))["seeded_transfers"] == 20
