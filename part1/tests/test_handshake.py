import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.models.schemas import (
    AccountDigest, CueFinding, CuePlan, Demographics, FrameInfo, PacketVital, PreArrivalPacket, RppgEstimates,
    VisualCueReport,
)
from src.services import account_digest, engine_client, handshake_log
from src.services.account_digest import _Digest, digest_account, mask_numbers
from src.services.packet import build_packet, initials

# What the licence in inputs/ reads as. None of these three may ever appear in a packet.
NAME, ID_NUMBER, DOB = "DAVID MC-FUNNY", "DAVID901014MF9AA", "1990-01-01"


@pytest.fixture(autouse=True)
def isolated_handshake_log(monkeypatch, tmp_path):
    monkeypatch.setattr(handshake_log, "LOG_PATH", tmp_path / "handshakes.json")


def demographics(**over):
    base = dict(full_name=NAME, id_number=ID_NUMBER, age=36, date_of_birth=DOB, document_type="UK driving licence",
                needs_review=True, issues=["The card is marked as a specimen / not a real document."])
    return Demographics(**{**base, **over})


def vitals(**over):
    base = dict(heart_rate_bpm=89, respiration_rate_bpm=19, heart_rate_quality=0.69, respiration_quality=0.29,
                signal_quality_score=0.29, uncalibrated=True, source="presage", issues=["kFaceNotForward", "kChestNotVisible"])
    return RppgEstimates(**{**base, **over})


def finding(cue_id, label, result, confidence=0.8, frames=()):
    return CueFinding(cue_id=cue_id, label=label, finding=result, confidence=confidence, evidence_frames=list(frames))


def signs(responsive_confidence=0.9, responsive="present"):
    return VisualCueReport(
        plan=CuePlan(),
        findings=[finding("laboured_breathing", "Visible effort to breathe", "present", 0.72, [1, 2]),
                  finding("responsiveness", "Alert and responsive", responsive, responsive_confidence, [1]),
                  finding("chest_clutching", "Hand pressed to the chest", "absent", 0.75),
                  finding("sweating", "Visible sweating", "cannot_assess", 0.4)],
        frames=[FrameInfo(index=i, t_s=float(i)) for i in range(1, 5)],
        reported_but_not_seen=["Hand pressed to the chest"])


DIGEST = AccountDigest(had_account=True, complaint="Collapsed after running uphill; gasping for 10 minutes, chest pain, pale lips.",
                       account="[name] collapsed after sprinting uphill and has been gasping for over 10 minutes. Card [number].",
                       redacted=True)


def packet(**over):
    args = dict(demographics=demographics(), vitals=vitals(), signs=signs(), digest=DIGEST)
    return build_packet(**{**args, **over})


# ================================================================ the extractor

@pytest.mark.parametrize("name, expected", [("DAVID MC-FUNNY", "D. M."), ("ana maria lopez", "A. M. L."), ("  x ", "X."),
                                            ("", None), (None, None), ("123 456", None)])
def test_initials(name, expected):
    assert initials(name) == expected


def test_the_packet_sends_a_label_age_complaint_readings_and_notes():
    p = packet()
    assert p.patient_label == "D. M." and p.age == 36 and p.sex is None
    assert p.complaint == DIGEST.complaint
    assert [(v.heart_rate, v.resp_rate) for v in p.vitals] == [(89.0, None), (None, 19.0)]
    assert [v.confidence for v in p.vitals] == [0.69, 0.29]                     # one confidence per reading
    assert all(v.source == "presage" and "face not turned" in v.hint for v in p.vitals)
    assert [n.title for n in p.notes] == ["ID check", "Voice account", "Video check"]


def test_no_name_id_number_or_birth_date_ever_leaves_in_the_packet():
    wire = json.dumps(packet().model_dump())
    for secret in (NAME, "MC-FUNNY", "DAVID", ID_NUMBER, DOB, "1990"):
        assert secret not in wire, secret
    assert {"ID number", "Date of birth (age is sent instead)", "Full name (only initials are sent)"} <= set(packet().withheld)


def test_the_id_note_describes_the_card_without_identifying_the_holder():
    note = next(n for n in packet().notes if n.title == "ID check")
    assert "UK driving licence" in note.text and "age 36" in note.text
    assert "specimen" in note.text and "check by eye" in note.text
    assert "DAVID" not in note.text and ID_NUMBER not in note.text


