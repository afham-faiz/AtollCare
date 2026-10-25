import pytest

from src import config
from src.services import gemini_client, transcription


@pytest.mark.parametrize("raw, expected", [
    ("true", True), ("TRUE", True), ("yes", True), ("on", True), ("1", True),
    ("false", False), ("False", False), ("no", False), ("off", False), ("0", False),
])
def test_toggle_accepts_the_usual_spellings(monkeypatch, raw, expected):
    monkeypatch.setenv("GEMINI_USE_ENTERPRISE", raw)
    assert config._required_bool("GEMINI_USE_ENTERPRISE") is expected


def test_toggle_rejects_anything_else(monkeypatch):
    monkeypatch.setenv("GEMINI_USE_ENTERPRISE", "enterprise")
    with pytest.raises(config.ConfigError, match="must be true or false"):
        config._required_bool("GEMINI_USE_ENTERPRISE")


def test_toggle_is_required_and_the_error_names_the_line(monkeypatch):
    monkeypatch.delenv("GEMINI_USE_ENTERPRISE", raising=False)
    with pytest.raises(config.ConfigError, match="GEMINI_USE_ENTERPRISE"):
        config._required_bool("GEMINI_USE_ENTERPRISE")


@pytest.mark.parametrize("enterprise, expected_kwargs", [
    (True, {"enterprise": True, "api_key": "KEY"}),    # Google Cloud / Agent Platform key
    (False, {"api_key": "KEY"}),                        # Google AI Studio key
])
def test_each_setting_builds_the_matching_client(monkeypatch, enterprise, expected_kwargs):
    seen = {}
    monkeypatch.setattr(gemini_client.genai, "Client", lambda **kw: seen.update(kw) or object())
    monkeypatch.setattr(config, "GEMINI_API_KEY", "KEY")
    monkeypatch.setattr(config, "GEMINI_USE_ENTERPRISE", enterprise)
    gemini_client.make_client()
    seen.pop("http_options")                            # checked in its own test below
    assert seen == expected_kwargs


def test_requests_time_out_and_retry_as_set_in_the_env_file(monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini_client.genai, "Client", lambda **kw: seen.update(kw) or object())
    monkeypatch.setattr(config, "GEMINI_API_KEY", "KEY")
    monkeypatch.setattr(config, "GEMINI_TIMEOUT_S", 42.5)
    monkeypatch.setattr(config, "GEMINI_RETRY_ATTEMPTS", 3)
    gemini_client.make_client()
    assert seen["http_options"].timeout == 42500           # the SDK counts milliseconds
    assert seen["http_options"].retry_options.attempts == 3


@pytest.mark.parametrize("name", ["GEMINI_TIMEOUT_S", "GEMINI_RETRY_ATTEMPTS"])
def test_the_timeout_settings_are_required(monkeypatch, name):
    monkeypatch.delenv(name, raising=False)
    with pytest.raises(config.ConfigError, match=name):
        config._required_float(name)


def test_the_page_info_shows_which_kind_of_key_is_in_use(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "KEY")
    monkeypatch.setattr(config, "GEMINI_USE_ENTERPRISE", False)
    assert transcription.transcription_info()["platform"] == "developer"
    monkeypatch.setattr(config, "GEMINI_USE_ENTERPRISE", True)
    assert transcription.transcription_info()["platform"] == "enterprise"


def test_mock_mode_does_not_need_the_toggle(monkeypatch):
    # No key -> mock voice; a missing GEMINI_USE_ENTERPRISE must not break the page.
    monkeypatch.delattr(config, "GEMINI_USE_ENTERPRISE")
    monkeypatch.delenv("GEMINI_USE_ENTERPRISE", raising=False)
    info = transcription.transcription_info()
    assert info["mode"] == "mock" and info["platform"] is None
