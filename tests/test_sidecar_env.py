from src.services import sidecar_manager


def test_ffmpeg_path_defaults_to_the_bundled_copy(monkeypatch):
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    env = sidecar_manager.sidecar_env()
    assert env["FFMPEG_PATH"].lower().endswith(("ffmpeg.exe", "ffmpeg")) or "ffmpeg" in env["FFMPEG_PATH"].lower()


def test_an_explicit_ffmpeg_path_is_respected(monkeypatch):
    monkeypatch.setenv("FFMPEG_PATH", "C:/tools/ffmpeg.exe")
    assert sidecar_manager.sidecar_env()["FFMPEG_PATH"] == "C:/tools/ffmpeg.exe"


def test_mock_flag_overrides_the_env_file_mode(monkeypatch):
    monkeypatch.setenv("PRESAGE_MODE", "sdk")
    assert sidecar_manager.sidecar_env(mock=True)["PRESAGE_MODE"] == "mock"
