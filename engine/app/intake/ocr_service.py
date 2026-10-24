"""Read an ID document (driving licence, national ID...) from a photo with a Gemini vision model.

parse_identity_doc() never raises: anything it cannot read comes back as None with a note in
`issues`, and `needs_review` tells the health-centre clerk to check the card by eye.

The model only transcribes what is printed; code does the rest (joining the name, checking the
number's shape, working out the age from the date of birth), so those never depend on the model's maths.
"""
import re
from datetime import date

from pydantic import BaseModel

from app.intake import config
from app.intake.gemini_client import make_client
from app.intake.schemas import Demographics
from app.intake.video_prep import normalise_image

PROMPT = """Read this identity document photo. Transcribe ONLY text that is actually visible. Never infer,
complete or guess a value: if a field is unreadable, covered (by a finger, glare, a watermark or stamp) or
absent, return null for it.

- surname and given_names: exactly as printed. On a UK driving licence these are fields 1 and 2.
- date_of_birth: as an ISO date YYYY-MM-DD (UK licences print it as DD.MM.YYYY, so 01.02.1990 is 1990-02-01).
- id_number: the document's own identification number (licence number, national ID or passport number), exactly as printed.
- document_type: for example "UK driving licence".
- is_specimen: true if the card is marked specimen, sample, prop, void or not real. Still read its fields.
- text_partly_obscured: true if any part of the text you used is hard to read.
- legibility_issues: short notes about anything you were unsure of."""


class IdReading(BaseModel):
    """What the model is asked to return (JSON schema)."""

    document_type: str | None = None
    surname: str | None = None
    given_names: str | None = None
    date_of_birth: str | None = None
    id_number: str | None = None
    is_specimen: bool = False
    text_partly_obscured: bool = False
    legibility_issues: list[str] = []


_ID_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/ ]{3,29}")


def age_on(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def parse_identity_doc(image_bytes: bytes, today: date | None = None) -> Demographics:
    """Photo of an ID in, Demographics out. Never raises."""
    try:
        if not config.GEMINI_API_KEY:
            return Demographics(issues=["No GEMINI_API_KEY in inputs/.env, so the ID could not be read."])
        image, mime = normalise_image(image_bytes)
        reading, model = _read_with_gemini(image, mime)
    except Exception as exc:  # noqa: BLE001 — a bad photo, bad key or network problem must not crash the intake
        return Demographics(issues=[f"read_failed: {exc.__class__.__name__}: {str(exc)[:300]}"])
    return _to_demographics(reading, model, today or date.today())


def _read_with_gemini(image: bytes, mime: str) -> tuple[IdReading, str]:
    from google.genai import types

    model = config.GEMINI_ID_MODEL
    client = make_client()  # keep the reference: the SDK closes its connection when it is collected
    response = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=image, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=IdReading),
    )
    return IdReading.model_validate_json(response.text), model


def _to_demographics(reading: IdReading, model: str, today: date) -> Demographics:
    issues = list(reading.legibility_issues)

    name = " ".join(p.strip() for p in (reading.given_names, reading.surname) if p and p.strip()) or None

    id_number = (reading.id_number or "").strip() or None
    if id_number and not _ID_SHAPE.fullmatch(id_number):
        issues.append(f"ID number {id_number!r} does not look like an ID number, so it was dropped.")
        id_number = None

    dob = age = None
    if reading.date_of_birth:
        try:
            born = date.fromisoformat(reading.date_of_birth.strip())
            if born > today:
                issues.append("Date of birth is in the future, so it was dropped.")
            else:
                dob, age = born.isoformat(), age_on(born, today)
        except ValueError:
            issues.append(f"Date of birth {reading.date_of_birth!r} was not a valid date, so it was dropped.")

    for label, value in (("name", name), ("ID number", id_number), ("date of birth", dob)):
        if value is None:
            issues.append(f"Could not read the {label}.")
    if reading.is_specimen:
        issues.append("The card is marked as a specimen / not a real document.")
    if reading.text_partly_obscured:
        issues.append("Some of the text is hard to read.")

    return Demographics(
        full_name=name,
        id_number=id_number,
        age=age,
        date_of_birth=dob,
        document_type=reading.document_type,
        needs_review=bool(issues),
        issues=issues,
        diagnostics={"model": model, "platform": config.gemini_platform(), "raw_reading": reading.model_dump()},
    )
