---
title: "AtollCare: the patient's story arrives before the patient does"
published: false
tags: hackathon, healthtech, ai, mlh
---

*Built in 24 hours at OxHack 2026 (theme: **Time**) by Afham, Percy and Debanjan.*

## Where the idea came from

Afham is Maldivian. When we sat down on Friday night to pick a problem, they told us what a medical emergency looks
like at home.

The Maldives is about 1,200 coral islands in 26 atolls, strung out over hundreds of kilometres of the Indian Ocean.
Around 190 of them are inhabited. Most have a small health centre at best; the specialists, the cath lab and the
intensive care beds are concentrated in Malé, the capital. So when someone on an outer island has a heart attack, a
stroke, a bad fall or a complicated birth, the medicine is often not the slowest part. The journey is: a sea ambulance
for an hour or more, a seaplane that can't fly after dark, a chain of phone calls between the island, the atoll
hospital and Malé.

And during all of that, the team waiting in Malé usually knows almost nothing. They learn who the patient is, what
happened and how sick they are when the doors open. Every minute of that journey could have been a minute of
preparation. That gap is what we built for, and it's why the hackathon's theme, *Time*, fit so well: we can't make the
boat go faster, but we can make the time on it count.

## What we built

AtollCare turns the phone everyone already has into the first monitor in the chain, and carries one patient story
through three connected screens. What is captured once is never asked again.

1. **The companion's phone** (`/pre-arrival`). A family member scans the health centre's QR code. "Call 102 first",
   consent, then they film the patient for 30–60 seconds while saying what happened. **Presage** measures heart and
   breathing rate live from the camera, with hints on framing the shot. The spoken words become the account
   (**ElevenLabs Scribe**, with Gemini as a fallback). **Gemini** checks still frames for visible signs and cites the
   frame it saw each one in. An optional ID photo is read by Gemini. Nothing is sent until they press **Send**.
2. **The crew's phone** (`/crew`). The packet is waiting; one tap starts the transfer with everything carried over.
   Presage scans on a propped-up phone, as often as the patient's acuity calls for. The crew speak their notes ("aspirin
   300, GTN spray"), Gemini turns them into a structured handoff, and the hospital's questions are read aloud in the
   boat by **ElevenLabs**, so nobody has to look away from the patient.
3. **The hospital** (`/hospital`). A Presage tile with the latest heart and breathing rate, the trace, *"known 1 h 19 min
   before arrival"*, the camera trend and an oximeter cross-check; every other measurement with its source and age; what
   was seen on video; an SBAR handoff; and one primary decision: **Accept**.
4. **Network insights** (`/insights`). For the people running the service: time to acceptance by hospital, journey
   times, alerts and questions per day, built on **Tiger Data**.

## Sponsor tracks we entered

| Track | How we used it |
|---|---|
| **Best Use of Presage** (our main track) | Contactless heart rate, breathing rate and waveforms from a phone camera, live or from an uploaded clip, with Presage's own stability verdict deciding what counts |
| **Best Use of Gemini API** | Visible-sign check on video frames with cited evidence, ID reading, live SBAR handoff, and drug/dose extraction from spoken notes, each with a fallback |
| **Best Use of ElevenLabs** | Scribe speech-to-text for the companion's account and crew notes; hospital questions and alerts spoken aloud in the vehicle |
| **Best Use of Tiger Data** | Vitals and timelines as hypertables on Tiger Cloud, three continuous aggregates, compression, and a live benchmark |
| **DEV Writing Challenge** | This post |

## Presage: the phone as the first monitor

- **Live from the phone.** The phone sends JPEG frames (30 fps, 640 px, each stamped with its capture time) over the
  app's own HTTPS address to `presage-bridge/`, which runs the official `@smartspectra/node-sdk`. Presage answers with
  framing hints while the shot is lined up, then heart rate, breathing rate, the pulse waveform and the chest-movement
  waveform within seconds. The scan ends by itself once Presage calls both stable. If the phone can't stream, Presage
  measures the uploaded clip instead.
