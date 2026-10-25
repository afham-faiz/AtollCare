# Pre-arrival packets and scans through the API (mock Gemini, no Presage bridge): the companion's phone captures once,
# the transfer started from it carries everything, and nothing is invented when a service is missing.
import subprocess
import time
from uuid import UUID, uuid4

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from app.intake.schemas import RppgEstimates
from app.main import create_app
from app.models import Scan, ScanStatus
from app.services.hub import get_hub

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000000000100013d0d3a840000000049454e44ae426082")


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        c.post("/api/demo/reset")
        c.patch("/api/demo/state", json={"region_id": "maldives", "speed_multiplier": 1})
        yield c


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> bytes:
    """A 3-second test-pattern video (no face: Presage would find nothing, which is the point)."""
    out = tmp_path_factory.mktemp("clip") / "clip.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=15", "-t", "3", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out.read_bytes()


def ok(resp, status=200):
    assert resp.status_code == status, resp.text
    return resp.json()


def wait_scans(c, path: str, key: str = "scans", timeout_s: float = 30.0) -> list[dict]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        scans = ok(c.get(path))[key]
        if scans and all(s["status"] != "processing" for s in scans):
            return scans
        time.sleep(0.2)
    raise AssertionError(f"scans still processing: {scans}")


def test_packet_from_phone_to_transfer(client, clip):
    i = ok(client.post("/api/intakes", json={"health_centre_id": "dhiffushi_hc"}))
    assert i["status"] == "draft" and i["code"].startswith("PA-")

    i = ok(client.patch(f"/api/intakes/{i['id']}", json={
        "patient": {"age": 58, "sex": "M"},
        "account": "He grabbed his chest about forty minutes ago and is sweating a lot. Pain goes to his left arm.",
    }))
    assert i["account_source"] == "text"
    assert i["complaint"] == "He grabbed his chest about forty minutes ago and is sweating a lot."  # first sentence

    i = ok(client.post(f"/api/intakes/{i['id']}/id-photo", files={"image": ("id.png", PNG, "image/png")}))
    assert i["identity"]["needs_review"] and i["identity"]["issues"]  # no Gemini: nothing guessed, flagged for review

    ok(client.post(f"/api/intakes/{i['id']}/scans", files={"video": ("clip.mp4", clip, "video/mp4")}))
    scan = wait_scans(client, f"/api/intakes/{i['id']}")[0]
    assert scan["status"] == "done"
    assert scan["vitals"] is None and "Presage" in scan["vitals_note"]  # no bridge: no numbers, said plainly
    findings = scan["signs"]["findings"]
    assert findings and all(f["finding"] == "cannot_assess" for f in findings)  # no Gemini: nothing claimed

    i = ok(client.post(f"/api/intakes/{i['id']}/send"))
    assert i["status"] == "sent"
    assert [x["id"] for x in ok(client.get("/api/intakes?status=sent"))] == [i["id"]]

    t = ok(client.post(f"/api/intakes/{i['id']}/transfer", json={"destination_id": "igmh", "mode": "boat"}))
    assert t["status"] == "preparing" and t["origin_id"] == "dhiffushi_hc" and t["patient"]["age"] == 58
    assert t["pre_arrival"]["code"] == i["code"] and t["pre_arrival"]["scans"][0]["id"] == scan["id"]
    assert any(n["author"] == "companion" and "chest" in n["text"] for n in t["notes"])
    assert ok(client.get(f"/api/intakes/{i['id']}"))["status"] == "started"
    # captured once: the packet can't be edited after the transfer starts
    assert client.patch(f"/api/intakes/{i['id']}", json={"account": "changed"}).status_code == 409


def test_empty_packet_cannot_be_sent(client):
    i = ok(client.post("/api/intakes", json={}))
    assert client.post(f"/api/intakes/{i['id']}/send").status_code == 422
    assert client.post(f"/api/intakes/{i['id']}/transfer", json={"destination_id": "igmh", "mode": "boat"}).status_code == 422


