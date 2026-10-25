# AtollCare — product brief (v3, Presage on the phone)

> **The patient's story arrives before the patient does.**

## Focus

Remote emergency **transfers** — island, rural, maritime, mountain — where a patient spends 30 minutes to several
hours in a boat, ambulance or aircraft before reaching the hospital that can treat them. Today the receiving team
learns almost nothing until the doors open.

AtollCare makes the phone everyone already has into the first monitor in the chain. **Presage** reads heart and
breathing rate from the camera, with no contact, in 30 to 60 seconds: first on the companion's phone before anyone
reaches the health centre, then on the crew's phone, propped up in the boat, as often as the patient's acuity calls
for. The receiving hospital sees every reading with where it came from, how long before arrival it knew, and when
the camera trend says to prepare more.

Region-neutral: regions are data packs (hospitals, clinics, transport modes, the emergency number). The Maldives and
the Scottish Western Isles ship as examples.

## Three screens, one story, captured once

| Screen | Device | What it does |
|---|---|---|
| **Pre-arrival** `/pre-arrival` | The companion's phone | "Call 102 first." Consent. Film the patient for 30–60 s while saying what happened: Presage measures live, the words become the account. Optional ID photo. Send. |
| **Crew** `/crew` | The crew's phone (or a mounted tablet) | Packets sent ahead; one tap starts the transfer with everything carried over. Presage scans on a propped-up phone, timed by acuity. Voice notes → handoff. Hospital replies read aloud. |
| **Hospital** `/hospital` | Desktop / tablet | The Presage tile (latest HR and RR, the trace, "known 1 h 19 min before arrival", the camera trend, the oximeter check) · vitals with source and age · SBAR · seen on video · **Accept**. |

## Why Presage is the main track

- **It runs from the phone, live.** The phone streams JPEG frames to the SmartSpectra SDK (`presage-bridge/`) over the
  app's own HTTPS address. Framing hints come back while the shot is lined up; HR, RR, the pulse and breathing
  waveforms within seconds. If the phone can't stream, Presage measures the uploaded clip instead.
- **Presage's own verdict decides.** A reading Presage calls stable (±3 bpm, ±1 breath/min) is scored; anything else is
  shown and labelled, never counted. Its framing problems, apnea detection and talking detection are shown in every
  scan's report.
- **It changes a decision.** Two stable scans minutes apart that moved a lot raise "Camera trend HR 92→124 — take a full
  manual set", spoken in the vehicle; the hospital's accept dialog suggests the resus bay.
- **Inside the clearance, said out loud.** Presage's FDA 510(k) K254169 covers spot checks of pulse (50–150) and
  breathing (8–26) over 30 s, on a phone in a static mount, by trained staff. The crew's propped-up scan copies that.
  The companion's video is labelled a bystander estimate and never scored. A camera reading alone never raises a
  critical alert; the crew's oximeter pulse is checked against the camera every time it's entered.
- **Privacy, plainly.** The picture goes to our server while it's measured (Presage, and Gemini on still frames); the
  video isn't stored, and only frames that show a sign are kept for the hospital. Presage's native mobile SDK, keeping
  everything on the phone, is the next step.

## Sponsor tracks

| Track | Role in the product |
|---|---|
| **Presage** (main) | Live HR, RR, pulse and breathing waveforms, framing hints, apnea and talking from the phone; serial-scan trend; oximeter check |
| **Gemini** | Visible signs checked frame by frame with the frames cited; ID read; the account condensed (age and sex when stated); the SBAR |
| **ElevenLabs** | Speech to text (the companion's account from the video's sound, crew notes); hospital replies spoken in the vehicle |
| **Tiger Data** | Hypertables + a real-time 1-minute aggregate of measured readings; network aggregates and compression behind Network insights |
| **Vultr** | Engine + web on Cloud Compute behind Caddy HTTPS |

## The demo

Script, setup, fallbacks and hard questions: [`PITCH.md`](PITCH.md).

## Not doing now

- Presage's native iOS/Android SDK (next step: only numbers leave the phone).
- Real authentication, per-hospital inboxes, push instead of polling, SMS fallback, offline queue.
- The route optimiser, dispatch board, first-aid library.

*Decision support only. No real patient data.*
