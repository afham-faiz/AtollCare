"""Extract the salient items from Part 1's three inputs into one packet for the crew app.

build_packet() is a pure function: the same inputs always give the same packet, and it never calls a model
(the voice account is digested separately, see account_digest.py). It decides three things:

- what is SENT (age, a label, a one-line complaint, Presage readings, short notes),
- what is WITHHELD on purpose (the real name, the ID number, the date of birth, evidence images), and
- what is MISSING, so the crew is never left to assume an absent value was normal.

Rules that matter:
- Only real Presage measurements are sent as vitals. Mock or unavailable readings are never passed on as if measured.
- Each vital carries its own confidence (the crew app excludes readings under 0.6 from NEWS2 itself).
- Nothing is inferred from a sign that was not seen.
"""
import re

from src import config
from src.models.schemas import (
    AccountDigest, Demographics, PacketNote, PacketVital, PreArrivalPacket, RppgEstimates, VisualCueReport,
)

NOTE_LIMIT = 2000  # the crew app rejects longer notes
# Ranges the crew app accepts for these two fields.
HEART_RATE_RANGE = (10, 300)
RESP_RATE_RANGE = (1, 80)

CAMERA_HINTS = {
    "kNoFaceFound": "no face found", "kMultipleFacesFound": "more than one face", "kFaceNotCentered": "face not centred",
    "kFaceSizeOutOfRange": "face too small or too large", "kTooDark": "too dark", "kTooBright": "too bright",
    "kChestNotVisible": "upper chest not in frame", "kCameraTuning": "camera still adjusting",
    "kFrameRateTooLow": "frame rate too low", "kExcessiveMotion": "too much movement", "kFaceTooClose": "face too close",
    "kFaceTooFar": "face too far", "kFaceTooHigh": "face too high in the frame", "kFaceTooLow": "face too low in the frame",
    "kFaceNotForward": "face not turned toward the camera",
}


def initials(full_name: str | None) -> str | None:
    """'DAVID MC-FUNNY' -> 'D. M.'  (first letter of each word)."""
    letters = [next((c for c in word if c.isalpha()), "") for word in (full_name or "").split()]
    letters = [c.upper() for c in letters if c]
    return " ".join(f"{c}." for c in letters) or None


def camera_hint(issues: list[str]) -> str | None:
    known = [CAMERA_HINTS[i] for i in issues if i in CAMERA_HINTS]
    return ("Camera notes: " + ", ".join(known) + ".") if known else None


