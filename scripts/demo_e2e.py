"""§13 E2E: run the hero scenario through the live API.

create → intake → vitals → assess → refer → accept → dispatch → simulate to arrival (300×) → close.
Asserts final status `closed` and `saved_vs_baseline_min > 0`.

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
    parser.add_argument("--timeout", type=float, default=180, help="seconds to wait for arrival")
    args = parser.parse_args()
    api = httpx.Client(base_url=args.base.rstrip("/") + "/api", timeout=30)

    def call(method: str, path: str, **kw):
        r = api.request(method, path, **kw)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} → {r.status_code}: {r.text}")
        return r.json()

    print("health:", call("GET", "/health"))
    call("POST", "/demo/reset")
    call("PATCH", "/demo/state", json={"set_time_of_day": "21:00", "speed_multiplier": 1,
                                         "weather": {"sea_state": 2, "wind_kt": 10, "visibility_km": 10},
                                         "clear_night_override": True})

    case = call("POST", "/cases", json={"origin_facility_id": "isdhoo_hc",
                                         "patient": {"name": "E2E", "age": 58, "sex": "M"}},
                headers={"X-Role": "reporter"})
    cid = case["id"]
    print("created", case["short_code"])
    call("POST", f"/cases/{cid}/intake", json={
        "raw_text": "Crushing chest pain for 40 minutes, sweating, pain going to his left arm."})
    call("POST", f"/cases/{cid}/vitals", json={"source": "presage", "heart_rate": 112, "resp_rate": 24,
                                                "confidence": 0.9})
    call("POST", f"/cases/{cid}/submit")
    call("POST", f"/cases/{cid}/vitals", json={"heart_rate": 114, "resp_rate": 24, "spo2": 95, "on_oxygen": False,
                                                "systolic_bp": 104, "temperature_c": 36.8, "consciousness": "A"},
         headers={"X-Role": "clinician"})
    case = call("POST", f"/cases/{cid}/assess")
    rec = case["recommendation"]
    chosen = next(r for r in rec["alternatives"] if r["id"] == rec["chosen_route_id"])
    print(f"recommendation: {rec['severity']} {rec['primary_condition_id']} → {rec['destination_id']}")
    print("  route:", chosen["label"], f"({chosen['total_min']} min)")
    print("  breach:", rec["breach_warning"])
    assert chosen.get("interim_stop_id") == "gan_l_rh", "hero should stop at Gan Regional for fibrinolysis"

    call("POST", f"/cases/{cid}/refer", json={"note": "E2E referral"}, headers={"X-Role": "clinician"})
    case = call("POST", f"/cases/{cid}/referral/respond",
                json={"response": "accepted", "responder_name": "Dr E2E (IGMH)"})
    assert case["status"] == "accepted"
    case = call("POST", f"/cases/{cid}/dispatch", json={"route_id": case["recommendation"]["chosen_route_id"]})
    print("dispatched, ETA", case["transport"]["eta"])

    call("PATCH", "/demo/state", json={"speed_multiplier": 300})
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        case = call("GET", f"/cases/{cid}")
        print(f"  status={case['status']:<10} leg={case['transport']['current_leg_index']} "
              f"pos={case['transport']['position']}", end="\r")
        if case["status"] == "arrived":
            break
        time.sleep(2)
    print()
    call("PATCH", "/demo/state", json={"speed_multiplier": 1})
    if case["status"] != "arrived":
        print("FAIL: did not arrive in time")
        return 1
    case = call("POST", f"/cases/{cid}/close", json={"outcome_note": "E2E complete"})
    saved = case["headline"]["saved_vs_baseline_min"]
    print("closed:", case["headline"]["text"])
    track = call("GET", f"/cases/{cid}/track")
    print(f"track points: {len(track['positions'])}; timeline events: {len(case['timeline'])}")
    assert case["status"] == "closed", case["status"]
    assert saved is not None and saved > 0, saved
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
