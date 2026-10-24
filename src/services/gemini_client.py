from google import genai
from google.genai import types

from src import config


def make_client() -> genai.Client:
    """Gemini client for the platform the API key belongs to (GEMINI_USE_ENTERPRISE in inputs/.env).

    Requests time out after GEMINI_TIMEOUT_S, so a stalled connection becomes an error the page can show
    instead of an endless wait.
    """
    options = types.HttpOptions(
        timeout=int(config.GEMINI_TIMEOUT_S * 1000),  # the SDK counts milliseconds
        retry_options=types.HttpRetryOptions(attempts=config.GEMINI_RETRY_ATTEMPTS),
    )
    if config.GEMINI_USE_ENTERPRISE:
        # Google Cloud / Agent Platform (Vertex AI express mode) keys.
        return genai.Client(enterprise=True, api_key=config.GEMINI_API_KEY, http_options=options)
    # Google AI Studio keys.
    return genai.Client(api_key=config.GEMINI_API_KEY, http_options=options)