def _fit(text: str, limit: int = NOTE_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _clamp01(x: float | None) -> float:
    return max(0.0, min(1.0, float(x or 0.0)))


def _seen_labels(signs: VisualCueReport | None) -> list[str]:
    return [f.label for f in signs.findings if f.finding == "present"] if signs else []


def _complaint(digest: AccountDigest | None, signs: VisualCueReport | None) -> str:
    if digest and digest.complaint.strip():
        return digest.complaint.strip()
    seen = _seen_labels(signs)
    return "Pre-arrival check, no account given" + (f". Seen on video: {', '.join(seen)}" if seen else "")


def _vitals(est: RppgEstimates | None, missing: list[str]) -> list[PacketVital]:
    if est is None:
        missing.append("Heart rate and breathing rate were not measured.")
        return []
    if est.source != "presage":
        missing.append(f"Heart rate and breathing rate were not measured by Presage (source: {est.source}), "
                       "so no vitals were sent.")
        return []
    hint = camera_hint(est.issues)
    out: list[PacketVital] = []
    for label, field, value, quality, (low, high) in (
        ("Heart rate", "heart_rate", est.heart_rate_bpm, est.heart_rate_quality, HEART_RATE_RANGE),
        ("Breathing rate", "resp_rate", est.respiration_rate_bpm, est.respiration_quality, RESP_RATE_RANGE),
    ):
        if value is None:
            missing.append(f"{label} was not measured.")
        elif not low <= value <= high:
            missing.append(f"{label} {value} is outside the range the crew app accepts, so it was not sent.")
        else:
            confidence = _clamp01(quality if quality is not None else est.signal_quality_score)
            out.append(PacketVital(**{field: float(value)}, confidence=confidence, hint=hint))
    return out


def _video_note(signs: VisualCueReport) -> PacketNote | None:
    if not signs.findings or not signs.frames:
        return None
    pct = lambda f: f"{f.label} ({round(f.confidence * 100)}%)"  # noqa: E731
    groups = {k: [pct(f) for f in signs.findings if f.finding == k] for k in ("present", "absent", "cannot_assess")}
    lines = [f"Video check before arrival (AI, {len(signs.frames)} still frames; decision support, not a diagnosis)."]
    if groups["present"]:
        lines.append("Seen: " + ", ".join(groups["present"]) + ".")
    if groups["absent"]:
        lines.append("Not seen: " + ", ".join(groups["absent"]) + ".")
    if groups["cannot_assess"]:
        lines.append("Could not assess: " + ", ".join(groups["cannot_assess"]) + ".")
    if signs.reported_but_not_seen:
        lines.append("Mentioned in the account but not seen on video: " + ", ".join(signs.reported_but_not_seen) + ".")
    lines.append("Still frames cannot show movement or rhythm, and a sign not seen may simply not have been in view.")
    return PacketNote(title="Video check", text=_fit(" ".join(lines)))


def _id_note(d: Demographics) -> PacketNote | None:
    if d.full_name is None and d.id_number is None and d.age is None:
        return None  # nothing was read
    parts = [f"ID check at the health centre: {d.document_type or 'ID document'}"]
    if d.age is not None:
        parts.append(f"age {d.age}")
    text = ", ".join(parts) + "."
    if any("specimen" in i.lower() for i in d.issues):
        text += " The card is marked as a specimen, not a real document."
    if d.needs_review:
        text += " The card needs a check by eye."
    return PacketNote(title="ID check", text=_fit(text))


def build_packet(
    *,
    demographics: Demographics | None,
    vitals: RppgEstimates | None,
    signs: VisualCueReport | None,
    digest: AccountDigest | None,
    label_mode: str | None = None,
    send_consciousness: bool | None = None,
    min_confidence: float | None = None,
) -> PreArrivalPacket:
    """Aggregate Part 1's outputs. The three optional arguments default to the settings in inputs/.env."""
    label_mode = label_mode if label_mode is not None else config.HANDSHAKE_PATIENT_LABEL
    send_consciousness = send_consciousness if send_consciousness is not None else config.HANDSHAKE_SEND_CONSCIOUSNESS
    min_confidence = min_confidence if min_confidence is not None else config.HANDSHAKE_CONSCIOUSNESS_MIN_CONFIDENCE

    missing: list[str] = []
    withheld: list[str] = []
    notes: list[PacketNote] = []

    # --- who: only a label and an age ---
    label = initials(demographics.full_name) if (demographics and label_mode == "initials") else None
    age = demographics.age if demographics else None
    if demographics is None or (demographics.full_name is None and demographics.age is None):
        missing.append("No ID was read, so the patient's age is unknown.")
    if demographics:
        if demographics.full_name:
            withheld.append("Full name (only initials are sent)" if label else "Full name")
        if demographics.id_number:
            withheld.append("ID number")
        if demographics.date_of_birth:
            withheld.append("Date of birth (age is sent instead)")
        note = _id_note(demographics)
        if note:
            notes.append(note)

    # --- what happened: the redacted account ---
    if digest is None or not digest.had_account:
        missing.append("No voice account was given.")
    else:
        if digest.account:
            notes.append(PacketNote(title="Voice account", text=_fit(
                "Voice account from the bystander, before arrival (names and ID numbers removed): " + digest.account)))
            withheld.append("Names and ID numbers spoken in the account (removed)")
        else:
            missing.append("Only a one-line summary of the voice account is sent: the full account could not be "
                           "checked for names and ID numbers, so it was held back.")
            withheld.append("Full voice account (could not be checked for names and ID numbers)")

    # --- what the camera and the frames show ---
    vital_readings = _vitals(vitals, missing)
    consciousness = None
    if signs is None or not signs.findings:
        missing.append("Visible signs in the video were not checked.")
    else:
        note = _video_note(signs)
        if note:
            notes.append(note)
        else:
            missing.append("Visible signs in the video could not be checked.")
        if any(f.evidence_frames for f in signs.findings):
            withheld.append("Evidence frame images (not supported by the crew app)")
        responsive = next((f for f in signs.findings if f.cue_id == "responsiveness"), None)
        if send_consciousness and responsive and responsive.finding == "present" and responsive.confidence >= min_confidence:
            consciousness = "A"

    missing.append("Oxygen level, blood pressure and temperature are not measured by Part 1.")
    return PreArrivalPacket(
        patient_label=label, age=age, complaint=_complaint(digest, signs), vitals=vital_readings,
        consciousness=consciousness, notes=notes, withheld=withheld, missing=missing,
    )