- **Presage's verdict decides.** A reading it calls stable (±3 bpm, ±1 breath/min) is scored; anything else is shown and
  labelled, never counted. Each scan's report shows the waveforms, when the shot wasn't usable and why ("Too much
  movement 3–7 s"), a pause in breathing if Presage detects one, and how much the patient talked.
- **It changes a decision.** Two stable crew scans minutes apart that moved a lot raise *"Camera trend HR 92→124, RR
  18→25 over 3 min, take a full manual set"*: spoken in the vehicle, amber on the hospital tile, and the accept dialog
  suggests the resus bay.
- **Inside the clearance.** Presage's FDA 510(k) K254169 covers spot checks of pulse (50–150 bpm) and breathing (8–26)
  over 30 s, on a phone in a static mount, by trained staff. Our ranges are those; the crew's propped-up scan copies that
  setup; the companion's video is a *bystander estimate*, shown but never scored; and a camera reading alone never
  raises a critical alert.
- **Where the video goes.** To our server while it's measured, then discarded; only frames that show a sign are kept,
  for the hospital. Presage's native mobile SDK, keeping everything on the phone, is the next step.

## The rest of the stack

- **Engine (FastAPI + Pydantic):** the transfer lifecycle (`preparing → pending → accepted → arrived → closed`), NEWS2
  (partial until the crew add SpO₂, blood pressure, temperature and consciousness), a least-squares deterioration
  forecast, and alerts with hysteresis so they don't flap. Pydantic models generate the OpenAPI spec and, from that, the
  web app's TypeScript types.
- **Gemini** writes the SBAR with a JSON response schema, only from recorded facts, with a fallback model when the
  first is overloaded and a deterministic template if both fail. The UI says which one wrote it. The sign check is
  grounded in code: a sign can only be "seen" if it cites real frames.
- **Tiger Data (Tiger Cloud, TimescaleDB 2.31):** vitals and notes are hypertables with daily chunks. A real-time
  1-minute continuous aggregate of *measured* readings feeds each patient's trend chart and forecast; two more
  aggregates power the insights page. With 60 days of seeded history (480 transfers, about 340,000 readings) on the
  free tier, compression shrank the older chunks from 69 MB to 12 MB (83% smaller), and the page's live benchmark
  answers the same question from the aggregate in about 90 ms versus 300 ms scanning every raw reading.
- **Web (Next.js 16):** a calm clinical interface. The crew screen fits a 1024×768 tablet without scrolling, and the
  same address serves the app, the API and the Presage bridge, which matters because phones only allow their camera on
  HTTPS.

## Not just the Maldives

Nothing in AtollCare is specific to one country. Hospitals, clinics and transport modes live in region packs (JSON
files), and we ship two: the Maldives and Scotland's Western Isles. The same gap, a long journey and a receiving team
that knows nothing until the doors open, shows up in many places:

- **Other archipelagos:** the Philippines and Indonesia (thousands of inhabited islands each), and Pacific nations such
  as Fiji, Vanuatu, the Solomon Islands and Kiribati, where transfers to a referral hospital can mean a long boat ride or
  an inter-island flight.
- **Remote islands in rich countries:** Scotland's Hebrides and Orkney, the Greek islands, Norway's coast. The air
  ambulances are excellent, but the hospital still benefits from knowing early.
- **Long road and air distances:** rural Australia (where flying doctors cover huge areas), northern Canada and Alaska,
  and rural districts in India or sub-Saharan Africa, where the nearest specialist may be hours away by road.
- **Mountains and sea:** helicopter rescues in Nepal or the Alps, and offshore platforms or ships at sea.

Anywhere the patient spends time in transit, that time can carry their story ahead of them.

## What was hard

- **Being honest about data provenance.** Every value carries `presage`, `manual` or `simulated` and a timestamp,
  rendered next to the number. Testers still read our demo signal as real, so simulated values became muted, lost their
  status word and stopped counting: NEWS2, alerts and the forecast use measured readings only.
- **Designing for a moving boat.** One primary action at a time, status in words as well as colour, a hospital question
  that lands *on* the mic button, and everything spoken aloud once.
- **Narrowing the idea.** We started with a nine-screen system for the whole Maldives referral chain: a route optimiser,
  a reporter app, a dispatch board. Our testers were blunt: too much, and the one thing that should feel like magic
  (contactless vitals) wasn't there. Cutting it down to one story across three screens, with Presage on the phone at
  its centre, made it a product.
- **Free-tier limits at 3 a.m.** Gemini's free tier allows about 20 requests a day per model, which a few demo runs
  use up, so the engine spreads work across models and falls back cleanly.

## What's next

Presage's native mobile SDK so only numbers leave the phone, a Dhivehi interface and voice, per-hospital inboxes and
authentication, an SMS fallback for low-connectivity legs, and validation of the contactless readings against a
monitor in a real sea ambulance.

*Decision support only. No real patient data. Clinical thresholds and timings in the demo are illustrative.*

**Code:** https://github.com/afham-faiz/AtollCare
