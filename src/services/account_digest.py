"""Make the bystander's voice account safe to hand over.

The account is spoken freely, so it can contain a name or an ID number (a health card number, say). One Gemini
request returns two things: a one-line complaint (the crew app's required field) and the full account with
names and ID numbers replaced. Code then masks any long digit run again, as a second safety net.

digest_account() never raises. If Gemini is unavailable the complaint falls back to the start of the account
(with digits masked) and the full account is NOT passed on, because it could not be checked.
"""
import re

from pydantic import BaseModel

from src import config
from src.models.schemas import AccountDigest
from src.services.gemini_client import make_client

COMPLAINT_CHARS = 200
NUMBER_RUN = re.compile(r"\b\d{4,}\b")

PROMPT = """You are preparing a bystander's spoken account of a patient to be handed to an ambulance crew.
Return two fields:
- complaint: ONE line of at most 25 words saying what is wrong: symptoms, timing, what happened. Use only facts
  stated in the account. No advice, no guesses, no names, no ID numbers.
- redacted_account: the whole account, lightly cleaned of spoken filler, with every person's name replaced by
  "[name]" and every ID, card, phone or reference number replaced by "[number]". Keep everything else, including
  ages, times, places and symptoms. Do not add or reword medical facts.

The account:
\"\"\"
{account}
\"\"\""""


class _Digest(BaseModel):
    complaint: str
    redacted_account: str


def mask_numbers(text: str) -> str:
    """Replace any run of four or more digits (ID, card and phone numbers) with [number]."""
    return NUMBER_RUN.sub("[number]", text)


def _one_line(text: str, limit: int = COMPLAINT_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip().strip("\"'")
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut + "…"


def digest_account(raw_account: str) -> AccountDigest:
    """Raw voice account in, send-safe digest out. Never raises."""
    raw = (raw_account or "").strip()
    if not raw:
        return AccountDigest(had_account=False)
    fallback = AccountDigest(had_account=True, complaint=_one_line(mask_numbers(raw)))
    if not config.GEMINI_API_KEY:
        return fallback
    try:
        digest = _ask_gemini(raw)
    except Exception:  # unreachable, refused, malformed: the account simply is not passed on
        return fallback
    complaint = _one_line(mask_numbers(digest.complaint)) or fallback.complaint
    account = mask_numbers(re.sub(r"[ \t]+", " ", digest.redacted_account).strip())
    return AccountDigest(had_account=True, complaint=complaint, account=account, redacted=bool(account))


def _ask_gemini(raw: str) -> _Digest:
    from google.genai import types

    client = make_client()  # keep the reference: the SDK closes its connection when it is collected
    response = client.models.generate_content(
        model=config.GEMINI_SUMMARY_MODEL,
        contents=PROMPT.format(account=raw),
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Digest),
    )
    return _Digest.model_validate_json(response.text)
