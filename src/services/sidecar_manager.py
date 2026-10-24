import os
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SIDECAR_URL = os.environ.get("PRESAGE_SIDECAR_URL", "http://127.0.0.1:3001")


def sidecar_mode() -> str | None:
    """Return the running sidecar's mode ('sdk' or 'mock'), or None if it is down."""
    try:
        return httpx.get(f"{SIDECAR_URL}/health", timeout=2).json().get("mode")
    except (httpx.HTTPError, ValueError):
        return None


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

    env = os.environ.copy()
    if mock:
        env["PRESAGE_MODE"] = "mock"  # real environment wins over --env-file

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
