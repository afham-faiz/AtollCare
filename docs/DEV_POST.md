---
title: "AtollCare: the patient's story arrives before the patient does"
published: false
tags: hackathon, healthtech, ai, webdev
cover_image: https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/06-hospital-presage-tile.jpg
---

*Built in 24 hours at OxHack 2026 (theme: **Time**) by Afham, Percy and Debanjan.*

> **TL;DR** — A phone camera measures a patient's heart and breathing rate with **Presage**, the family's spoken account
> is transcribed by **ElevenLabs**, **Gemini** turns it all into a clinical handoff, and the receiving hospital sees it
> while the patient is still on the boat. In our demo, the hospital knew **1 h 18 min before arrival**. Every transfer
> is stored on **Tiger Data** so a health service can see how fast its network responds.

![The hospital's view: heart rate measured by Presage, known 1 h 18 min before arrival](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/06-hospital-presage-tile.jpg)

## Where the idea came from

Afham is Maldivian. When we sat down on Friday night to pick a problem, he told us what a medical emergency looks like
at home.

The Maldives is about 1,200 coral islands in 26 atolls, strung out over hundreds of kilometres of the Indian Ocean.
Around 190 of them are inhabited. Most have a small health centre at best; the specialists, the cath lab and the
intensive care beds are concentrated in Malé, the capital. So when someone on an outer island has a heart attack, a
stroke, a bad fall or a complicated birth, the medicine is often not the slowest part. The journey is: a sea ambulance
for an hour or more, a seaplane that can't fly after dark, a chain of phone calls between the island, the atoll
hospital and Malé.

And during all of that, the team waiting in Malé usually knows almost nothing. They learn who the patient is, what
happened and how sick they are when the doors open.

That's why the hackathon's theme, **Time**, fit so well. We can't make the boat go faster. But every minute of that
journey could be a minute of preparation instead of a cold start at the door.

## How it works: one patient, three screens

AtollCare turns the phone everyone already has into the first monitor in the chain, and carries one patient story
through three connected screens. What is captured once is never asked again. (That's Debanjan playing the patient in
the screenshots.)

### 1. The family's phone, before anyone arrives

A family member scans the health centre's QR code. The page says *"Call 102 first"*, asks for consent, and then asks
them to film the patient for 30 seconds while saying what happened.

![The pre-arrival screen on the companion's phone](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/01-pre-arrival.jpg)

While they film, **Presage** measures heart and breathing rate from the camera, live, with hints on how to frame the
shot (*"face and chest inside the corners"*). The words they speak are transcribed by **ElevenLabs Scribe**, and
**Gemini** checks still frames for visible signs, citing the frame it saw each one in.

![Presage measuring live from the phone camera while the companion describes what happened](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/02-presage-phone-scan.jpg)

Nothing reaches the health centre until they press **Send**.

![Ready to send: Presage's heart and breathing rate and the transcribed account](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/03-ready-to-send.jpg)

### 2. The crew, on the boat

The packet is waiting on the crew's screen under *"Sent ahead from a phone"*. One tap starts the transfer with the
account, the video findings and the readings carried over.

![The crew screen: a packet sent ahead from a phone, one tap to start the transfer](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/04-crew-sent-ahead.jpg)

On the way, a propped-up phone or tablet keeps measuring with Presage. The crew add what the camera can't (oxygen
level, blood pressure, temperature, consciousness), and speak their notes: *"aspirin 300, GTN spray"* becomes a
structured handoff. Questions from the hospital are read aloud by **ElevenLabs**, so nobody has to look away from
the patient.

![Presage measuring continuously on the crew screen: steady signal, breathing 26 a minute](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/05-crew-presage-live.jpg)

### 3. The hospital, long before the doors open

The receiving team sees the patient arriving with a Presage tile (latest heart rate, the trend, and *how long before
arrival they knew*), every other measurement with its source and age, the family's own words, a Gemini-written SBAR
handoff, and one primary decision: **Accept**, with what to prepare (cath lab, resus bay). The crew hear the answer.

### 4. The people running the service

Every transfer is stored in **Tiger Data**. The insights page shows how fast handoffs are accepted, journey times,
alerts per day and which hospitals are slowest to respond.

![Network insights over 60 days on Tiger Cloud](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/07-network-insights.jpg)

## Sponsor tracks we entered

| Track | How we used it |
|---|---|
| **Best Use of Presage** (our main track) | Contactless heart rate, breathing rate and waveforms from a phone camera, live or from an uploaded clip, with Presage's own stability verdict deciding what counts |
| **Best Use of Gemini API** | Visible-sign check on video frames with cited evidence, ID reading, a live SBAR handoff, and drug/dose extraction from spoken notes, each with a fallback |
| **Best Use of ElevenLabs** | Scribe speech-to-text for the family's account and the crew's notes; hospital questions and alerts spoken aloud in the vehicle |
| **Best Use of Tiger Data** | Vitals and timelines as hypertables on Tiger Cloud, three continuous aggregates, compression, and a live benchmark |
| **DEV Writing Challenge** | This post |

## Under the hood

### Presage: the phone as the first monitor

- **Live from the phone.** The phone streams JPEG frames (30 fps, 640 px, each stamped with its capture time) over
  the app's own HTTPS address to a small Node service running the official `@smartspectra/node-sdk`. Presage answers
  with framing hints, then heart rate, breathing rate and both waveforms within seconds. If the phone can't stream,
  Presage measures the uploaded clip instead.
- **Presage's verdict decides.** A reading Presage calls stable (±3 bpm, ±1 breath/min) is scored; anything else is
  shown and labelled, never counted. Outside the cleared range, the app says so plainly: *"Camera estimate: breathing
  rate 30, count it by hand"*.
- **It changes a decision.** Two stable crew scans minutes apart that moved a lot raise *"Camera trend HR 92→124, RR
  18→25 over 3 min, take a full manual set"*: spoken in the vehicle, amber on the hospital tile, and the accept dialog
  suggests the resus bay.
- **Inside the clearance.** Presage's FDA 510(k) K254169 covers spot checks of pulse (50–150 bpm) and breathing (8–26)
  over 30 s, on a phone in a static mount, by trained staff. Our ranges are those; the crew's propped-up scan copies
  that setup; the family's video is a *bystander estimate*, shown but never scored; and a camera reading alone never
  raises a critical alert.

### Gemini

Gemini writes the SBAR handoff with a JSON response schema, only from recorded facts, with a fallback model when the
first is overloaded and a deterministic template if both fail; the screen says which one wrote it. The visible-sign
check is grounded in code: a sign can only be marked "seen" if it cites real frames.

### ElevenLabs

Scribe transcribes the family's account (it even tags *[hyperventilating]*, which a clinician wants to know) and the
crew's voice notes. Text-to-speech reads the hospital's questions and the acceptance aloud in the boat.

### Tiger Data (Tiger Cloud, TimescaleDB 2.31)

Vitals and notes are hypertables with daily chunks. A real-time 1-minute continuous aggregate of *measured* readings
feeds each patient's trend chart; two more aggregates power the insights page. With 60 days of seeded history
(about 480 transfers and 340,000 readings) on the free tier, compression shrank the older chunks from 69 MB to 12 MB
(83% smaller), and the page's live benchmark answers the same question from the aggregate in 90 ms versus 300 ms
scanning every raw reading.

![Built on Tiger Cloud: compression and the aggregate-vs-raw benchmark](https://raw.githubusercontent.com/afham-faiz/AtollCare/main/docs/images/08-tiger-cloud.jpg)

### The rest

A FastAPI engine owns the data and the clinical logic (NEWS2, a least-squares deterioration forecast, alerts with
hysteresis). Pydantic models generate the OpenAPI spec and, from it, the TypeScript types for the Next.js 16 web app.
One address serves the app, the API and the Presage service, which matters because phones only allow their camera on
HTTPS.

## Not just the Maldives

Nothing in AtollCare is specific to one country. Hospitals, clinics and transport modes live in region packs (JSON
files), and we ship two: the Maldives and Scotland's Western Isles. The same gap, a long journey and a receiving team
that knows nothing until the doors open, shows up in many places:

- **Other archipelagos:** the Philippines and Indonesia (thousands of inhabited islands each), and Pacific nations
  such as Fiji, Vanuatu, the Solomon Islands and Kiribati, where reaching a referral hospital can mean a long boat ride
  or an inter-island flight.
- **Remote islands in rich countries:** Scotland's Hebrides and Orkney, the Greek islands, Norway's coast. The air
  ambulances are excellent, but the hospital still benefits from knowing early.
- **Long road and air distances:** rural Australia (where flying doctors cover huge areas), northern Canada and
  Alaska, and rural districts in India or sub-Saharan Africa, where the nearest specialist may be hours away by road.
- **Mountains and sea:** helicopter rescues in Nepal or the Alps, and offshore platforms or ships at sea.

Anywhere a patient spends time in transit, that time can carry their story ahead of them.

## What was hard

- **Honest data.** Every value carries its source (`presage`, `manual` or `simulated`) and a timestamp. Testers still
  read our demo signal as real, so simulated values became muted, lost their status word and stopped counting: NEWS2,
  alerts and the forecast use measured readings only.
- **Designing for a moving boat.** One primary action at a time, status in words as well as colour, a hospital question
  that lands *on* the mic button, and everything spoken aloud once.
- **Narrowing the idea.** We started with a nine-screen system for the whole Maldives referral chain: a route
  optimiser, a reporter app, a dispatch board. Our testers were blunt: too much, and the one thing that should feel like
  magic (contactless vitals) wasn't there. Cutting it down to one story across three screens, with Presage on the phone
  at its centre, made it a product.
- **Free tiers at 3 a.m.** Gemini's free tier allows about 20 requests a day per model, which a few demo runs use up,
  so the engine spreads work across models and falls back cleanly.

## What's next

Presage's native mobile SDK so only numbers leave the phone, a Dhivehi interface and voice, per-hospital inboxes and
authentication, an SMS fallback for low-connectivity legs, and validation of the contactless readings against a
monitor in a real sea ambulance.

---

*Decision support only. No real patient data. Clinical thresholds and timings in the demo are illustrative.*

**Code:** [github.com/afham-faiz/AtollCare](https://github.com/afham-faiz/AtollCare)
