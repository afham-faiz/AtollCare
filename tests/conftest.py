import pytest

from src import config
from src.services import cue_log, id_log, recordings, transcript_log


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """Tests use fixed settings and temp folders: never the real inputs/.env, key, logs or recordings."""
    values = {
        "GEMINI_API_KEY": "",
        "GEMINI_USE_ENTERPRISE": True,
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
    monkeypatch.setattr(recordings, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr(transcript_log, "LOG_PATH", tmp_path / "transcripts.json")
    monkeypatch.setattr(id_log, "LOG_PATH", tmp_path / "id_scans.json")
    monkeypatch.setattr(cue_log, "LOG_PATH", tmp_path / "visual_cues.json")
