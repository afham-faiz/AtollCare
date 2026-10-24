# Network insights (transfer_log hypertable), infra detection and the deploy-facing endpoints.
from datetime import datetime, timedelta, timezone

from app.core import infra, insights, regions
from app.config import Settings
from tests.test_api import client, create, ok  # noqa: F401

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def test_seed_rows_are_deterministic_flagged_and_complete():
    region = regions.region("maldives")
    a = insights.seed_rows(region, 60, NOW)
    b = insights.seed_rows(region, 60, NOW)
    assert [r.transfer_id for r in a] == [r.transfer_id for r in b]
    assert 300 < len(a) < 700
    assert all(r.seeded and r.region_id == "maldives" for r in a)
    assert all(r.arrived_at <= NOW and r.arrived_at > r.departed_at for r in a)
    assert {r.channel for r in a} == {"radio", "atollcare"}
    hospitals = {f.id for f in region.facilities if f.kind == "hospital"}
    assert all(r.destination_id in hospitals for r in a)


def test_atollcare_channel_gives_more_warning_than_radio():
    rows = insights.seed_rows(regions.region("maldives"), 60, NOW)
    res = insights.aggregate(rows, "maldives", 60, NOW - timedelta(days=60), "Indian/Maldives")
    ch = {c.channel: c for c in res.channels}
    assert ch["atollcare"].median_warning_min > 3 * ch["radio"].median_warning_min
    assert ch["atollcare"].median_accept_min < ch["radio"].median_accept_min
    assert res.totals.transfers == len(rows) == sum(d.transfers for d in res.daily)
    assert len(res.by_hour) == 24 and sum(h.transfers for h in res.by_hour) == len(rows)


def test_percentile_matches_postgres_percentile_cont():
    assert insights.pctl([1, 2, 3, 4], 0.5) == 2.5
    assert insights.pctl([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9.1
    assert insights.pctl([], 0.5) is None


def test_region_code_and_labels():
    assert infra.region_code({"region": {"regioncode": "lhr"}}) == "LHR"
    assert infra.region_code({"region": "ewr"}) == "EWR"
    assert infra.region_code({}) is None
    assert infra.host_text("Vultr", "lhr") == "Vultr · LHR"
    assert infra.host_text(None, None) == "This computer"
    assert infra.database_text("memory", "", None, None) == ("In-memory (demo)", "memory")
    tiger = "postgres://tsdbadmin:x@abc123.k9.tsdb.cloud.timescale.com:31234/tsdb?sslmode=require"
    assert infra.database_text("postgres", tiger, "2.17.2", "16.4") == ("Tiger Cloud · TimescaleDB 2.17.2", "tiger_cloud")
    assert infra.database_text("postgres", "postgresql://db:5432/x", "2.17.2", "16.4")[1] == "timescaledb"
    assert infra.database_text("postgres", "postgresql://db:5432/x", None, "16.4") == ("PostgreSQL 16", "postgres")


async def test_host_label_env_override():
    s = Settings(host_label="Vultr", host_region="lhr", metadata_url="")
    assert await infra.detect_host(s) == ("Vultr", "LHR", "env")
    assert await infra.detect_host(Settings(host_label="", metadata_url="")) == (None, None, "none")


def test_insights_api_seed_query_clear(client):  # noqa: F811
    meta = ok(client.get("/api/meta"))
    assert meta["infra"]["database_kind"] in ("memory", "timescaledb", "tiger_cloud", "postgres")
    assert ok(client.get("/api/health"))["infra"]["host"]
    ok(client.delete("/api/insights/seed"))
    seed = ok(client.post("/api/insights/seed?days=60"))
    assert seed["inserted"] > 300 and seed["region_id"] == "maldives"
    res = ok(client.get("/api/insights?days=60"))
    assert res["totals"]["seeded"] == seed["inserted"]
    assert res["daily"] and res["channels"] and res["by_mode"] and len(res["by_hour"]) == 24
    assert res["source"] in ("transfer_daily", "raw", "memory")
    # re-seeding replaces, never duplicates
    again = ok(client.post("/api/insights/seed?days=60"))
    assert ok(client.get("/api/insights?days=60"))["totals"]["seeded"] == again["inserted"]
    ok(client.delete("/api/insights/seed"))
    assert ok(client.get("/api/insights?days=60"))["totals"]["seeded"] == 0
    assert client.get("/api/insights?days=0").status_code == 422


def test_live_transfer_is_logged_on_arrival(client):  # noqa: F811
    ok(client.delete("/api/insights/seed"))
    t = create(client)
    ok(client.post(f"/api/transfers/{t['id']}/handoff"))
    ok(client.post(f"/api/transfers/{t['id']}/accept", json={"by": "Dr A", "prepare": ["Cath lab"]}))
    ok(client.post(f"/api/transfers/{t['id']}/arrive"))
    ok(client.post(f"/api/transfers/{t['id']}/close"))
    res = ok(client.get("/api/insights?days=7"))
    live = res["totals"]["transfers"] - res["totals"]["seeded"]
    assert live >= 1
    atc = next(c for c in res["channels"] if c["channel"] == "atollcare")
    assert atc["prepared_pct"] is not None and atc["prepared_pct"] > 0
