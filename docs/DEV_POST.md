---
title: "AtollCare: the patient's story arrives before the patient does"
published: false
tags: hackathon, healthtech, ai, webdev
---

> Draft for the DEV Writing Challenge. Add screenshots, a short video and the live URL, then publish.

## The problem

Remote emergency transfers (island, rural, maritime, mountain) can put a patient in a boat, ambulance or aircraft
for an hour or more before they reach the hospital that can treat them. The crew have both hands on the patient. The
receiving team, meanwhile, knows almost nothing until the doors open.

We started with a nine-screen prototype for the Maldives: route optimiser, reporter app, dispatch board. Our
testers were blunt. Too much, too specific, and the one thing that should feel magic (contactless vitals) didn't work.
So we cut it to **two screens** and one loop.

## What we built

1. **Crew screen**: a tablet on a mount. The camera reads heart rate, breathing rate and HRV with **Presage**. The
   crew tap once and talk. **ElevenLabs Scribe** transcribes, and **Gemini** pulls out what was given ("Aspirin
   300 mg · GTN spray · Oxygen 4 litres"). One tap sends the handoff.
2. **Hospital screen**: who's arriving, how sick, what's been given, every measurement with its source and age, an
   SBAR, the ETA, and one primary decision: **Accept**. Questions typed here are spoken aloud in the vehicle. The
   acceptance, and what's being prepared, appears on the crew screen.

## Presage: making the camera an instrument

Presage's SmartSpectra is validated for a camera that *isn't* handheld, with the face and upper chest in view, a
still patient, and about 30 seconds for breathing to settle. That's exactly a mounted tablet in an ambulance, so we
designed around it:

- **`presage-bridge/`** runs the official `@smartspectra/node-sdk` next to the camera. The browser streams RGBA frames
  over a local WebSocket (16-byte header: magic, width, height, capture time) into `sendFrame`, and gets back HR, RR,
  HRV, the breathing trace and framing hints ("Too far — move the camera closer", "Chest not visible — show the
  upper chest").
- **Video never leaves the vehicle.** Every 5 s the bridge posts only *stable* numbers to the engine.
- **The UI tells the truth.** Readings show *Presage · acquiring* until they're stable. Pulse above the validated
  110 BPM is flagged *confirm with a monitor*. Without a key the vitals are **Simulated**: muted, with no clinical status word,
  and labelled on both screens and in the SBAR as "(simulated)".

## The rest of the stack

- **Engine (FastAPI + Pydantic):** transfer lifecycle (`preparing → pending → accepted → arrived → closed`), NEWS2
  (partial until the crew add SpO₂ / BP / temperature / ACVPU), a least-squares deterioration forecast, and alerts with
  hysteresis so they don't flap. Pydantic models generate the OpenAPI spec and, from that, the web app's TypeScript
  types.
- **Gemini** writes the SBAR with a JSON response schema and only from recorded facts. A deterministic template takes
  over if it fails, and the UI says which one wrote it.
- **Tiger Data:** vitals and notes are hypertables. A one-minute continuous aggregate with real-time aggregation feeds
  the trend chart and forecast.
- **Vultr:** engine + web on Cloud Compute behind Caddy (automatic HTTPS). The bridge in the vehicle posts to it.
- **Web (Next.js 16):** a light, quiet clinical interface. The crew screen fits a 1024×768 tablet without scrolling,
  and the hospital detail pane lays out by its own width with container queries.

## What was hard

- **Being honest about data provenance.** Every value carries `presage`, `manual` or `simulated` and a timestamp.
  We render it next to the number, not in a legend.
- **Designing for a moving vehicle.** One primary action at a time, status in words as well as colour, a hospital
  question that lands *on* the mic button, and everything spoken aloud once.
- **A demo that survives stage conditions.** Prepared cases, a presenter panel behind a shortcut, a sim clock for the
  journey, and a typed fallback for every voice step.

## What's next

Per-hospital inboxes and authentication, push instead of polling, SMS fallback for low-connectivity legs, and
validation of the contactless readings against a monitor in a real vehicle.

*Decision support only. No real patient data. Clinical thresholds and timings in the demo are illustrative.*
