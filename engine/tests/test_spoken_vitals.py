# Vitals said out loud: the parser's rules, and a crew note that says them becomes a reading.
import pytest

from app.core.spoken_vitals import digits, labels, parse
from tests.test_api import client, create, ok  # noqa: F401  (client is a fixture)


@pytest.mark.parametrize(("said", "expected"), [
    ("ninety four", "94"),
    ("one twenty over eighty", "120 over 80"),
    ("one hundred and five", "105"),
    ("thirty seven point two", "37.2"),
    ("a hundred percent", "a 100 percent"),
    ("oh, and", "oh, and"),
])
def test_spoken_numbers(said, expected):
    assert digits(said) == expected


def test_reads_what_the_camera_cannot():
    h = parse("Sats 94 on air, BP 120 over 80, temp 37.2, alert")
    assert (h.spo2, h.on_oxygen, h.systolic_bp, h.diastolic_bp, h.temperature_c) == (94, False, 120, 80, 37.2)
    assert h.consciousness.value == "A"
    assert labels(h) == ["SpO₂ 94% on air", "BP 120/80", "Temp 37.2 °C", "Alert"]


def test_words_oxygen_and_more():
    h = parse("sats ninety four percent on two litres of oxygen, blood pressure one twenty over eighty, "
              "temperature thirty seven point two")
    assert (h.spo2, h.on_oxygen, h.systolic_bp, h.temperature_c) == (94, True, 120, 37.2)
    h = parse("SpO2 is 88%, BP 90/60, pulse 124, resp rate 28, confused")
    assert (h.spo2, h.systolic_bp, h.heart_rate, h.resp_rate, h.consciousness.value) == (88, 90, 124, 28, "C")


def test_fahrenheit_and_last_state_wins():
    h = parse("was confused earlier, now alert, temp 101 F")
    assert h.temperature_c == 38.3 and h.consciousness.value == "A"
    assert parse("not responding to voice, responds to pain").consciousness.value == "P"
    assert parse("unresponsive").consciousness.value == "U"


@pytest.mark.parametrize("said", [
    "Gave aspirin 300 mg, pain 8 out of 10, chest pain",
    "patient alert the hospital about allergies",
    "sat him up at 30 degrees",
    "not confused",
    "sats 140",  # out of range: heard wrong, so left out
])
def test_leaves_out_what_is_not_a_vital(said):
    h = parse(said)
    assert labels(h) == [], labels(h)


def test_heard_endpoint_records_nothing(client):  # noqa: F811
    t = create(client)
    h = ok(client.post("/api/transfers/vitals/heard", json={"text": "sats 92, BP 100 over 70"}))
    assert (h["spo2"], h["systolic_bp"], h["diastolic_bp"]) == (92, 100, 70)
    assert "spo2" not in ok(client.get(f"/api/transfers/{t['id']}"))["latest"]
    r = client.post("/api/transfers/vitals/heard/voice", files={"audio": ("v.webm", b"abc", "audio/webm")})
    assert r.status_code == 501 and r.json()["error"]["code"] == "stt_unavailable"


def test_a_crew_note_that_says_vitals_records_them(client):  # noqa: F811
    t = create(client)
    t = ok(client.post(f"/api/transfers/{t['id']}/notes",
                       json={"text": "Gave aspirin 300 mg. Sats 91 on air, BP 98 over 60, responds to voice", "kind": "voice"}))
    latest = t["latest"]
    assert latest["spo2"]["value"] == 91 and latest["spo2"]["source"] == "manual"
    assert latest["systolic_bp"]["value"] == 98 and latest["consciousness"]["value"] == "V"
    note = next(n for n in t["notes"] if n["author"] == "crew" and n["kind"] == "voice")
    assert note["extraction"]["observations"][:3] == ["SpO₂ 91% on air", "BP 98/60", "Responds to voice"]
    assert any(n["text"].startswith("Vitals from a crew note: SpO₂ 91%") for n in t["notes"])
    assert t["news2"]["total"] is not None
