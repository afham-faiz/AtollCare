# F-M6.1 / F-M6.2 / F-M6.4 Camera scan jobs: store video → Presage adapter in background → VitalsReading.
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from app.core import refdata
from app.models import ManualVitalsRequest, ScanJobStatus, VitalsSource
from app.services.context import AppError, Services

log = logging.getLogger("atollcare.scans")
MAX_VIDEO_BYTES = 60 * 1024 * 1024
LOW_CONFIDENCE = 0.6


class ScanService:
    def __init__(self, svc: Services, cases) -> None:  # cases: CaseService (avoid import cycle)
        self.svc = svc
        self.cases = cases
        self.tasks: set[asyncio.Task] = set()

    async def start(self, case_id: UUID, data: bytes, content_type: str) -> str:
        if not self.svc.presage.scan_enabled:
            raise AppError("scan_disabled", "Camera scan disabled (manual mode) — enter vitals manually", 409)
        if not data:
            raise AppError("empty_video", "No video received", 422)
        if len(data) > MAX_VIDEO_BYTES:
            raise AppError("video_too_large", "Video exceeds 60 MB — keep scans to 30 s", 413)
        case = await self.cases.get(case_id)
        job_id = uuid4().hex
        ext = "mp4" if "mp4" in content_type else "webm"
        key = f"scans/{case.id}/{job_id}.{ext}"
        media_url = await self.svc.storage.put(key, data, content_type or "video/webm")
        self.svc.scan_jobs[job_id] = {"status": "queued", "case_id": case.id, "reading": None, "error": None}
        hint = None
        scenario = refdata.scenarios().get(case.meta.scenario_id or "")
        if scenario:
            hint = scenario.get("presage_mock")
        elif case.vitals:
            last = case.vitals[-1]
            hint = {k: v for k, v in {"heart_rate": last.heart_rate, "resp_rate": last.resp_rate}.items() if v}
        task = asyncio.create_task(self._run(job_id, case.id, data, ext, media_url, hint))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job_id

    async def _run(self, job_id: str, case_id: UUID, data: bytes, ext: str, media_url: str, hint) -> None:
        job = self.svc.scan_jobs[job_id]
        job["status"] = "processing"
        tmp = Path(tempfile.gettempdir()) / f"atollcare_scan_{job_id}.{ext}"
        try:
            tmp.write_bytes(data)
            result = await self.svc.presage.process(tmp, hint)
            source = VitalsSource.presage if result.source == "presage" else VitalsSource.mock
            req = ManualVitalsRequest(
                source=source, heart_rate=result.heart_rate, resp_rate=result.resp_rate,
                confidence=result.confidence, media_url=media_url,
            )
            case = await self.cases.add_vitals(case_id, req, actor="reporter")
            job["reading"] = case.vitals[-1] if case.vitals else None
            job["status"] = "done"
        except Exception as exc:  # noqa: BLE001
            log.warning("scan %s failed: %s", job_id, exc)
            job["status"] = "failed"
            job["error"] = str(exc)
        finally:
            tmp.unlink(missing_ok=True)

    def status(self, job_id: str) -> ScanJobStatus:
        job = self.svc.scan_jobs.get(job_id)
        if job is None:
            raise AppError("not_found", "Unknown scan job", 404)
        return ScanJobStatus(status=job["status"], reading=job["reading"], error=job["error"], case_id=job["case_id"])