def test_scan_during_a_transfer(client, clip):
    t = ok(client.post("/api/transfers", json={"patient": {"age": 70}, "complaint": "Short of breath",
                                               "origin_id": "dhiffushi_hc", "destination_id": "igmh", "mode": "boat"}))
    t = ok(client.post(f"/api/transfers/{t['id']}/scans", files={"video": ("c.mp4", clip, "video/mp4")}))
    assert t["scans"][0]["status"] == "processing"
    scan = wait_scans(client, f"/api/transfers/{t['id']}")[0]
    assert scan["status"] == "done" and scan["signs"] is not None
    # one line on the timeline, said plainly: nothing measured, nothing checked (no bridge, no Gemini)
    lines = [n["text"] for n in ok(client.get(f"/api/transfers/{t['id']}"))["notes"] if n["text"].startswith("Crew scan:")]
    assert lines == ["Crew scan: heart and breathing rate not measured. Visible signs not checked."]


def live_summary(hr: int = 84, rr: int = 15) -> str:
    """What the bridge hands the phone when a live scan stops (presage-bridge `summary`)."""
    import json

    pulse = [{"t_s": i, "value": hr, "confidence": 0.7, "stable": True} for i in range(20)]
    breathing = [{"t_s": i, "value": rr, "confidence": 0.5, "stable": True} for i in range(10)]
    return json.dumps({"mode": "sdk", "heart_rate_bpm": hr, "respiration_rate_bpm": rr, "confidence": 0.5,
                       "issues": [], "hints": [], "diagnostics": {"pulse_series": pulse, "breathing_series": breathing,
                                                                  "path": "live", "frames": 900, "seconds": 31.0}})


def test_live_scan_result_comes_with_the_clip(client, clip):
    """The phone streamed to Presage while recording: its numbers land at once, scored once; only Gemini runs."""
    t = ok(client.post("/api/transfers", json={"complaint": "Chest pain", "origin_id": "dhiffushi_hc",
                                               "destination_id": "igmh", "mode": "boat"}))
    ok(client.post(f"/api/transfers/{t['id']}/scans", files={"video": ("c.mp4", clip, "video/mp4")},
                   data={"presage": live_summary()}))
    scan = wait_scans(client, f"/api/transfers/{t['id']}")[0]
    v = scan["vitals"]
    assert (v["heart_rate_bpm"], v["respiration_rate_bpm"]) == (84, 15)
    assert v["heart_rate_stable"] and v["respiration_stable"] and v["diagnostics"]["path"] == "live"
    assert scan["vitals_note"] is None  # not "bridge isn't running": the clip wasn't sent to Presage at all
    t = ok(client.get(f"/api/transfers/{t['id']}"))
    assert {(r["heart_rate"], r["resp_rate"]) for r in t["vitals"] if r["source"] == "presage"} == {(None, 15), (84, None)}
    # the live result isn't a live camera: the monitoring state is left as it was
    assert t["monitoring"]["source"] == "simulated"


def test_a_malformed_live_result_is_refused(client, clip):
    i = ok(client.post("/api/intakes", json={"health_centre_id": "dhiffushi_hc"}))
    resp = client.post(f"/api/intakes/{i['id']}/scans", files={"video": ("c.mp4", clip, "video/mp4")},
                       data={"presage": "not json"})
    assert resp.status_code == 422


def test_scan_mode_stops_simulated_readings(client):
    t = ok(client.post("/api/transfers", json={"complaint": "Chest pain", "origin_id": "dhiffushi_hc",
                                               "destination_id": "igmh", "mode": "boat"}))
    t = ok(client.post(f"/api/transfers/{t['id']}/monitoring", json={"source": "scan"}))
    assert t["monitoring"]["source"] == "scan"
    assert any(n["text"] == "Contactless monitoring: 60-second Presage scans" for n in t["notes"])
    before = len(ok(client.get(f"/api/transfers/{t['id']}"))["vitals"])
    client.portal.call(get_hub().transfers.tick)
    assert len(ok(client.get(f"/api/transfers/{t['id']}"))["vitals"]) == before


