from google import genai
from google.genai import types

from app.intake import config


def make_client(api_key: str | None = None) -> genai.Client:
    """Gemini client for the platform the API key belongs to (GEMINI_USE_ENTERPRISE in .env). The engine's own
    adapter passes its key explicitly; intake services use the intake key (blank unless GEMINI_MODE=real).

    Requests time out after GEMINI_TIMEOUT_S, so a stalled connection becomes an error the page can show
    instead of an endless wait.
    """
    options = types.HttpOptions(
        timeout=int(config.GEMINI_TIMEOUT_S * 1000),  # the SDK counts milliseconds
        retry_options=types.HttpRetryOptions(attempts=config.GEMINI_RETRY_ATTEMPTS),
    )
    key = api_key if api_key is not None else config.GEMINI_API_KEY
    if config.GEMINI_USE_ENTERPRISE:
        # Google Cloud / Agent Platform (Vertex AI express mode) keys.
        return genai.Client(enterprise=True, api_key=key, http_options=options)
    # Google AI Studio keys.
    return genai.Client(api_key=key, http_options=options)
