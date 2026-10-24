# F-M2.3 NEWS2 — every boundary in the RCP table + partial scoring.
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core import news2


@pytest.mark.parametrize(
    "value,expected",
    [(5, 3), (8, 3), (9, 1), (11, 1), (12, 0), (20, 0), (21, 2), (24, 2), (25, 3), (40, 3)],
)
def test_resp_rate(value, expected):
    assert news2.score_resp_rate(value) == expected


@pytest.mark.parametrize("value,expected", [(85, 3), (91, 3), (92, 2), (93, 2), (94, 1), (95, 1), (96, 0), (100, 0)])
def test_spo2(value, expected):
    assert news2.score_spo2(value) == expected


@pytest.mark.parametrize("value,expected", [(True, 2), (False, 0)])
def test_air_or_oxygen(value, expected):
    assert news2.score_on_oxygen(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(70, 3), (90, 3), (91, 2), (100, 2), (101, 1), (110, 1), (111, 0), (219, 0), (220, 3), (250, 3)],
)
def test_systolic_bp(value, expected):
    assert news2.score_systolic_bp(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(30, 3), (40, 3), (41, 1), (50, 1), (51, 0), (90, 0), (91, 1), (110, 1), (111, 2), (130, 2), (131, 3), (180, 3)],
)
def test_heart_rate(value, expected):
    assert news2.score_heart_rate(value) == expected


@pytest.mark.parametrize("value,expected", [("A", 0), ("C", 3), ("V", 3), ("P", 3), ("U", 3)])
def test_consciousness(value, expected):
    assert news2.score_consciousness(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(34.0, 3), (35.0, 3), (35.1, 1), (36.0, 1), (36.1, 0), (38.0, 0), (38.1, 1), (39.0, 1), (39.1, 2), (41.0, 2)],
)
def test_temperature(value, expected):
    assert news2.score_temperature(value) == expected


def test_bands():
    assert news2.band_for(0, False) == "low"
    assert news2.band_for(4, False) == "low"
    assert news2.band_for(3, True) == "low_medium"
    assert news2.band_for(5, False) == "medium"
    assert news2.band_for(6, True) == "medium"
    assert news2.band_for(7, False) == "high"


def test_acceptance_f_m1_4_total_17():
    # RR 26, SpO2 90, SBP 88, HR 135, temp 39.5, V (on air) → 3+3+3+3+2+3 = 17
    r = news2.score_values(
        {"resp_rate": 26, "spo2": 90, "on_oxygen": False, "systolic_bp": 88, "heart_rate": 135,
         "temperature_c": 39.5, "consciousness": "V"}
    )
    assert r.total == 17
    assert r.band == "high"
    assert r.complete


def test_partial_presage_hr_rr_only():
    r = news2.score_values({"heart_rate": 112, "resp_rate": 24})
    assert r.total == 4
    assert not r.complete
    assert set(r.missing) == {"spo2", "on_oxygen", "systolic_bp", "consciousness", "temperature_c"}
    assert news2.partial_label(r) == "Partial NEWS2 (RR, HR only)"


def test_latest_values_within_30_min_and_quality_gate():
    from app.models import VitalsReading

    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    cid = uuid4()
    readings = [
        VitalsReading(id=uuid4(), case_id=cid, recorded_at=now - timedelta(minutes=45), source="manual", spo2=88),
        VitalsReading(id=uuid4(), case_id=cid, recorded_at=now - timedelta(minutes=10), source="presage",
                      heart_rate=150, confidence=0.4, low_quality=True),
        VitalsReading(id=uuid4(), case_id=cid, recorded_at=now - timedelta(minutes=5), source="presage",
                      heart_rate=95, resp_rate=18, confidence=0.9),
    ]
    values = news2.latest_values(readings, now)
    assert values == {"heart_rate": 95, "resp_rate": 18}  # old SpO2 and low-quality HR excluded
