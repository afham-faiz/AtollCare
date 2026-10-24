# F-M7.1 / F-M7.5 Settings — every env var the engine reads lives here.
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENGINE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
ENGINE_VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # Core. Empty / "memory://" → in-process store (tests, no-docker dev). Postgres URL → TimescaleDB / Tiger Cloud.
    database_url: str = ""
    public_host: str = "localhost"
    cors_origins: str = "http://localhost:3000"

    # Adapters
    gemini_mode: str = "mock"  # real | mock
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    gemini_timeout_s: float = 12.0

    elevenlabs_mode: str = "mock"  # real | mock
    elevenlabs_api_key: str = ""
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    elevenlabs_stt_model: str = "scribe_v1"
    elevenlabs_voice_guide: str = ""
    elevenlabs_voice_status: str = ""

    presage_mode: str = "mock"  # sdk | cloud | mock | manual
    presage_api_key: str = ""
    presage_api_url: str = ""
    presage_sdk_path: str = ""

    storage_mode: str = "local"  # local | s3
    storage_local_dir: str = str(ENGINE_DIR / "var" / "storage")
    s3_endpoint: str = ""
    s3_bucket: str = "atollcare"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"

    # Demo
    default_speed_multiplier: float = 1.0
    timezone: str = "Indian/Maldives"
    sim_tick_s: float = 2.0
    disable_background_tasks: bool = False

    @property
    def use_memory_db(self) -> bool:
        return not self.database_url or self.database_url.startswith("memory")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