@pytest.mark.parametrize("source, expected_readings", [("presage", 2), ("mock", 0)])
def test_scan_vitals_become_readings_once(client, source, expected_readings):
    """Measured scan vitals become Presage readings (one per vital, each with its own quality); mock never does."""
    t = ok(client.post("/api/transfers", json={"complaint": "Chest pain", "origin_id": "dhiffushi_hc",
                                               "destination_id": "igmh", "mode": "boat"}))
    svc = get_hub().transfers
    scan = Scan(id=uuid4(), at=svc.now(), status=ScanStatus.done,
                vitals=RppgEstimates(heart_rate_bpm=96, respiration_rate_bpm=22, heart_rate_quality=0.8,
                                     respiration_quality=0.7, signal_quality_score=0.7, uncalibrated=False, source=source))

    async def run():
        async with svc.locks[UUID(t["id"])]:
            doc = await svc._load(UUID(t["id"]))
            await svc._record_scan_vitals(doc, scan)
            await svc._record_scan_vitals(doc, scan)  # a second call is a no-op
            await svc._note_scan(doc, scan, "Crew scan")
            await svc._note_scan(doc, scan, "Crew scan")
            await svc._save(doc)

    client.portal.call(run)
    t = ok(client.get(f"/api/transfers/{t['id']}"))
    presage = [v for v in t["vitals"] if v["source"] == "presage"]
    assert len(presage) == expected_readings
    if expected_readings:
        # rounded: TimescaleDB stores confidence as a 4-byte REAL (0.8 reads back as 0.8000000119)
        assert {(v["heart_rate"], v["resp_rate"], round(v["confidence"], 3)) for v in presage} == {(96, None, 0.8),
                                                                                                    (None, 22, 0.7)}
        assert t["latest"]["heart_rate"]["source"] == "presage" and t["news2"] is not None
    # a scan is not a live camera: the monitoring state is left as it was
    assert t["monitoring"]["source"] == "simulated"
    lines = [n["text"] for n in t["notes"] if n["text"].startswith("Crew scan:")]
    assert len(lines) == 1
    if expected_readings:
        assert lines[0].startswith("Crew scan: heart rate 96 bpm; breathing 22/min.")


def test_bystander_video_is_shown_but_never_scored(client):
    """The companion's video is outside Presage's cleared use: its numbers reach the timeline, not NEWS2."""
    from app.models import PreArrival

    t = ok(client.post("/api/transfers", json={"complaint": "Chest pain", "origin_id": "dhiffushi_hc",
                                               "destination_id": "igmh", "mode": "boat"}))
    svc = get_hub().transfers
    scan = Scan(id=uuid4(), at=svc.now(), status=ScanStatus.done,
                vitals=RppgEstimates(heart_rate_bpm=96, respiration_rate_bpm=22, heart_rate_quality=0.8,
                                     respiration_quality=0.7, source="presage"))
    packet = PreArrival(intake_id=uuid4(), code="PA-TEST", sent_at=svc.now(), scans=[scan])
    client.portal.call(svc.attach_pre_arrival, UUID(t["id"]), packet)
    t = ok(client.get(f"/api/transfers/{t['id']}"))
    assert not [v for v in t["vitals"] if v["source"] == "presage"] and t["news2"] is None
    assert any(n["text"].startswith("Pre-arrival video: heart rate 96 bpm") for n in t["notes"])


def test_old_camera_readings_stop_counting(client):
    """A Presage spot check counts for 15 minutes; crew values keep the usual NEWS2 window."""
    from datetime import timedelta

    t = ok(client.post("/api/transfers", json={"complaint": "Chest pain", "origin_id": "dhiffushi_hc",
                                               "destination_id": "igmh", "mode": "boat"}))
    old = (get_hub().transfers.now() - timedelta(minutes=20)).isoformat()
    ack = ok(client.post(f"/api/transfers/{t['id']}/vitals", json={"source": "presage", "heart_rate": 140,
                                                                    "confidence": 0.9, "recorded_at": old}))
    assert ack["news2"] is None and not ack["alerts"]
    ack = ok(client.post(f"/api/transfers/{t['id']}/vitals", json={"heart_rate": 140, "recorded_at": old}))
    assert ack["news2"] is not None  # the crew's reading from 20 minutes ago still counts


