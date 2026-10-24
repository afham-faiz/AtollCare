# FastAPI app: routers, CORS, global error handling, startup (migrations, demo state, simulator loop).
from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import ENGINE_VERSION, get_settings
from app.core import infra
from app.logging_setup import case_id_var, setup_logging
from app.routers import system, transfers
from app.services.context import AppError
from app.services.hub import build_hub

log = logging.getLogger("atollcare")
CASE_ID_RE = re.compile(r"/transfers/([0-9a-f-]{36})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    hub = build_hub(settings)
    for attempt in range(30):  # wait for the database container
        try:
            await hub.svc.repo.init()
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 29:
                raise
            log.warning("database not ready (%s) — retrying", exc)
            await asyncio.sleep(2)
    await hub.demo.load_state()
    try:
        hub.svc.infra = await infra.detect(settings, hub.svc.repo)
    except Exception as exc:  # noqa: BLE001 — cosmetic; never block startup
        log.warning("infra detection failed: %s", exc)
    log.info("engine started: db=%s (%s) host=%s adapters=%s", hub.svc.repo.kind, hub.svc.infra.database,
             hub.svc.infra.host, hub.svc.adapter_status().model_dump())
    if not settings.disable_background_tasks:
        hub.loop.start()
    yield
    await hub.loop.stop()
    await hub.svc.repo.close()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="AtollCare Engine", version=ENGINE_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["*"], allow_headers=["*"],
        allow_credentials=False,
    )

    @app.middleware("http")
    async def bind_case_id(request: Request, call_next):
        m = CASE_ID_RE.search(request.url.path)
        token = case_id_var.set(m.group(1) if m else None)
        try:
            return await call_next(request)
        finally:
            case_id_var.reset(token)

    def err(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return err(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return err(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return err(422, "validation_error", f"{where}: {first.get('msg', 'invalid input')}")

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return err(500, "internal_error", f"{type(exc).__name__}: {exc}")

    for r in (system, transfers):
        app.include_router(r.router)
    return app


app = create_app()
