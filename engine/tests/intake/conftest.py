import pytest

from app.intake import config


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """Tests use fixed settings: never the real .env or key."""
    values = {
        "GEMINI_API_KEY": "",
        "GEMINI_USE_ENTERPRISE": True,
        "GEMINI_TIMEOUT_S": 150.0,
        "GEMINI_RETRY_ATTEMPTS": 2,
        "GEMINI_STT_MODEL": "gemini-3.8-flash",
        "GEMINI_STT_FALLBACK_MODEL": "",
        "GEMINI_CHAT_MODEL": "gemini-3.8-flash",
        "GEMINI_ID_MODEL": "gemini-3.8-flash",
        "GEMINI_CUE_PLANNER_MODEL": "gemini-3.8-flash",
        "GEMINI_VQA_MODEL": "gemini-3.8-flash",
        "VQA_FRAME_INTERVAL_S": 2.0,
        "VQA_MAX_FRAMES": 24,
        "VQA_MODE": "two_step",
        "VIDEO_RECORD_MAX_S": 60.0,
        "TRANSCRIBE_LANGUAGE": "en-US",
        "STT_SILENCE_STOP_S": 2.0,
        "STT_FLASH_PAUSE_S": 0.8,
        "STT_FLASH_MAX_SEGMENT_S": 8.0,
        "SAVE_RECORDINGS": False,
    }
    for name, value in values.items():
        monkeypatch.setattr(config, name, value, raising=False)
