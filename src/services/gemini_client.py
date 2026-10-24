from google import genai

from src import config


def make_client() -> genai.Client:
    """Gemini client for the platform the API key belongs to (see GEMINI_PLATFORM in inputs/.env)."""
    if config.gemini_platform() == "enterprise":
        # Google Cloud / Vertex AI "express mode" keys.
        return genai.Client(enterprise=True, api_key=config.GEMINI_API_KEY)
    return genai.Client(api_key=config.GEMINI_API_KEY)