def test_even_an_issue_that_quotes_the_id_number_cannot_leak():
    leaky = demographics(issues=[f"ID number {ID_NUMBER!r} does not look like an ID number, so it was dropped."])
    assert ID_NUMBER not in json.dumps(packet(demographics=leaky).model_dump())


def test_label_can_be_switched_off():
    assert packet(label_mode="none").patient_label is None


def test_the_video_note_lists_seen_not_seen_could_not_assess_and_what_the_account_claimed():
    note = next(n for n in packet().notes if n.title == "Video check")
    assert "Seen: Visible effort to breathe (72%), Alert and responsive (90%)." in note.text
    assert "Not seen: Hand pressed to the chest (75%)." in note.text
    assert "Could not assess: Visible sweating (40%)." in note.text
    assert "Mentioned in the account but not seen on video: Hand pressed to the chest." in note.text
    assert "4 still frames" in note.text and "not a diagnosis" in note.text


def test_evidence_images_are_withheld_because_the_crew_app_cannot_carry_them():
    assert any("Evidence frame images" in w for w in packet().withheld)


def test_mock_or_unavailable_vitals_are_never_sent_as_measurements():
    for source in ("mock", "unavailable"):
        p = packet(vitals=vitals(source=source))
        assert p.vitals == []
        assert any(f"source: {source}" in m for m in p.missing)


def test_readings_outside_the_crew_apps_ranges_are_dropped_and_reported():
    p = packet(vitals=vitals(heart_rate_bpm=400, respiration_rate_bpm=0))
    assert p.vitals == []
    assert any("Heart rate 400" in m for m in p.missing) and any("Breathing rate 0" in m for m in p.missing)


def test_a_missing_vital_is_reported_not_guessed():
    p = packet(vitals=vitals(respiration_rate_bpm=None, respiration_quality=None))
    assert [v.heart_rate for v in p.vitals] == [89.0] and "Breathing rate was not measured." in p.missing


def test_no_vitals_at_all():
    p = packet(vitals=None)
    assert p.vitals == [] and "Heart rate and breathing rate were not measured." in p.missing


def test_confidence_falls_back_to_the_overall_score_and_is_kept_in_range():
    p = packet(vitals=vitals(heart_rate_quality=None, respiration_quality=1.7, signal_quality_score=0.5))
    assert [v.confidence for v in p.vitals] == [0.5, 1.0]


def test_everything_missing_still_gives_a_valid_packet():
    p = build_packet(demographics=None, vitals=None, signs=None, digest=None)
    assert p.complaint == "Pre-arrival check, no account given" and p.vitals == [] and p.notes == []
    assert p.patient_label is None and p.age is None
    for text in ("No ID was read, so the patient's age is unknown.", "No voice account was given.",
                 "Visible signs in the video were not checked.", "Oxygen level, blood pressure and temperature"):
        assert any(text in m for m in p.missing), text


def test_without_an_account_the_complaint_falls_back_to_what_was_seen():
    p = build_packet(demographics=None, vitals=None, signs=signs(), digest=AccountDigest())
    assert p.complaint.startswith("Pre-arrival check, no account given. Seen on video: Visible effort to breathe")


def test_an_account_that_could_not_be_checked_is_not_forwarded_in_full():
    held_back = AccountDigest(had_account=True, complaint="Gasping and chest pain.", account="", redacted=False)
    p = packet(digest=held_back)
    assert p.complaint == "Gasping and chest pain." and "Voice account" not in [n.title for n in p.notes]
    assert any("held back" in m for m in p.missing) and any("Full voice account" in w for w in p.withheld)


def test_notes_never_exceed_the_crew_apps_2000_character_limit():
    long_digest = AccountDigest(had_account=True, complaint="x", account="word " * 1000, redacted=True)
    notes = packet(digest=long_digest).notes
    assert all(len(n.text) <= 2000 for n in notes) and next(n for n in notes if n.title == "Voice account").text.endswith("…")


def test_consciousness_is_off_by_default_because_their_app_cannot_label_an_ai_source():
    assert packet().consciousness is None


@pytest.mark.parametrize("confidence, result, expected", [(0.9, "present", "A"), (0.7, "present", "A"), (0.69, "present", None),
                                                          (0.99, "absent", None), (0.99, "cannot_assess", None)])
