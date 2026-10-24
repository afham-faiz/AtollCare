# F-M7.4 Object storage — s3 (Vultr Object Storage, S3-compatible, presigned GET) | local (./var/storage served by
# /api/media/{key}). Scan videos are lifecycle-expired after 24 h (bucket rule, see README).
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from app.config import Settings

log = logging.getLogger("atollcare.storage")
SAFE_KEY = re.compile(r"^[A-Za-z0-9._/-]+$")


class StorageAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.storage_mode
        self.local_dir = Path(settings.storage_local_dir)
        self._client = None
        if self.mode == "s3" and not (settings.s3_endpoint and settings.s3_access_key and settings.s3_secret_key):
            log.warning("STORAGE_MODE=s3 but S3 credentials missing — falling back to local storage")
            self.mode = "local"
        if self.mode == "local":
            self.local_dir.mkdir(parents=True, exist_ok=True)

    @property
    def status(self) -> str:
        return "real" if self.mode == "s3" else "mock"

    def _s3(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=self.settings.s3_endpoint,
                aws_access_key_id=self.settings.s3_access_key,
                aws_secret_access_key=self.settings.s3_secret_key,
                region_name=self.settings.s3_region,
            )
        return self._client

    def local_path(self, key: str) -> Path:
        if not SAFE_KEY.match(key) or ".." in key:
            raise ValueError("invalid storage key")
        return self.local_dir / key

    async def exists(self, key: str) -> bool:
        if self.mode == "local":
            return self.local_path(key).exists()
        try:
            await asyncio.to_thread(self._s3().head_object, Bucket=self.settings.s3_bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        if self.mode == "local":
            path = self.local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_bytes, data)
            return self.url(key)
        await asyncio.to_thread(
            self._s3().put_object, Bucket=self.settings.s3_bucket, Key=key, Body=data, ContentType=content_type
        )
        return self.url(key)

    def url(self, key: str) -> str:
        if self.mode == "local":
            return f"/api/media/{key}"
        return self._s3().generate_presigned_url(
            "get_object", Params={"Bucket": self.settings.s3_bucket, "Key": key}, ExpiresIn=24 * 3600
        )
