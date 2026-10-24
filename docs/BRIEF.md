# AtollCare — product brief (v2, refocused)

> **The patient's story arrives before the patient does.**

## Focus

Remote emergency **transfers** — island, rural, maritime, mountain — where a patient spends 30 minutes to several
hours in a boat, ambulance or aircraft before reaching the hospital that can treat them. Today the receiving team
learns almost nothing until the doors open.

AtollCare puts a camera on a mount in the vehicle. **Presage** reads heart rate, breathing rate and HRV hands-free
while the crew keeps both hands on the patient. The crew **talk** instead of typing. The receiving hospital sees a
live briefing and a vitals trend, can accept with one tap, and can ask questions that are **spoken aloud** in the
vehicle.

It is region-neutral. Regions are data packs (hospitals, clinics, transport modes). The Maldives and the Scottish
Western Isles ship as examples, and a new region is a single JSON file.

## Two screens, one story

| Screen | Device | What it shows (nothing else) |
|---|---|---|
| **Crew** `/crew` | Tablet or laptop on a mount, landscape | Patient + status · camera instrument with framing guide · live HR / RR / HRV and breathing waveform (Presage) · crew-entered SpO₂ / BP / temp / ACVPU · NEWS2 · one mic button · **Send handoff** · hospital questions and acceptance, read aloud · ETA |
| **Hospital** `/hospital` | Desktop / tablet | Incoming transfers · condition, urgency, arrival · vitals with source and age · SBAR + what's been given · trend · **Accept** (primary) · Ask the crew · map (secondary) |

A transfer is **crew-only while it's being prepared**. The hospital sees it the moment the crew send the handoff.

## Why Presage is the main track

- **The setup matches what Presage is validated for:** a mounted camera, a patient lying still, face and upper chest
  visible. A handheld phone held by a bystander who is also talking does not.
- **It's a real integration, not a mock-up:** `presage-bridge/` runs the official `@smartspectra/node-sdk` next to the
  camera (Windows, macOS and Linux). The browser streams frames to it and gets HR, RR, HRV, breathing waveform and
  framing hints back ("face too far", "chest not visible").
- **Privacy story:** video never leaves the vehicle. Only the numbers go to the cloud.
- **Honest limits shown in the UI:** pulse is validated for 40–110 BPM (higher readings are flagged *confirm
  manually*). Breathing takes 30 s to settle. Contactless HR + RR give only a *partial* NEWS2, and the crew adds
  SpO₂ / BP / temperature / ACVPU with a few taps.
- **No API key? The demo still works:** a clearly labelled *demo signal* takes over, on both screens and in the SBAR.

## Sponsor tracks

| Track | Role in the product |
|---|---|
| **Presage** (main) | Live hands-free HR, RR, HRV and breathing waveform from the mounted camera |
| **ElevenLabs** | Crew voice notes → text (Scribe); hospital questions and alerts spoken in the vehicle (TTS) |
| **Gemini** | Turns vitals + voice notes into a live SBAR briefing; extracts interventions ("aspirin 300 mg, 21:14") |
| **Tiger Data** | Vitals hypertable + 1-minute continuous aggregate → trend chart and deterioration forecast |
| **Vultr** | Engine + web on Cloud Compute behind Caddy HTTPS; the bridge posts to it from the vehicle |

## The demo (3 minutes)

Full script with setup and backups: [`PITCH.md`](PITCH.md).

1. **Crew screen** on a laptop on a stand. A teammate lies back as the patient. Prepared case *Chest pain on a sea
   ambulance* (presenter panel, Ctrl + .). Presage acquires → HR and RR appear as *Presage · live*, the breathing
   waveform moves.
2. Crew taps the mic: "Gave aspirin 300 milligrams and GTN spray, oxygen four litres, pain eight out of ten." → chips
   appear. **Send handoff** → review → send.
3. **Hospital screen**: the transfer arrives with condition, urgency, arrival time, sourced vitals and the SBAR.
   **Ask the crew**: "On blood thinners?" → the laptop speaks it → crew answer by voice.
4. **Accept** · cath lab · "Come straight to the cath lab" → the crew dock shows it, and the vehicle hears it.
5. Close: "Same app, any region": Western Isles → *Suspected stroke, island to Glasgow*.

## What we are dropping

- The phone reporter app, first-aid library, family link / QR, offline queue, language selector.
- The route optimiser UI, dispatch board, asset roster, capacity panel, weather / daylight controls, engine
  inspector, "time saved vs phone chain" panel, five scripted scenarios, role switcher, dark mode.
- The Maldives as the story. It stays as one example region pack.

## Explicitly out of scope

Real authentication, multi-tenant hospitals, device/sensor integrations beyond the camera, national record systems,
SMS/WhatsApp (pitch them as next steps).
