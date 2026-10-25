import os
import subprocess
import time
from pathlib import Path

import httpx

from src import config  # noqa: F401  (loads inputs/.env into the environment before the sidecar starts)

ROOT = Path(__file__).resolve().parents[2]
SIDECAR_URL = os.environ.get("PRESAGE_SIDECAR_URL", "http://127.0.0.1:3001")


def sidecar_mode() -> str | None:
    """Return the running sidecar's mode ('sdk' or 'mock'), or None if it is down."""
    try:
        return httpx.get(f"{SIDECAR_URL}/health", timeout=2).json().get("mode")
    except (httpx.HTTPError, ValueError):
        return None


def sidecar_env(mock: bool = False) -> dict:
    """Environment for the Node sidecar. The sidecar needs ffmpeg to convert phone video for the SDK."""
    env = os.environ.copy()
    if mock:
        env["PRESAGE_MODE"] = "mock"  # a real environment variable wins over --env-file
    if not env.get("FFMPEG_PATH"):
        try:
            import imageio_ffmpeg

            env["FFMPEG_PATH"] = imageio_ffmpeg.get_ffmpeg_exe()  # bundled with `pip install -r requirements.txt`
        except ImportError:
            pass  # falls back to an `ffmpeg` on PATH
    return env


def ensure_sidecar(mock: bool = False, wait_s: float = 15.0) -> subprocess.Popen | None:
    """Start the Node sidecar if it is not already up. Returns the process if we started it."""
    if sidecar_mode():
        return None

    venv_node = ROOT / ".venv" / "Scripts" / "node.exe"
    cmd = [str(venv_node) if venv_node.exists() else "node"]
    env_file = ROOT / "inputs" / ".env"
    if env_file.exists():
        cmd.append(f"--env-file={env_file}")
    cmd.append(str(ROOT / "presage-sidecar" / "server.js"))

    env = sidecar_env(mock)

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log = open(log_dir / "sidecar.log", "ab")
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=log)

    deadline = time.time() + wait_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Presage sidecar exited at startup; see {log_dir / 'sidecar.log'}")
        if sidecar_mode():
            return proc
        time.sleep(0.3)
    proc.terminate()
    raise RuntimeError("Presage sidecar did not become ready in time")
