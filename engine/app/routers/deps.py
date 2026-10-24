# Shared router dependencies.
from app.services.hub import Hub, get_hub


def hub() -> Hub:
    return get_hub()
