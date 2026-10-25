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
Then three mock judges told us the second version still put Presage on a laptop on a stand, while the people in our
story only have phones. So the phone became the instrument.

## What we built

1. **The companion's phone** (`/pre-arrival`): "Call 102 first", consent, then film the patient for 30–60 seconds while
   saying what happened. **Presage** measures heart and breathing rate live from the camera; the words become the
   account (**ElevenLabs Scribe**). **Gemini** checks still frames for visible signs and cites the frames. Send.
2. **The crew's phone** (`/crew`): the packet is waiting; one tap starts the transfer with everything carried over.
   Presage scans on a propped-up phone, as often as the patient's acuity calls for. Voice notes become the handoff.
3. **The hospital** (`/hospital`): a Presage tile with the latest heart and breathing rate, the trace, *"known 1 h 19 min
   before arrival"*, the camera trend and the oximeter check; every other measurement with its source and age; an
   SBAR; and one primary decision: **Accept**.

## Presage: the phone as the first monitor

- **Live from the phone.** The phone sends JPEG frames (30 fps, 640 px, each stamped with its capture time) over the
  app's own HTTPS address to `presage-bridge/`, which runs the official `@smartspectra/node-sdk`. Presage answers
  with framing hints while the shot is lined up, then HR, RR, the pulse waveform and the chest-movement waveform
  within seconds. The scan ends itself once Presage calls both stable after its 30-second window. If the phone can't
  stream, Presage measures the uploaded clip instead (converted once, at constant 30 fps, from the original upload).
- **Presage's verdict decides.** A reading it calls stable (±3 bpm, ±1 breath/min) is scored; anything else is shown and
  never counted. Each scan's report shows the waveforms, when the shot wasn't usable and why ("Too much movement
  3–7 s"), a pause in breathing if Presage detects one, and how much the patient talked.
- **It changes a decision.** Two stable crew scans minutes apart that moved a lot raise *"Camera trend HR 92→124, RR
  18→25 over 3 min — take a full manual set"*: spoken in the vehicle, amber on the hospital tile, and the accept dialog
  suggests the resus bay.
- **Inside the clearance.** Presage's FDA 510(k) K254169 covers spot checks of pulse (50–150 bpm) and breathing (8–26)
  over 30 s, on a phone in a static mount, by trained staff. Our ranges are those; the crew's propped-up scan copies
  that setup; the companion's video is a *bystander estimate*, never scored; and a camera reading alone never raises a
  critical alert. When the crew enter an oximeter pulse it's checked against the camera, on screen.
- **Where the video goes.** To our server while it's measured (Presage, and Gemini on still frames). It isn't stored;
  only frames that show a sign are kept, for the hospital. Presage's native mobile SDK, keeping everything on the
  phone, is the next step.

## The rest of the stack

- **Engine (FastAPI + Pydantic):** transfer lifecycle (`preparing → pending → accepted → arrived → closed`), NEWS2
  (partial until the crew add SpO₂ / BP / temperature / ACVPU), a least-squares deterioration forecast, and alerts with
  hysteresis so they don't flap. Pydantic models generate the OpenAPI spec and, from that, the web app's TypeScript
  types.
- **Gemini** writes the SBAR with a JSON response schema and only from recorded facts. A deterministic template takes
  over if it fails, and the UI says which one wrote it.
- **Tiger Data:** vitals and notes are hypertables with daily chunks. A real-time 1-minute continuous aggregate of
  *measured* readings feeds each patient's trend chart and forecast (the chart says which aggregate answered, and in
  how many ms). Two more aggregates power a Network insights page for operations leads: time to acceptance, the
  slowest hospitals, alerts and questions per day. Columnar compression after a week took 60 days of seeded history
  from 71 MB to 12 MB, and the page runs a live benchmark: 2.6 ms from the aggregate vs 22.8 ms scanning 189k rows.
- **Vultr:** engine + web on Cloud Compute behind Caddy (automatic HTTPS via sslip.io), deployed with one script; the
  engine reads Vultr's instance metadata so the presenter panel shows the region it's really running in. The bridge
  in the vehicle posts to it.
- **Web (Next.js 16):** a light, quiet clinical interface. The crew screen fits a 1024×768 tablet without scrolling,
  and the hospital detail pane lays out by its own width with container queries.

## What was hard

- **Being honest about data provenance.** Every value carries `presage`, `manual` or `simulated` and a timestamp,
  rendered next to the number. Testers still read our "demo signal" as real, so simulated values became muted, lost
  their status word, and stopped counting: NEWS2, alerts and the forecast use measured readings only. Prepared demo
  cases now pre-fill nothing.
- **Designing for a moving vehicle.** One primary action at a time, status in words as well as colour, a hospital
  question that lands *on* the mic button, and everything spoken aloud once.
- **A demo that survives stage conditions.** Prepared cases, a presenter panel behind a shortcut, a sim clock for the
  journey, and a typed fallback for every voice step.

## What's next

Presage's native mobile SDK so only numbers leave the phone, per-hospital inboxes and authentication, push instead of
polling, SMS fallback for low-connectivity legs, and validation of the contactless readings against a monitor in a
real vehicle.

*Decision support only. No real patient data. Clinical thresholds and timings in the demo are illustrative.*
