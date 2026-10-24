# F-M8.2 Simulated clock. All engine logic uses clock.now() so the night-time scenario works during a daytime
# pitch. sim_now = real_now + offset + (real_now − anchor_real) × (speed − 1)
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.core import refdata
from app.models import DemoState


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def real_now() -> datetime:
    return datetime.now(UTC)


class Clock:
    def __init__(self) -> None:
        self.state = DemoState(speed_multiplier=get_settings().default_speed_multiplier)

    def load(self, state: DemoState) -> None:
        self.state = state

    def now(self) -> datetime:
        real = real_now()
        anchor = self.state.clock_anchor_real or real
        elapsed = (real - anchor).total_seconds()
        offset = self.state.clock_offset_min * 60
        return real + timedelta(seconds=offset + elapsed * (self.state.speed_multiplier - 1))

    def _rebase(self, sim: datetime) -> None:
        real = real_now()
        self.state.clock_offset_min = (sim - real).total_seconds() / 60
        self.state.clock_anchor_real = real

    def set_speed(self, speed: float) -> None:
        sim = self.now()
        self._rebase(sim)
        self.state.speed_multiplier = speed

    def set_offset(self, offset_min: float) -> None:
        self.state.clock_offset_min = offset_min
        self.state.clock_anchor_real = real_now()

    def set_time_of_day(self, hhmm: str) -> None:
        local_now = self.now().astimezone(tz())
        hh, mm = (int(x) for x in hhmm.split(":"))
        target = datetime.combine(local_now.date(), time(hh, mm), tzinfo=tz())
        self._rebase(target.astimezone(UTC))


clock = Clock()


# ---------------------------------------------------------------- daylight helpers (F-M4.7)
def _hhmm(value: str) -> time:
    hh, mm = (int(x) for x in value.split(":"))
    return time(hh, mm)


def daylight_bounds(day: date) -> tuple[datetime, datetime, datetime]:
    """Return (sunrise, sunset, seaplane_last_landing) for a local date, as aware datetimes."""
    cfg = refdata.transport_config()["daylight"]
    sunrise = datetime.combine(day, _hhmm(cfg["sunrise"]), tzinfo=tz())
    sunset = datetime.combine(day, _hhmm(cfg["sunset"]), tzinfo=tz())
    last = sunset - timedelta(minutes=cfg.get("seaplane_return_buffer_min", 60))
    return sunrise, sunset, last


def is_daylight(at: datetime, night_override: bool | None = None) -> bool:
    if night_override is not None:
        return not night_override
    local = at.astimezone(tz())
    sunrise, sunset, _ = daylight_bounds(local.date())
    return sunrise <= local <= sunset


def fmt_local(at: datetime) -> str:
    return at.astimezone(tz()).strftime("%H:%M")
