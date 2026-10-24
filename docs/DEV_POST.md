---
title: "AtollCare: turning a phone chain into a parallel handoff for island emergencies"
published: false
tags: hackathon, healthtech, ai, python
---

> Draft for the DEV Writing Challenge — edit, add screenshots and the live URL, then publish.

## The problem: distance and handoffs, not money

The Maldives has around 190 inhabited islands across ~90,000 km² of ocean. Specialist care — cath lab, neurosurgery,
ICU — is concentrated in Malé. When someone on an outer island has a heart attack, the clock is eaten by a
*sequential phone chain*: health centre → atoll hospital → specialist in Malé → evacuation approval → transport
operator. Each call waits for the previous one; information is lost at every hop.

Transport is constrained too. Seaplanes are fast but daylight-only. Speedboats stop running in rough seas. Fixed-wing
flights only connect airports. A good decision needs the clock, the weather, the treatment window *and* live hospital
capacity at the same time.

## What we built

**AtollCare** is one live case that travels with the patient:

1. **Island** — a giant *Raise medical alert* button, voice or text description, a 30-second contactless face scan for
   heart and breathing rate, and first-aid guidance read aloud.
2. **Decision engine** — NEWS2 scoring, condition and treatment window, every feasible route (sea, seaplane,
   fixed-wing chains, interim stabilisation stops), scored and explained.
3. **Hospital** — an SBAR referral, vitals trend with a hedged deterioration forecast, one-click accept / decline /
   request info. Declines re-route automatically.
4. **Transport** — dispatch board, live map, accelerated simulator, spoken status updates for the family.

The headline on every screen: *Symptom → definitive care: X h Y min, Z min faster than the phone chain.*

## How each sponsor's tech fits

- **Presage SmartSpectra** — the phone records a 30 s face video; the engine's `PresageAdapter` turns it into HR and
  RR, which feed NEWS2 (as a clearly labelled *partial* score) and the vitals trend.
- **Gemini** — structured intake from messy text (JSON schema output constrained to our condition IDs), SBAR summaries,
  a plain-language explanation of why a route won, and *selecting* (never writing) steps from a vetted first-aid
  library. Every call has a deterministic fallback.
- **ElevenLabs** — Scribe speech-to-text for voice intake; TTS for first-aid steps, family status updates and a crew
  brief, cached by content hash in object storage.
- **Tiger Data** — `vitals_readings`, `transport_positions` and `case_events` are hypertables; a `vitals_1m`
  continuous aggregate with real-time aggregation feeds the trend chart and the least-squares forecast.
- **Vultr** — the whole stack runs on a Cloud Compute VM with Docker Compose and Caddy (automatic HTTPS via
  `sslip.io`), with scan videos and audio in Vultr Object Storage.

## The engine, briefly

The interesting part is deterministic and tested. Routes are enumerated per candidate hospital from templates —
direct sea, seaplane (with Malé reached via the Hulhulé seaplane base), sea → fixed-wing → ground chains, and
*interim-stop* plans (e.g. fibrinolysis at a regional hospital, then onward). Assets are dispatched in parallel at time
zero, so a fixed-wing can be flying to Kadhdhoo while the speedboat is still at sea.

```
score = total_min + 3 × window breach − medic bonus + 15 per extra handover + 1000 if infeasible
```

If no route reaches definitive care inside the window, the engine picks the best plan that meets the *interim*
window and says so: "No route reaches PCI within 120 min. Recommended: fibrinolysis at Gan Regional (ETA 51 min), then
by fixed-wing to IGMH." Infeasible routes stay visible with reasons ("seaplane: night — after sunset 18:15").

## Challenges

- **A night scenario during a daytime pitch.** Everything runs on a simulated clock with an offset and speed
  multiplier, so we can jump to 21:00 and watch a boat cross an atoll at 60×.
- **Not letting AI make clinical decisions.** The LLM extracts and explains; a clinical standard scores; an auditable
  optimiser decides; humans act.
- **Presage in the browser.** There's no confirmed browser SDK, so we record video client-side and process it on the
  server behind an adapter with `sdk | cloud | mock | manual` modes.

## What's next

Real referral and transport timing data, Dhivehi voice once verified, SMS/WhatsApp intake, and integration with
national health records — plus the same model for the Pacific, Indonesia, the Philippines and the Scottish isles.

*Decision support only. All clinical windows, speeds and capabilities in the demo are illustrative assumptions.*
