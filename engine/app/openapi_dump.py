# F-M7.6 Write the OpenAPI schema without starting the server: `uv run python -m app.openapi_dump <out.json>`.
import json
import sys
from pathlib import Path

from app.main import app

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
