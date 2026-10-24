from google import genai

from src import config


def make_client() -> genai.Client:
    """Gemini client for the platform the API key belongs to (GEMINI_USE_ENTERPRISE in inputs/.env)."""
    if config.GEMINI_USE_ENTERPRISE:
        # Google Cloud / Agent Platform (Vertex AI express mode) keys.
        return genai.Client(enterprise=True, api_key=config.GEMINI_API_KEY)
    # Google AI Studio keys.
    return genai.Client(api_key=config.GEMINI_API_KEY)
