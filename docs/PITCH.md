# Pitch: 3 minutes, Presage first

The Presage judges prefer mobile. Every beat below is a phone measuring a real person with Presage, and the hospital
acting on it. Other sponsors stay in the write-up, not on stage.

## Before going on stage

**Hour 0, days before: prove it works.** Record 10+ scans of the team (different skin tones, iOS Safari and Android
Chrome), each with a fingertip oximeter on and breathing counted by hand for 60 s. Keep one table for the slide:

| Scans | Mean difference vs oximeter (HR) | Worst miss | Mean difference vs hand count (RR) | "No face found" | Skin tones |
|---|---|---|---|---|---|
| … | … bpm | … bpm | … /min | … of … | … |

The product builds this as you go: enter the oximeter pulse in the crew's vitals sheet and the hospital's Presage
tile shows *"camera 98, oximeter 96 · agree"*. Without that table, don't claim accuracy.

**Rehearse with a recorded face.** `node presage-bridge/scripts/replay.mjs face.mp4 --ffmpeg <path>` streams a video
through the live path exactly as a phone would and prints Presage's summary. Use it to check the bridge before every
rehearsal.

**The room.**
- Laptop runs engine, Presage bridge and a **production** web build (`bun run build && bun run start`: faster on a
  phone than the dev server).
- `./scripts/phone_tunnel.sh` on our own 4G hotspot, not venue Wi-Fi. Open the printed `https://…` address on the
  laptop, press **Ctrl + .**, pick *Dhangethi Health Centre* under **On a phone**, and scan the QR with both phones.
- Projector split: left, the companion's phone mirrored (scrcpy for Android, QuickTime for iPhone); right, `/hospital`.
- A teammate plays the patient: seated, still, face and upper chest lit from the front.
- Presenter panel → *Clear live transfers*. Speed 1×. Crew phone volume up.
- A packet recorded from a real face at rehearsal, already sent, as the fallback. A 30 s screen recording of a good run.
- Never show *Simulated* during the Presage pitch.

## Script

**0:00–0:12 · Hook.** Hold up the phone. "11 pm on an island. His father collapsed. The cardiologist is 90 minutes away
by boat. This phone is the only medical device on the island."

**0:12–0:50 · The companion's phone.**
- Scan the health centre's QR: the page opens already pointed at Dhangethi. Tick consent, *Start*.
- *Turn on camera*, point at the patient. Presage answers before recording starts: *"Presage is watching"*, and any
  framing hint (*"Centre the face in the frame"*).
- Tap record and narrate as the companion: *"He collapsed forty minutes ago, chest pain going into his left arm, he
  has diabetes."* The patient stays still and quiet.
- About 0:30: **HR 92 · Presage · live**, pulse waveform moving. By 0:45 the breathing rate and chest wave. "No sensor
  touches him. That's Presage, from a phone camera." It finishes by itself once Presage calls both stable. *Send*.

**0:50–1:10 · Hospital.** The row arrives. The Presage tile: **92 bpm · 18 /min**, the heart rate across the scan,
*"Known 1 h 19 min before arrival"*, and the companion's own words, transcribed from the same video. "The story arrived
before the patient. Nobody will ask him again." (The companion's reading is labelled a bystander estimate: shown, not
scored.)

**1:10–1:35 · Crew.** On the crew phone: *Sent ahead from a phone* → **Start transfer → IGMH by sea ambulance**. One
tap. Mic: *"Aspirin 300, GTN spray, pain eight out of ten."* Chips appear. *Measure again*: a crew scan on the
propped-up phone, scored this time.

**1:35–1:55 · Accept.** Hospital: *Chest pain, possible ACS (no ECG yet)*. *Accept* → resus bay, *"Come straight in."*
The crew phone says it out loud.

**1:55–2:40 · Proof.** "Don't take our word for it."
- The patient does 30 seconds of jumping jacks; the crew scans again. While Presage acquires: every number shows where
  it came from, simulated values never count, the video isn't kept, a camera reading alone never raises a critical
  alert.
- The hospital tile turns amber: **"Camera trend HR 92→124, RR 18→25 over 3 min — take a full manual set"**, spoken in
  the vehicle. The accept dialog now suggests the resus bay. "Presage didn't just display a number. It changed what the
  hospital prepares."
- If there's time: point the phone at a judge.

**2:40–3:00 · Close.** The accuracy slide for five seconds. "Captured once, on the phone they already have. Presage
turns a camera into the first monitor in the chain."

## If something fails

- **No live number:** show Presage's own hint ("it refuses to guess"), then open the packet recorded from a real face
  at rehearsal and say when it was recorded.
- **The phone can't reach Presage live** (tunnel, hotspot): the recorder says so and keeps recording; Presage measures
  the uploaded clip instead (about the clip's length plus the upload). Keep talking through the hospital screen.
- **Mirroring dies:** hold the phone up to the laptop camera, or play the 30 s recording.
- **Gemini's quota runs out:** the sign check says so ("Gemini's usage limit was reached"); Presage is unaffected.
- **Table judging:** the 60-second version is the judge as the patient.

## Hard questions

- **"Ill patients, a moving boat, a relative filming. That's outside your clearance."** "You're right. K254169 covers
  spot checks of pulse (50–150) and breathing (8–26) over 30 seconds, healthy adults 18–70, a phone in a static mount,
  trained staff. Our crew mode copies that setup: a propped-up phone, trained crew, one scan at a time. The companion's
  video is labelled a bystander estimate and never scored. A camera reading alone only prompts a manual check; it can
  never raise a critical alert, and the accepting clinician decides."
- **"How accurate was it here, today?"** The table above: scans, mean difference against the oximeter, worst miss,
  failures, skin tones. Then: "Every crew oximeter reading is checked against the camera in the product itself."
- **"A phone call already gives pre-notification. What does a camera add?"** "Most of the measured benefit comes from
  the call, the ECG and the onset time, and we carry all three. Presage adds repeated, hands-free observations over a
  one-to-three-hour journey on boats with no monitor or no free hands, and it changes a visible decision: whether to
  prepare resus and ask for a full manual set."
- **"Where does the video go?"** "To our server while it's measured: Presage reads the vitals from it and Gemini
  checks still frames for visible signs. It isn't stored; only frames that show a sign are kept, for the hospital. The
  next step is Presage's native mobile SDK, so only numbers leave the phone."
- **"Why not Presage's iOS/Android SDK?"** "That's the next step for exactly that reason. For the hackathon the phone
  streams to the SmartSpectra SDK on the clinic's laptop, so any phone with a browser works today, and the clip path is
  the fallback when the signal drops."
- **"Can the AI make things up?"** The handoff is built only from recorded facts and says who drafted it. Chest pain
  alone is "possible ACS"; STEMI only with ST elevation reported. Gemini's visual findings each cite the frames they
  rest on ("seen in 3 of 24 frames"), and "couldn't tell" is never shown as "not there".
