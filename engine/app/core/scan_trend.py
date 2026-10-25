# Serial Presage scans. Presage is cleared for spot checks, so the honest way to see a trend with it is two spot checks
# some minutes apart: a clear rise between two stable crew scans is a reason to take a full manual set now.
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.models import Scan, ScanStatus

MIN_GAP = timedelta(minutes=2)  # back-to-back scans of a calm patient differ by Presage's own ±3 bpm, not by 20
HR_RISE = 20
RR_RISE = 5
RR_HIGH = 25  # NEWS2 scores 25+/min as 3 on its own


@dataclass
class ScanTrend:
    minutes: int
    hr: tuple[int, int] | None  # (first, latest), only when Presage called both stable
    rr: tuple[int, int] | None
    worrying: bool
    text: str


def _usable(s: Scan) -> bool:
    # Presage's numbers are final once they're on the scan, even while Gemini is still checking the video
    v = s.vitals
    return (s.status != ScanStatus.failed and v is not None and v.source == "presage"
            and (v.heart_rate_bpm is not None or v.respiration_rate_bpm is not None))


def _stable_hr(s: Scan) -> int | None:
    v = s.vitals
    ok = v.heart_rate_stable if v.heart_rate_stable is not None else (v.heart_rate_quality or 0) >= 0.6
    return v.heart_rate_bpm if ok else None


def _stable_rr(s: Scan) -> int | None:
    v = s.vitals
    ok = v.respiration_stable if v.respiration_stable is not None else (v.respiration_quality or 0) >= 0.6
    return v.respiration_rate_bpm if ok else None


def scan_trend(scans: list[Scan]) -> ScanTrend | None:
    """The change from the first to the latest stable crew scan, if they're far enough apart to mean something."""
    good = [s for s in scans if _usable(s)]
    if len(good) < 2:
        return None
    first, last = good[0], good[-1]
    if last.at - first.at < MIN_GAP:
        return None
    minutes = round((last.at - first.at).total_seconds() / 60)
    hr = (_stable_hr(first), _stable_hr(last))
    rr = (_stable_rr(first), _stable_rr(last))
    hr_pair = hr if None not in hr else None
    rr_pair = rr if None not in rr else None
    worrying = bool(
        (hr_pair and hr_pair[1] - hr_pair[0] >= HR_RISE)
        or (rr_pair and rr_pair[1] - rr_pair[0] >= RR_RISE)
        or (rr[1] is not None and rr[1] >= RR_HIGH)
    )
    parts = []
    if hr_pair:
        parts.append(f"HR {hr_pair[0]}→{hr_pair[1]}")
    if rr_pair:
        parts.append(f"RR {rr_pair[0]}→{rr_pair[1]}")
    if not parts:
        return None
    text = f"Camera trend {', '.join(parts)} over {minutes} min" + (" — take a full manual set" if worrying else "")
    return ScanTrend(minutes=minutes, hr=hr_pair, rr=rr_pair, worrying=worrying, text=text)
