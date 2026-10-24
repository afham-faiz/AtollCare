# Pitch: 3 minutes

**Before going on stage**

- Crew laptop on a stand, camera angled at a teammate reclining as the patient (face and upper chest in view, lit from
  the front). The Presage bridge runs on it with a real key. Chrome or Edge, camera and mic allowed.
- Second screen (or laptop) on `/hospital`, showing "No incoming transfers".
- On the crew laptop: **Ctrl + .** → Reset → **Chest pain on a sea ambulance**. The crew screen opens in *Preparing
  handoff*. Close the panel.
- Speed 1×. Voice on. Volume up on the crew laptop.

## Script

**1 · Problem (20 s).** "A heart attack on an outer island: an hour or more on a sea ambulance before the hospital
that can treat it. The team waiting at the other end learns almost nothing until the doors open. The crew have both
hands on the patient. Nobody's typing."

**2 · Crew screen (70 s).**
- "This is the tablet on the wall of the boat. The camera is a medical instrument now." Point at the guide: face and
  upper chest. The capsule goes *Presage · acquiring*, then heart rate and breathing appear as **Presage · live**, and
  the breathing waveform moves. "No sensors on the patient. That's Presage."
- Tap the mic and say: *"Gave aspirin 300 milligrams and GTN spray, oxygen four litres, pain eight out of ten."* Tap
  again. The words turn into chips: **Aspirin 300 mg · GTN spray · Oxygen 4 litres · Pain 8 out of 10**. "ElevenLabs
  Scribe hears it. Gemini structures it."
- **Send handoff.** The review sheet shows urgency, key vitals with where each number came from, and the SBAR.
  **Send to IGMH**. The status chip flies to *Handoff sent*.

**3 · Hospital screen (50 s).**
- The row arrives and highlights. Open it: *Suspected STEMI*, NEWS2, arrival time, and every vital with its source
  and age. "The patient's story arrived before the patient."
- **Ask the crew** → *On blood thinners?* The crew laptop says it out loud. The crew answer by voice. The answer
  appears under the question.
- **Accept transfer** → prepare *Cath lab* → message *"Come straight to the cath lab."*

**4 · Back to the crew (20 s).** The dock turns to **Accepted · Dr … — "Come straight to the cath lab"**, and it's
spoken in the vehicle. "One loop: scan, speak, hand off, answered."

**5 · Anywhere (20 s).** Ctrl + . → region **Western Isles** → **Suspected stroke, island to Glasgow**. "Same app.
A region is a JSON file of hospitals, clinics and transport. Next: hospital inboxes, auth, SMS fallback."

## Backup moves

- **No Presage key, or the camera fails:** the camera says why it isn't measuring and the vitals show as **Simulated**.
  Say it plainly: "Those numbers are simulated, and we label them everywhere, including in the hospital's briefing."
- **Mic fails or the room is loud:** the keyboard icon beside the mic types the same note.
- **Wi-Fi fails:** run engine + web on the crew laptop (`README → Run locally`). The hospital screen can be a second
  browser window.

## Judge Q&A

- **Is Presage accurate enough?** We use it inside its validated envelope: a mounted (not handheld) camera, face and
  upper chest visible, patient still, 30 s for breathing to settle. Pulse is validated for 40–110 BPM. Above that the
  crew screen says *confirm with a monitor*. HR + RR give a *partial* NEWS2, and the crew add SpO₂ / BP / temperature
  / ACVPU with a few taps.
- **Privacy?** Video never leaves the vehicle. The bridge runs next to the camera, and only numbers go to the cloud.
- **Can the AI make things up?** The SBAR is built only from recorded vitals and the crew's own words. It says
  *"Drafted by Gemini"* or *"Drafted from template"*, and simulated values carry *(simulated)*. If Gemini is down,
  a deterministic template takes over. The crew's original sentence always sits next to the extracted chips.
- **Safety?** Decision support: a clinician accepts, the crew act. Alerts use NEWS2 bands plus a hedged trend
  forecast, with hysteresis so they don't flap.
- **Why not WhatsApp?** WhatsApp moves messages. It doesn't measure vitals hands-free, structure what was given,
  or put one *Accept* in front of the receiving team.
- **Data and scale?** No real patient data. One small VM and managed Postgres (Tiger Cloud: vitals hypertable and a
  one-minute continuous aggregate for the trend). New regions are data files.
