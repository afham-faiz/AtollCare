import os

# Tests run fully in mock mode against the in-memory repository, no background simulator loop.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
os.environ["DISABLE_BACKGROUND_TASKS"] = "true"
for key in ("GEMINI_MODE", "ELEVENLABS_MODE"):
    os.environ[key] = "mock"
os.environ["STORAGE_MODE"] = "local"
# no instance metadata lookup in tests (an empty URL disables it)
os.environ["METADATA_URL"] = ""
os.environ.pop("HOST_LABEL", None)