def test_consciousness_only_when_enabled_and_clearly_seen(confidence, result, expected):
    p = packet(signs=signs(responsive_confidence=confidence, responsive=result), send_consciousness=True, min_confidence=0.7)
    assert p.consciousness == expected


# ================================================================ the account digest

def test_long_digit_runs_are_masked():
    assert mask_numbers("card number 41890 and phone 07700900123, aged 54 for 10 minutes") == \
        "card number [number] and phone [number], aged 54 for 10 minutes"


def test_the_digest_uses_gemini_then_masks_numbers_again(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(account_digest, "_ask_gemini", lambda raw: _Digest(
        complaint="Collapsed, gasping. Card 41890.", redacted_account="[name] collapsed. Card 41890 was given."))
    d = digest_account("David collapsed. Card 41890 was given.")
    assert d.had_account and d.redacted
    assert d.complaint == "Collapsed, gasping. Card [number]." and d.account == "[name] collapsed. Card [number] was given."


def test_if_gemini_fails_the_full_account_is_held_back_and_the_summary_is_masked(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(account_digest, "_ask_gemini", lambda raw: (_ for _ in ()).throw(RuntimeError("down")))
    d = digest_account("David is gasping. His health card number is 41890. " * 8)
    assert d.had_account and not d.redacted and d.account == ""
    assert "41890" not in d.complaint and len(d.complaint) <= 201


def test_without_a_key_the_digest_still_never_raises_and_holds_the_account_back():
    d = digest_account("He is gasping, card 41890.")
    assert d.had_account and d.account == "" and "41890" not in d.complaint


def test_an_empty_account_is_not_an_account():
    assert digest_account("   ").had_account is False


# ================================================================ a fake crew engine that enforces their rules

class FakeEngine:
    """Mirrors the constraints in the real engine's request models (engine/app/models.py)."""

    FACILITIES = [{"id": "isdhoo_hc", "short_name": "Isdhoo HC", "name": "Isdhoo Health Centre", "kind": "clinic"},
                  {"id": "igmh", "short_name": "IGMH", "name": "Indira Gandhi Memorial Hospital", "kind": "hospital"}]

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.fail: dict[str, httpx.Response] = {}   # path suffix -> forced response
        self.down = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused", request=request)
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        for suffix, response in self.fail.items():
            if request.url.path.endswith(suffix):
                return response
        path = request.url.path
        if request.method == "GET" and path == "/api/meta":
            return httpx.Response(200, json={"region": {"id": "maldives", "name": "Maldives", "modes": ["boat", "plane"],
                                                        "facilities": self.FACILITIES}})
        if path == "/api/transfers":
            return self.create(body)
        if path.endswith("/monitoring"):
            return httpx.Response(200 if body["source"] in ("presage", "simulated", "off") else 422, json={})
        if path.endswith("/vitals"):
            return self.vitals(body)
        if path.endswith("/notes"):
            ok = 1 <= len(body["text"]) <= 2000 and body.get("kind", "text") in ("voice", "text", "answer")
            return httpx.Response(200 if ok else 422, json={"detail": "bad note"})
        return httpx.Response(404, json={})

    def create(self, b: dict) -> httpx.Response:
        ids = {f["id"] for f in self.FACILITIES}
        error = None
        if not str(b.get("complaint", "")).strip():
            return httpx.Response(422, json={"detail": [{"msg": "String should have at least 1 character"}]})
        if b["origin_id"] not in ids or b["destination_id"] not in ids:
            error = ("unknown_facility", "Pick a origin and destination in Maldives")
        elif b["origin_id"] == b["destination_id"]:
            error = ("same_place", "Origin and destination must differ")
        elif b["mode"] not in ("boat", "plane"):
            error = ("mode_unavailable", f"{b['mode']} is not available in Maldives")
        if error:
            return httpx.Response(422, json={"error": {"code": error[0], "message": error[1]}})
        return httpx.Response(200, json={"id": "11111111-2222-3333-4444-555555555555", "code": "AC-4F2K", "status": "preparing"})

    @staticmethod
    def vitals(b: dict) -> httpx.Response:
        ranges = {"heart_rate": (10, 300), "resp_rate": (1, 80), "confidence": (0, 1)}
        for key, (low, high) in ranges.items():
            if b.get(key) is not None and not low <= b[key] <= high:
                return httpx.Response(422, json={"detail": f"{key} out of range"})
        if b["source"] not in ("presage", "manual", "simulated"):
            return httpx.Response(422, json={"detail": "bad source"})
        if b.get("consciousness") not in (None, "A", "C", "V", "P", "U"):
            return httpx.Response(422, json={"detail": "bad consciousness"})
        return httpx.Response(200, json={"news2": None, "alerts": [], "monitoring": {}})


@pytest.fixture
def engine(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(engine_client, "_transport", fake.transport())
    return fake


ROUTE = dict(origin_id="isdhoo_hc", destination_id="igmh", mode="boat")


def test_a_full_hand_off_follows_the_order_their_api_needs(engine):
    result = engine_client.send_packet(packet(), **ROUTE)
    assert result.ok and result.code == "AC-4F2K" and result.link == "http://crew.test/crew/11111111-2222-3333-4444-555555555555"
    assert all(s.ok for s in result.steps)
    paths = [(m, p.removeprefix("/api/transfers")) for m, p, _ in engine.calls]
    assert paths == [("POST", ""), ("POST", "/11111111-2222-3333-4444-555555555555/monitoring"),
                     ("POST", "/11111111-2222-3333-4444-555555555555/vitals"), ("POST", "/11111111-2222-3333-4444-555555555555/vitals"),
                     ("POST", "/11111111-2222-3333-4444-555555555555/notes"), ("POST", "/11111111-2222-3333-4444-555555555555/notes"),
                     ("POST", "/11111111-2222-3333-4444-555555555555/notes")]


def test_the_transfer_is_created_with_the_label_age_complaint_and_route(engine):
    engine_client.send_packet(packet(), **ROUTE)
    create = engine.calls[0][2]
    assert create == {"patient": {"label": "D. M.", "age": 36, "sex": None}, "complaint": DIGEST.complaint, **ROUTE}


def test_presage_monitoring_is_switched_on_so_no_simulated_vitals_appear(engine):
    engine_client.send_packet(packet(), **ROUTE)
    assert engine.calls[1][2] == {"source": "presage"}


def test_without_real_readings_simulated_vitals_are_switched_off(engine):
    engine_client.send_packet(packet(vitals=None), **ROUTE)
    assert engine.calls[1][2] == {"source": "off"} and not any(p.endswith("/vitals") for _, p, _ in engine.calls)


def test_each_reading_goes_with_its_own_confidence_and_hint(engine):
    engine_client.send_packet(packet(), **ROUTE)
    sent = [b for _, p, b in engine.calls if p.endswith("/vitals")]
    assert sent[0] == {"source": "presage", "confidence": 0.69, "hint": "Camera notes: face not turned toward the camera, upper chest not in frame.", "heart_rate": 89.0}
    assert sent[1]["resp_rate"] == 19.0 and sent[1]["confidence"] == 0.29


def test_the_handshake_is_never_triggered_for_the_crew(engine):
    engine_client.send_packet(packet(), **ROUTE)
    assert not any(p.endswith(("/handoff", "/accept", "/arrive", "/close")) for _, p, _ in engine.calls)


def test_consciousness_is_sent_as_a_manual_entry_with_an_honest_hint_when_enabled(engine):
    p = packet(send_consciousness=True)
    engine_client.send_packet(p, **ROUTE)
    sent = [b for _, path, b in engine.calls if path.endswith("/vitals") and "consciousness" in b]
    assert sent == [{"source": "manual", "consciousness": "A", "hint": "Visual impression from video (AI), not entered by the crew"}]


def test_nothing_identifying_reaches_the_engine(engine):
    engine_client.send_packet(packet(), **ROUTE)
    wire = json.dumps([b for _, _, b in engine.calls])
    for secret in (NAME, "MC-FUNNY", ID_NUMBER, DOB, "41890"):
        assert secret not in wire, secret


def test_an_unknown_facility_is_reported_in_the_engines_own_words(engine):
    result = engine_client.send_packet(packet(), origin_id="nowhere", destination_id="igmh", mode="boat")
    assert not result.ok and result.transfer_id is None
    assert "unknown" not in result.error.lower() or "Pick a origin and destination" in result.error
    assert result.error.startswith("HTTP 422: Pick a origin and destination in Maldives")
    assert len(engine.calls) == 1   # it stopped at the first failure


@pytest.mark.parametrize("route, text", [(dict(origin_id="igmh", destination_id="igmh", mode="boat"), "must differ"),
                                         (dict(origin_id="isdhoo_hc", destination_id="igmh", mode="helicopter"), "not available")])
def test_other_route_mistakes_are_explained(engine, route, text):
    result = engine_client.send_packet(packet(), **route)
    assert not result.ok and text in result.error


def test_an_unreachable_engine_names_the_setting_to_check(engine):
    engine.down = True
    result = engine_client.send_packet(packet(), **ROUTE)
    assert not result.ok and "ENGINE_URL" in result.error and "http://engine.test" in result.error


def test_a_failure_after_creation_is_reported_but_the_transfer_stays(engine):
    engine.fail["/vitals"] = httpx.Response(422, json={"detail": "heart_rate out of range"})
    result = engine_client.send_packet(packet(), **ROUTE)
    assert result.ok and result.code == "AC-4F2K"                      # the transfer exists
    failed = [s for s in result.steps if not s.ok]
    assert len(failed) == 2 and "heart_rate out of range" in failed[0].detail
    assert sum(1 for s in result.steps if s.step.startswith("Send note") and s.ok) == 3   # notes still went


def test_an_empty_complaint_would_be_refused_so_the_packet_never_has_one():
    assert build_packet(demographics=None, vitals=None, signs=None, digest=None).complaint.strip()


def test_options_come_from_their_meta(engine):
    options = engine_client.get_options()
    assert options["region"] == {"id": "maldives", "name": "Maldives"} and options["modes"] == ["boat", "plane"]
    assert options["facilities"][0] == {"id": "isdhoo_hc", "name": "Isdhoo HC", "kind": "clinic"}


def test_options_report_an_unreachable_engine_instead_of_raising(engine):
    engine.down = True
    assert "ENGINE_URL" in engine_client.get_options()["error"]


# ================================================================ the API the page uses

def test_preview_builds_the_packet_without_sending_anything(engine):
    body = {"demographics": demographics().model_dump(), "account": "He is gasping.",
            "vitals": vitals().model_dump(), "signs": signs().model_dump()}
    resp = TestClient(app).post("/api/handshake/preview", json=body)
    assert resp.status_code == 200
    out = resp.json()
    assert out["packet"]["patient_label"] == "D. M." and out["account_checked"] is False   # no key: not forwarded in full
    assert engine.calls == []                                                               # preview sends nothing


def test_preview_works_with_nothing_at_all():
    out = TestClient(app).post("/api/handshake/preview", json={}).json()
    assert out["packet"]["complaint"] == "Pre-arrival check, no account given" and out["packet"]["vitals"] == []


def test_send_creates_the_transfer_and_logs_a_record_without_identifying_details(engine):
    body = {"packet": packet().model_dump(), **ROUTE}
    resp = TestClient(app).post("/api/handshake/send", json=body)
    assert resp.status_code == 200 and resp.json()["code"] == "AC-4F2K"
    logged = json.load(open(handshake_log.LOG_PATH, encoding="utf-8"))
    assert logged[0]["route"] == ROUTE and logged[0]["result"]["code"] == "AC-4F2K"
    wire = json.dumps(logged)
    for secret in (NAME, ID_NUMBER, DOB):
        assert secret not in wire


def test_send_reports_a_failure_without_an_error_status(engine):
    engine.down = True
    resp = TestClient(app).post("/api/handshake/send", json={"packet": packet().model_dump(), **ROUTE})
    assert resp.status_code == 200 and resp.json()["ok"] is False and "ENGINE_URL" in resp.json()["error"]


def test_options_endpoint(engine):
    assert TestClient(app).get("/api/handshake/options").json()["facilities"][1]["id"] == "igmh"


def test_a_missing_setting_is_named_clearly(monkeypatch, engine):
    monkeypatch.delattr(config, "HANDSHAKE_PATIENT_LABEL")
    monkeypatch.delenv("HANDSHAKE_PATIENT_LABEL", raising=False)
    resp = TestClient(app).post("/api/handshake/preview", json={})
    assert resp.status_code == 500 and "HANDSHAKE_PATIENT_LABEL" in resp.json()["detail"]


def test_handshake_settings_are_validated():
    with pytest.raises(config.ConfigError, match="initials, none"):
        import os
        os.environ["HANDSHAKE_PATIENT_LABEL"] = "fullname"
        try:
            config._required_choice("HANDSHAKE_PATIENT_LABEL", ("initials", "none"))
        finally:
            del os.environ["HANDSHAKE_PATIENT_LABEL"]
