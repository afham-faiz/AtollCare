"""E2E: play the demo story through the live API.

start transfer (crew only, "preparing") → contactless vitals (as the Presage bridge would post) → manual vitals →
crew voice note → send handoff (now the hospital sees it) → hospital question → crew answer → accept →
fast-forward to arrival → close.

Usage:  uv run --project engine python scripts/demo_e2e.py [--base http://localhost:8000]
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    api = httpx.Client(base_url=args.base.rstrip("/") + "/api", timeout=30)

    def call(method: str, path: str, **kw):
        r = api.request(method, path, **kw)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} → {r.status_code}: {r.text}")
        return r.json()

    print("health:", call("GET", "/health"))
    call("POST", "/demo/reset")
    call("PATCH", "/demo/state", json={"region_id": "maldives", "speed_multiplier": 1})
    t = call("POST", "/transfers", json={
        "patient": {"label": "E2E", "age": 58, "sex": "M"},
        "complaint": "Crushing chest pain for 40 minutes, sweating, pain to the left arm",
        "origin_id": "dhiffushi_hc", "destination_id": "igmh", "mode": "boat",
    })
    tid = t["id"]
    print(f"started {t['code']}: {t['distance_km']} km, ETA {t['eta']}")

    for hr, rr in [(96, 18), (101, 19), (106, 21)]:
        call("POST", f"/transfers/{tid}/vitals", json={"source": "presage", "heart_rate": hr, "resp_rate": rr,
                                                        "hrv_rmssd": 24, "confidence": 0.8})
    ack = call("POST", f"/transfers/{tid}/vitals", json={"spo2": 95, "on_oxygen": False, "systolic_bp": 104,
                                                          "temperature_c": 36.8, "consciousness": "A"})
    print("NEWS2:", ack["news2"]["total"], ack["news2"]["band"], "alerts:", [a["text"] for a in ack["alerts"]])

    t = call("POST", f"/transfers/{tid}/notes", json={"text": "Gave aspirin 300 mg and GTN spray. Oxygen 4 litres. "
                                                               "Pain 8 out of 10, sweating.", "kind": "voice"})
    print("interventions:", [i["text"] for i in t["interventions"]])

    def hospital_sees() -> bool:
        return any(x["id"] == tid for x in call("GET", "/transfers", params={"status": "pending,accepted,arrived"}))

    assert not hospital_sees(), "a transfer still being prepared must not reach the hospital"
    t = call("POST", f"/transfers/{tid}/handoff")
    assert t["status"] == "pending", t["status"]
    assert hospital_sees()
    print("handoff sent:", t["notes"][-1]["text"])
    t = call("POST", f"/transfers/{tid}/messages", json={"text": "Any allergy to blood thinners?", "sender": "Dr E2E"})
    q = next(n for n in t["notes"] if n["kind"] == "question")
    call("POST", f"/transfers/{tid}/notes", json={"text": "No known allergies", "reply_to": q["id"]})
    t = call("POST", f"/transfers/{tid}/accept", json={"by": "Dr E2E (Cardiology)", "prepare": ["Cath lab"]})
    print("accepted:", t["notes"][-1]["text"])
    print("briefing:", t["briefing"]["situation"])

    call("PATCH", "/demo/state", json={"speed_multiplier": 120})
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        t = call("GET", f"/transfers/{tid}")
        print(f"  status={t['status']:<9} progress={t['progress']:.2f} vitals={len(t['vitals'])}", end="\r")
        if t["status"] == "arrived":
            break
        time.sleep(2)
    print()
    call("PATCH", "/demo/state", json={"speed_multiplier": 1})
    if t["status"] != "arrived":
        print("FAIL: did not arrive in time")
        return 1
    trend = call("GET", f"/transfers/{tid}/vitals/trend")
    t = call("POST", f"/transfers/{tid}/close")
    print(f"closed {t['code']}: {len(t['notes'])} timeline entries, {len(trend['buckets'])} trend buckets "
          f"({trend['source']})")
    assert t["status"] == "closed"
    assert any(v["source"] == "presage" for v in t["vitals"])
    assert any(n["kind"] == "answer" for n in t["notes"])
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