def test_serial_scans_raise_a_camera_trend(client):
    """Two stable crew scans minutes apart: a big rise asks for a manual set, in the vehicle and at the hospital."""
    from datetime import timedelta

    t = ok(client.post("/api/transfers", json={"complaint": "Chest pain", "origin_id": "dhiffushi_hc",
                                               "destination_id": "igmh", "mode": "boat"}))
    svc = get_hub().transfers
    now = svc.now()

    def scan(at, hr, rr):  # still processing: Gemini hasn't finished, but Presage's numbers are in
        return Scan(id=uuid4(), at=at, status=ScanStatus.processing,
                    vitals=RppgEstimates(heart_rate_bpm=hr, respiration_rate_bpm=rr, heart_rate_stable=True,
                                         respiration_stable=True, heart_rate_quality=0.8, respiration_quality=0.7,
                                         source="presage"))

    async def run(scans):
        async with svc.locks[UUID(t["id"])]:
            doc = await svc._load(UUID(t["id"]))
            for s in scans:
                doc.scans.append(s)
                await svc._record_scan_vitals(doc, s)
            await svc._save(doc)

    client.portal.call(run, [scan(now - timedelta(minutes=12), 76, 16)])
    assert not any(a["code"] == "presage_trend" for a in ok(client.get(f"/api/transfers/{t['id']}"))["alerts"])
    client.portal.call(run, [scan(now, 118, 24)])
    t = ok(client.get(f"/api/transfers/{t['id']}"))
    trend = next(a for a in t["alerts"] if a["code"] == "presage_trend")
    assert trend["level"] == "warning"
    assert trend["text"] == "Camera trend HR 76→118, RR 16→24 over 12 min — take a full manual set"
    assert any(n["kind"] == "alert" and n["text"] == trend["text"] for n in t["notes"])  # spoken in the vehicle


def test_oximeter_pulse_checks_the_camera(client):
    t = ok(client.post("/api/transfers", json={"complaint": "Chest pain", "origin_id": "dhiffushi_hc",
                                               "destination_id": "igmh", "mode": "boat"}))
    ok(client.post(f"/api/transfers/{t['id']}/vitals", json={"source": "presage", "heart_rate": 98, "confidence": 0.9}))
    ok(client.post(f"/api/transfers/{t['id']}/vitals", json={"source": "manual", "heart_rate": 96}))
    ok(client.post(f"/api/transfers/{t['id']}/vitals", json={"source": "manual", "heart_rate": 72}))
    t = ok(client.get(f"/api/transfers/{t['id']}"))
    checks = [(c["camera"], c["reference"], c["agrees"], c["disputed"]) for c in t["presage_checks"]]
    assert checks == [(98, 96, True, False), (98, 72, False, True)]
    assert any(n["text"] == "Pulse check: camera 98, oximeter 72 — differ by 26 bpm, so the oximeter's is used"
               for n in t["notes"])
    assert t["latest"]["heart_rate"]["source"] == "manual"  # the newer oximeter value is the one scored


def test_scan_trend_needs_time_and_stability():
    from datetime import timedelta

    from app.core.scan_trend import scan_trend

    now = get_hub().transfers.now()

    def scan(minutes_ago, hr, stable=True):
        return Scan(id=uuid4(), at=now - timedelta(minutes=minutes_ago), status=ScanStatus.done,
                    vitals=RppgEstimates(heart_rate_bpm=hr, heart_rate_stable=stable, source="presage"))

    assert scan_trend([scan(1, 70), scan(0, 100)]) is None  # a minute apart: not a trend
    assert scan_trend([scan(10, 70, stable=False), scan(0, 100)]) is None  # baseline Presage didn't trust
    calm = scan_trend([scan(10, 70), scan(0, 78)])
    assert calm and not calm.worrying and calm.text == "Camera trend HR 70→78 over 10 min"


def test_scan_summary_marks_weak_readings_and_contradictions():
    from app.intake.schemas import CueFinding, CuePlan, PlannedCue, VisualCueReport
    from app.services.transfers import scan_summary

    plan = CuePlan(presentations=["stroke"], cues=[
        PlannedCue(cue_id="face_droop", label="Face droop", question="?", source="transcript", why="said"),
        PlannedCue(cue_id="arm_weakness", label="Arm weakness", question="?", source="baseline", why="std"),
    ])
    signs = VisualCueReport(plan=plan, findings=[
        CueFinding(cue_id="face_droop", label="Face droop", finding="absent", reason="symmetric"),
        CueFinding(cue_id="arm_weakness", label="Arm weakness", finding="present", reason="left arm limp",
                   evidence_frames=[3]),
    ])
    scan = Scan(id=uuid4(), at=get_hub().transfers.now(), status=ScanStatus.done, signs=signs,
                vitals=RppgEstimates(heart_rate_bpm=88, respiration_rate_bpm=30, heart_rate_quality=0.9,
                                     respiration_quality=0.3, source="presage"))
    assert scan_summary(scan) == ("heart rate 88 bpm; breathing 30/min (weak signal, not scored). "
                                  "Seen on video: Arm weakness. Described but not seen: Face droop.")
    scan.vitals.diagnostics = {"apnea_s": [12.4]}
    assert "Presage detected a pause in breathing at 12 s" in scan_summary(scan)
