# Pitch: 3 minutes

**Before going on stage**

- Crew laptop on a stand, camera angled at a teammate reclining as the patient (face and upper chest in view, lit from
  the front). The Presage bridge runs on it with a real key. Chrome or Edge, camera and mic allowed.
- Second screen (or laptop) on `/hospital`, showing "No incoming transfers".
- On the crew laptop: **Ctrl + .** → *Clear live transfers* → (once per database) *Seed 60 days of history* →
  **Chest pain on a sea ambulance**. The crew screen opens in *Preparing handoff*; the panel shows the suggested line
  and the vitals to type. Close the panel.
- Speed 1×. Voice on. Volume up on the crew laptop. A third tab on `/insights`.

## Script

**1 · Problem (15 s).** "A heart attack on an outer island: an hour or more on a sea ambulance before the hospital
that can treat it. The team at the other end learns almost nothing until the doors open. The crew have both hands on
the patient. Nobody's typing."

**2 · Crew screen (70 s).**
- "This is the tablet on the wall of the boat. The camera is a medical instrument." Point at the guide: face and upper
  chest. The capsule goes *Presage · acquiring*, then heart rate and breathing appear as **Presage · live**, and the
  breathing waveform moves. "No sensors on the patient. That's Presage."
- **Complete NEWS2** → type SpO₂ 95, BP 104, temp 36.8, alert. "Nothing on this screen is pre-filled: every number is
  measured by the camera or entered by the crew."
- Tap the mic: *"Gave aspirin 300 milligrams and GTN spray, oxygen four litres, pain eight out of ten."* The words turn
  into **Aspirin 300 mg · GTN spray · Oxygen 4 litres** and *Pain 8 out of 10*. "ElevenLabs hears it, Gemini structures
  it — and the crew can strike anything it got wrong."
- **Send handoff** → review → **Send to IGMH**.

**3 · Hospital screen (45 s).**
- The row arrives. Open it: *Suspected STEMI* — "matched from the crew's words", NEWS2, arrival time, and every vital
  with its source and age. "The patient's story arrived before the patient."
- **Ask the crew** → *On blood thinners?* The crew laptop says it out loud; the crew answer by voice.
- **Accept transfer** → *Cath lab* → *"Come straight to the cath lab."*

**4 · Back to the crew (15 s).** The dock turns to **Accepted — "Come straight to the cath lab"**, spoken in the
vehicle. "One loop: scan, speak, hand off, answered."

**5 · The network (20 s).** `/insights`: "Every reading and every handoff lands in Tiger Data. Median time to
acceptance, the slowest hospitals, alerts per day — continuous aggregates answer in a few milliseconds." Press **Run
the benchmark**: aggregate vs raw hypertable, live. "And it's all running on Vultr" — point at the presenter panel's
*Host: Vultr · LHR*.

**6 · Anywhere (15 s).** Ctrl + . → **Western Isles** → **Suspected stroke, island to Glasgow**. "Same app. A region
is a JSON file. Next: hospital inboxes, auth, SMS fallback."

## Backup moves

- **No Presage key, or the camera fails:** the camera says why it isn't measuring and the vitals show as **Simulated**
  — muted, no status word, never scored. Say it plainly: "Those numbers are simulated; we label them everywhere and
  they never raise an alert."
- **Mic fails or the room is loud:** the keyboard icon beside the mic types the same note.
- **Gemini overloaded:** it falls back to a lighter model, then to the template; the handoff says which wrote it.
- **Wi-Fi fails:** run engine + web on the crew laptop (`README → Run locally`); the hospital screen is a second window.

## Judge Q&A

- **Why a camera, when ambulances have monitors?** For the transports that don't: inter-island speedboats, ferries,
  community responders, rural volunteer drivers, low-resource services, overflow in a mass-casualty incident. And
  where there is a monitor, it gives a hands-free trend without attaching leads to a conscious patient.
- **Is Presage accurate enough?** We stay inside its validated envelope: mounted (not handheld) camera, face and upper
  chest visible, patient still, 30 s for breathing to settle, pulse validated 40–110 BPM (above that: *confirm with a
  monitor*). Motion in a moving vehicle degrades it; the screen shows Presage's own movement hints.
- **Privacy?** Video never leaves the device — the bridge runs next to the camera and only numbers go to the cloud.
  Voice audio does go to ElevenLabs for transcription, and note text to Google for Gemini; we say so.
- **Can the AI make things up?** The SBAR is built only from recorded vitals and the crew's words, says *Drafted by
  Gemini* or *Drafted from template*, and marks anything simulated. Extracted items are suggestions the crew can
  strike. Simulated data never moves NEWS2 or raises an alert.
- **Safety?** Decision support: a clinician accepts, the crew act. Alerts use NEWS2 bands plus a hedged trend
  forecast from measured readings, with hysteresis so they don't flap.
- **Why Tiger Data?** Vitals are a time series: hypertables with daily chunks, a real-time 1-minute aggregate behind
  every patient's trend, network aggregates behind operations, columnar compression after a week (83% smaller on 60
  days of history). The relational transfer documents sit in the same database.
- **Data and scale?** No real patient data; the network history is seeded and labelled as such. One small Vultr VM
  plus Tiger Cloud. New regions are data files.
