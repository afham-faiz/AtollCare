# Shared router dependencies. No real auth (§3): the web app's role switcher sends X-Role for event attribution.
from fastapi import Header

from app.services.hub import Hub, get_hub

ROLES = {"reporter", "clinician", "specialist", "transport", "demo", "system"}


def hub() -> Hub:
    return get_hub()


def actor_role(x_role: str | None = Header(default=None)) -> str:
    return x_role if x_role in ROLES else "clinician"
