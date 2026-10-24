import httpx

from src.services import rppg_extractor


def fake_post(payload=None, exc=None):
    def post(*args, **kwargs):
        if exc:
            raise exc
        req = httpx.Request("POST", "http://sidecar/vitals")
        return httpx.Response(200, json=payload, request=req)

    return post


def test_good_signal(monkeypatch):
    payload = {"mode": "sdk", "heart_rate_bpm": 80, "respiration_rate_bpm": 16, "confidence": 0.85, "issues": []}
    monkeypatch.setattr(httpx, "post", fake_post(payload))
    est = rppg_extractor.extract_vitals_from_video(b"video")
    assert est.heart_rate_bpm == 80
    assert est.source == "presage"
    assert not est.uncalibrated


def test_low_quality_is_uncalibrated(monkeypatch):
    payload = {"mode": "sdk", "heart_rate_bpm": 99, "respiration_rate_bpm": None, "confidence": 0.3, "issues": ["kTooDark"]}
    monkeypatch.setattr(httpx, "post", fake_post(payload))
    est = rppg_extractor.extract_vitals_from_video(b"video")
    assert est.uncalibrated
    assert est.issues == ["kTooDark"]


def sample(v, c, stable=True):
    return {"value": v, "confidence": c, "stable": stable}


def test_bad_final_samples_do_not_override_a_good_trace(monkeypatch):
    pulse = [sample(88, 0.7) for _ in range(20)] + [sample(55, 0.3, stable=False) for _ in range(3)]
    breathing = [sample(14, 0.0, stable=False)] * 5 + [sample(17, 0.3, stable=False) for _ in range(6)]
    payload = {
        "mode": "sdk", "heart_rate_bpm": 55, "respiration_rate_bpm": 20, "confidence": 0.25, "issues": [],
        "diagnostics": {"pulse_series": pulse, "breathing_series": breathing},
    }
    monkeypatch.setattr(httpx, "post", fake_post(payload))
    est = rppg_extractor.extract_vitals_from_video(b"video")
    assert est.heart_rate_bpm == 88
    assert round(est.heart_rate_quality, 2) == 0.7
    assert est.respiration_rate_bpm == 17          # only samples with confidence > 0
    assert est.signal_quality_score < 0.4          # overall = weakest vital
    assert est.uncalibrated


def test_sidecar_down_degrades_without_raising(monkeypatch):
    monkeypatch.setattr(httpx, "post", fake_post(exc=httpx.ConnectError("refused")))
    est = rppg_extractor.extract_vitals_from_video(b"video")
    assert est.heart_rate_bpm is None
    assert est.signal_quality_score == 0.0
    assert est.source == "unavailable"
