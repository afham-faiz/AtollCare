# Simulated clock for demos: sim_now = real_now + offset + (real_now − anchor_real) × (speed − 1).
# All engine logic uses clock.now() so a 75-minute boat transfer can play out in a few minutes on stage.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import DemoState


def real_now() -> datetime:
    return datetime.now(UTC)


class Clock:
    def __init__(self) -> None:
        self.state = DemoState()

    def load(self, state: DemoState) -> None:
        self.state = state

    def now(self) -> datetime:
        real = real_now()
        anchor = self.state.clock_anchor_real or real
        elapsed = (real - anchor).total_seconds()
        offset = self.state.clock_offset_min * 60
        return real + timedelta(seconds=offset + elapsed * (self.state.speed_multiplier - 1))

    def set_speed(self, speed: float) -> None:
        """Change speed without a jump: re-anchor so sim time is continuous."""
        sim = self.now()
        real = real_now()
        self.state.clock_offset_min = (sim - real).total_seconds() / 60
        self.state.clock_anchor_real = real
        self.state.speed_multiplier = speed

    def reset(self) -> None:
        self.state.clock_offset_min = 0
        self.state.clock_anchor_real = None
        self.state.speed_multiplier = 1


clock = Clock()


def fmt_local(at: datetime, tz: str) -> str:
    return at.astimezone(ZoneInfo(tz)).strftime("%H:%M")
