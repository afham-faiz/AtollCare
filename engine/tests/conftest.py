import os

# Tests run fully in mock mode against the in-memory repository, no background simulator loop.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
os.environ["DISABLE_BACKGROUND_TASKS"] = "true"
for key in ("GEMINI_MODE", "ELEVENLABS_MODE"):
    os.environ[key] = "mock"
os.environ["STORAGE_MODE"] = "local"
# never reach a real Presage bridge from tests (a port nothing listens on)
os.environ["PRESAGE_BRIDGE_URL"] = "http://127.0.0.1:9"
