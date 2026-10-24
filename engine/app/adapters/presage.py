# F-M6.2 Presage SmartSpectra contactless vitals (HR + RR from a face video). Modes: sdk | cloud | mock | manual.
# The browser records a ≤30 s video → engine stores it → this adapter processes it.
# TODO(presage-verify): confirm the real integration path (SDK binary/binding on Linux vs cloud API) with Presage.
from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings

log = logging.getLogger("atollcare.presage")


@dataclass
class PresageResult:
    heart_rate: float | None
    resp_rate: float | None
    confidence: float
    source: str  # "presage" | "mock"


class PresageError(RuntimeError):
    pass


class PresageAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.presage_mode
        if self.mode == "cloud" and not (settings.presage_api_key and settings.presage_api_url):
            log.warning("PRESAGE_MODE=cloud but PRESAGE_API_KEY/URL missing — using mock")
            self.mode = "mock"
        if self.mode == "sdk" and not settings.presage_sdk_path:
            log.warning("PRESAGE_MODE=sdk but PRESAGE_SDK_PATH missing — using mock")
            self.mode = "mock"

    @property
    def status(self) -> str:
        if self.mode in ("sdk", "cloud"):
            return "real"
        return "manual" if self.mode == "manual" else "mock"

    @property
    def scan_enabled(self) -> bool:
        return self.mode != "manual"

    async def process(self, video_path: Path, mock_hint: dict[str, float] | None = None) -> PresageResult:
        if self.mode == "manual":
            raise PresageError("Camera scan disabled (PRESAGE_MODE=manual) — enter vitals manually")
        if self.mode == "sdk":
            return await self._sdk(video_path)
        if self.mode == "cloud":
            return await self._cloud(video_path)
        return await self._mock(mock_hint or {})

    async def _mock(self, hint: dict[str, float]) -> PresageResult:
        await asyncio.sleep(3)
        hr = hint.get("heart_rate", 96.0)
        rr = hint.get("resp_rate", 18.0)
        return PresageResult(
            heart_rate=round(hr + random.uniform(-3, 3)),
            resp_rate=round(rr + random.uniform(-1, 1)),
            confidence=0.9,
            source="mock",
        )

    async def _sdk(self, video_path: Path) -> PresageResult:
        # TODO(presage-verify): SmartSpectra CLI/binding flags. Assumed contract: prints JSON {hr, rr, confidence}.
        proc = await asyncio.create_subprocess_exec(
            self.settings.presage_sdk_path, "--input", str(video_path), "--output", "json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=90)
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise PresageError("Presage SDK timed out") from exc
        if proc.returncode != 0:
            raise PresageError(f"Presage SDK failed: {err.decode()[:200]}")
        data = json.loads(out.decode())
        return PresageResult(
            heart_rate=data.get("hr") or data.get("pulse_rate"),
            resp_rate=data.get("rr") or data.get("breathing_rate"),
            confidence=float(data.get("confidence", 0.8)),
            source="presage",
        )

    async def _cloud(self, video_path: Path) -> PresageResult:
        # TODO(presage-verify): endpoint, auth header and response shape are placeholders until confirmed at the booth.
        async with httpx.AsyncClient(timeout=120) as client:
            with video_path.open("rb") as fh:
                resp = await client.post(
                    self.settings.presage_api_url,
                    headers={"Authorization": f"Bearer {self.settings.presage_api_key}"},
                    files={"video": (video_path.name, fh, "video/webm")},
                )
        if resp.status_code >= 400:
            raise PresageError(f"Presage cloud error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return PresageResult(
            heart_rate=data.get("heart_rate") or data.get("hr"),
            resp_rate=data.get("breathing_rate") or data.get("rr"),
            confidence=float(data.get("confidence", 0.8)),
            source="presage",
        )
