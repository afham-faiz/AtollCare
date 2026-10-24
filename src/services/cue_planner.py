"""Step 1 of the visual cue session: decide WHICH cues are worth looking for.

The bystander's account (the transcript) is read by a Gemini model that may only choose from the
vetted catalogue in src/data/cue_catalogue.json, so it cannot invent clinical checks. Each choice must
quote the words that prompted it, and the code checks the quote really appears in the account.
A few baseline cues are always included. With no account at all (or if the model cannot be reached) there
is nothing to focus on, so EVERY catalogue sign is checked instead.

plan_cues() never raises.
"""
import json
import re
from pathlib import Path

from pydantic import BaseModel

from src import config
from src.models.schemas import CuePlan, PlannedCue
from src.services.gemini_client import make_client

CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "data" / "cue_catalogue.json"
MAX_PICKS = 8

PROMPT = """A bystander has described a person who has suddenly become unwell. A video of that person will be
checked for visible signs. Choose which signs from the list below are worth looking for, given the account.

Rules:
- The account is unverified and may be wrong or exaggerated. Do not diagnose.
- Choose ONLY ids from the list. Pick at most {max_picks}. Prefer signs that would help confirm OR rule out
  what the account suggests.
- For each pick give a one-sentence reason, and transcript_quote: the exact words copied from the account
  that prompted it, or null if the pick comes from the general picture.
- presentations: the kinds of problem the account suggests, chosen only from: {presentations}.

Signs you can choose from:
{cues}

Patient age: {age}

The bystander's account:
\"\"\"
{transcript}
\"\"\""""


class _Pick(BaseModel):
    cue_id: str
    why: str = ""
    transcript_quote: str | None = None


class _Picks(BaseModel):
    presentations: list[str] = []
    cues: list[_Pick] = []


def load_catalogue() -> dict[str, dict]:
    data = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["cues"]}


def _planned(cue: dict, source: str, why: str = "", quote: str | None = None) -> PlannedCue:
    return PlannedCue(cue_id=cue["id"], label=cue["label"], question=cue["question"], source=source,
                      why=why, transcript_quote=quote)


def _baseline(catalogue: dict[str, dict], skip: set[str] = frozenset()) -> list[PlannedCue]:
    return [_planned(c, "baseline", why="Standard check made for every patient.")
            for c in catalogue.values() if c.get("baseline") and c["id"] not in skip]


def _everything(catalogue: dict[str, dict]) -> list[PlannedCue]:
    """No account to focus on: check every sign in the catalogue as a standard check."""
    return [_planned(c, "baseline", why="Standard check.") for c in catalogue.values()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def plan_cues(transcript: str, age: int | None = None) -> CuePlan:
    """Account in, list of cues to look for out. Never raises."""
    catalogue = load_catalogue()
    transcript = (transcript or "").strip()
    if not transcript:
        return CuePlan(cues=_everything(catalogue), issues=["No account was given, so every standard sign is checked."])
    if not config.GEMINI_API_KEY:
        return CuePlan(cues=_everything(catalogue),
                       issues=["No GEMINI_API_KEY in inputs/.env, so every standard sign is checked."])
    try:
        picks = _ask_planner(transcript, age, catalogue)
    except Exception as exc:
        return CuePlan(cues=_everything(catalogue),
                       issues=[f"planner_failed: {exc.__class__.__name__}: {str(exc)[:300]}",
                               "Could not focus on the account, so every standard sign is checked."])
    return build_plan(picks, transcript, catalogue)


def _ask_planner(transcript: str, age: int | None, catalogue: dict[str, dict]) -> _Picks:
    from google.genai import types

    presentations = sorted({p for c in catalogue.values() for p in c["presentations"] if p != "any"})
    prompt = PROMPT.format(
        max_picks=MAX_PICKS,
        presentations=", ".join(presentations),
        cues="\n".join(f"- {c['id']}: {c['label']} ({c['question']})" for c in catalogue.values()),
        age=age if age is not None else "unknown",
        transcript=transcript,
    )
    client = make_client()  # keep the reference: the SDK closes its connection when it is collected
    response = client.models.generate_content(
        model=config.GEMINI_CUE_PLANNER_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_Picks),
    )
    return _Picks.model_validate_json(response.text)


def build_plan(picks: _Picks, transcript: str, catalogue: dict[str, dict]) -> CuePlan:
    """Turn the model's picks into a plan, keeping only what can be verified."""
    issues: list[str] = []
    seen_text = _norm(transcript)
    chosen: list[PlannedCue] = []
    for pick in picks.cues:
        if pick.cue_id not in catalogue:
            issues.append(f"Ignored {pick.cue_id!r}: not in the cue catalogue.")
            continue
        if any(c.cue_id == pick.cue_id for c in chosen):
            continue
        if len(chosen) >= MAX_PICKS:
            issues.append("Ignored extra picks beyond the limit.")
            break
        quote = (pick.transcript_quote or "").strip() or None
        if quote and _norm(quote) not in seen_text:
            issues.append(f"The quote for {pick.cue_id!r} was not found in the account, so it was removed.")
            quote = None
        chosen.append(_planned(catalogue[pick.cue_id], "transcript", why=pick.why.strip(), quote=quote))

    known = {p for c in catalogue.values() for p in c["presentations"]} - {"any"}
    presentations = [p for p in dict.fromkeys(picks.presentations) if p in known]
    cues = chosen + _baseline(catalogue, skip={c.cue_id for c in chosen})
    return CuePlan(presentations=presentations, cues=cues, issues=issues)
