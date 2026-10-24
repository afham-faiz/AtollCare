# Pitch — 3 minutes

**Setup before going on stage:** `/demo` → Reset → tick *Autoplay* → speed 1× → open `/demo?view=split` on the stage
screen, `/report` on a phone (HTTPS URL), `/hospital` and `/transport` in tabs. Have a teammate ready to be scanned.

## Script

**1 · Problem (20 s)** — Map of the Maldives. "Around 190 inhabited islands spread over 90,000 km² of ocean. When a
fisherman on Isdhoo has a heart attack at 9 pm, the delay isn't medicine — it's handoffs. Health centre calls the
atoll hospital, who calls Malé, who calls for approval, who calls a boat. Each waits for the last."

**2 · Island (60 s)** — On the phone: *Raise medical alert* → read out the case code. Hold to speak: "crushing chest
pain for 40 minutes, sweating, pain in the left arm" (ElevenLabs Scribe). Analyse → Gemini structured intake: red flags,
STEMI 85 %. Camera scan the teammate (Presage) → HR/RR land in NEWS2 as a *partial* score. Send to doctor →
recommendation in seconds. Point at the *why*: "Seaplane rejected — night, after sunset 18:15. Sea ambulance to Malé
breaches the 120-minute PCI window. So: speedboat to Gan Regional for fibrinolysis in 51 minutes, then fixed-wing
Kadhdhoo → Hulhulé → IGMH."

> Night scenario during a daytime pitch: load **Night-time heart attack, Laamu** in `/demo` (sets the sim clock to
> 21:00) and use its case on the phone, or press *Night 21:00*.

**3 · Hospital (40 s)** — Stage screen: inbox row pulses red. Open it: SBAR written for the specialist, vitals trend
from Tiger Data's continuous aggregate with a hedged forecast, every route the engine considered and why it rejected
it. One click: **Accept**.

**4 · Transport (30 s)** — Dispatch board → Dispatch → set speed 60× → the boat moves on the map; the timeline shows
"Departed Isdhoo", "Reached Gan Regional — interim care". *Speak update* plays "The patient is on the way to IGMH,
expected arrival in…".

**5 · Headline (20 s)** — "Symptom to definitive care: 3 h 40 min — about 2 h 50 min faster than the phone chain."
Architecture strip: Presage · Gemini · ElevenLabs · Tiger Data · Vultr.

**6 · Scale (10 s)** — "Any archipelago: Pacific, Indonesia, Philippines, Scottish isles, the Arctic. Next: real
referral data, Dhivehi voice, SMS/WhatsApp intake, national health-system integration."

### Backup moves

- Capacity flip: load **Stroke with a capacity change, Baa** → `/hospital` → Capacity → IGMH CT off → route flips to
  Kulhudhuffushi within 2 s with a toast.
- Constraint reasoning: **Postpartum haemorrhage in bad weather** → sea state 6 → "No feasible transport" with each
  blocking reason → toggle Helicopter on → helicopter route appears.
- Treat locally first: **Sepsis treated locally first** → antibiotics start at Dhiffushi *now*, transfer follows.
- If the camera fails: *Enter manually* (the UI falls back automatically on permission denial).

## Judge Q&A prep

- **Safety?** Decision support, not decision making — every step needs a human to act (refer, accept, dispatch).
  First-aid text comes only from a vetted static library; the LLM can only select and order step IDs. Every AI output
  is badged; every clinical number is labelled DEMO ASSUMPTION. Presage's own clearance says vitals are not intended to
  independently direct therapy — we mirror that.
- **What if Gemini is down or wrong?** Every AI step has a deterministic fallback (rule-based intake, template SBAR
  and explanation) and the timeline records the fallback. The routing decision itself is deterministic, auditable,
  and unit-tested (NEWS2 boundaries, night / sea-state constraints, scenario outcomes).
- **Data?** No real patient data. Scan videos auto-expire (bucket lifecycle). No PII in URLs — case IDs are UUIDs,
  short codes are random. Timeline is an audit log.
- **Why not just WhatsApp?** WhatsApp moves messages; it doesn't know that the seaplane can't fly after 18:15, that
  the cath lab is down, or that fibrinolysis at Gan beats a 7-hour boat ride. And it still runs the handoffs in
  sequence. We'd *add* WhatsApp/SMS as an intake channel.
- **Scale / cost?** One small VM + managed Postgres. Facilities, transport modes, windows and baseline durations are
  data files — a new country is a new `facilities.json`.
- **Where do the numbers come from?** Illustrative: `engine/app/data/*.yaml`. The headline uses an illustrative
  sequential chain (20 + 40 + 60 + 45 min, not measured data) vs the measured acceptance time in our flow — both shown
  in the Assumptions popover.
