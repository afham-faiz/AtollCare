"""Run the teammate's crew-app engine on this machine, to test the hand-off (box 4 on the page).

    python run_crew_engine.py             start it (the first run sets it up, which takes about a minute)
    python run_crew_engine.py --refresh   throw the copy away and take a fresh one from origin/main

Their engine lives on the branch origin/main (run `git fetch origin` first if you have not). This script copies
only its `engine/` folder into `.crew-engine/` (git-ignored), builds a separate Python environment there, and
starts it on the port in ENGINE_URL (inputs/.env) with mock adapters and an in-memory store: no keys needed,
nothing is saved, and everything is gone when you stop it with Ctrl+C.
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from src import config

ROOT = Path(__file__).resolve().parent
CREW = ROOT / ".crew-engine"
ENGINE = CREW / "engine"
VENV = CREW / "venv"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def extract_engine() -> None:
    """Copy engine/ out of origin/main (read-only: nothing in your branch or working folder changes)."""
    have = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "origin/main"], cwd=ROOT, capture_output=True)
    if have.returncode != 0:
        sys.exit("The branch origin/main is not here yet. Run `git fetch origin` and try again.")
    tar = subprocess.run(["git", "archive", "origin/main", "engine"], cwd=ROOT, capture_output=True, check=True).stdout
    if ENGINE.exists():
        shutil.rmtree(ENGINE)
    CREW.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
        archive.extractall(CREW, filter="data")
    print(f"Copied their engine from origin/main into {ENGINE}")


def build_environment() -> None:
    dependencies = tomllib.loads((ENGINE / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    print("Building its Python environment and installing its packages (about a minute)...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    subprocess.run([str(venv_python()), "-m", "pip", "install", "-q", *dependencies], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="take a fresh copy from origin/main")
    args = parser.parse_args()

    if args.refresh and CREW.exists():
        shutil.rmtree(CREW)
    if not (ENGINE / "app" / "main.py").exists():
        extract_engine()
    if not venv_python().exists():
        build_environment()

    url = urlparse(config.ENGINE_URL)
    port = str(url.port or 8010)
    env = {**os.environ, "DATABASE_URL": "", "GEMINI_MODE": "mock", "ELEVENLABS_MODE": "mock", "STORAGE_MODE": "local"}
    print(f"Crew engine starting on {config.ENGINE_URL} (mock adapters, nothing is saved). Ctrl+C to stop.")
    try:
        subprocess.run([str(venv_python()), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port,
                        "--log-level", "warning"], cwd=ENGINE, env=env)
    except KeyboardInterrupt:
        print("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
