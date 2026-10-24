"""AtollCare Part 1 entry point.

    python run.py                      analyse the newest video in inputs/
    python run.py inputs/clip.mp4      analyse a specific video
    python run.py --serve              start the demo web page on http://127.0.0.1:8000 and open it
    python run.py --mock               use fake vitals (no Presage key or video needed)

Starts the Presage sidecar automatically if it is not already running.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUTS = ROOT / "inputs"


def newest_video() -> Path | None:
    videos = sorted(INPUTS.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return videos[0] if videos else None


def ensure_access_token() -> str:
    """The shared secret for the phone link. Created once and saved to inputs/.env."""
    import os
    import secrets

    from src import config

    if config.ACCESS_TOKEN:
        return config.ACCESS_TOKEN
    token = secrets.token_urlsafe(24)
    config.ENV_FILE.parent.mkdir(exist_ok=True)
    with config.ENV_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\nACCESS_TOKEN={token}\n")
    os.environ["ACCESS_TOKEN"] = token
    print(f"Created a new ACCESS_TOKEN in {config.ENV_FILE}")
    return token


def start_tunnel(port: int):
    """Start a Cloudflare quick tunnel to the local server. Returns (process, public https URL)."""
    import queue
    import re
    import shutil
    import subprocess
    import threading

    exe = shutil.which("cloudflared")
    if not exe:
        raise SystemExit("cloudflared is not installed. Install it with:  winget install Cloudflare.cloudflared\n"
                         "then open a new terminal and run this again.")
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            continue
        if line is None:
            break
        found = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if found:
            return proc, found.group(0)
    proc.terminate()
    raise SystemExit("cloudflared did not give a public address within 40 s. Check this network allows outbound HTTPS.")


def show_phone_link(url: str, token: str) -> None:
    link = f"{url}/phone?key={token}"
    print("\nOn the phone, scan this code or open this link (it contains the secret key; do not share it):")
    print(f"  {link}\n")
    try:
        import segno

        qr = segno.make(link, error="m")
        qr.save(INPUTS / "phone-link.png", scale=8, border=4)
        qr.terminal(compact=True)
        print(f"(Same code saved as {INPUTS / 'phone-link.png'})\n")
    except ImportError:
        print("(pip install segno to also get a QR code)\n")
    except UnicodeEncodeError:
        print(f"(Terminal cannot draw the QR code; open {INPUTS / 'phone-link.png'} instead)\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", nargs="?", type=Path, help="video file (default: newest .mp4 in inputs/)")
    parser.add_argument("--serve", action="store_true", help="start the demo web page")
    parser.add_argument("--tunnel", action="store_true",
                        help="with --serve, also open a Cloudflare tunnel so a phone can use /phone (needs cloudflared)")
    parser.add_argument("--mock", action="store_true", help="mock Presage (fake vitals)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="with --serve, do not open the browser")
    args = parser.parse_args()

    from src.services.recordings import save_recording
    from src.services.results_log import log_result
    from src.services.rppg_extractor import extract_vitals_from_video
    from src.services.sidecar_manager import ensure_sidecar, sidecar_mode
    from src.services.video_prep import downsample_video

    if args.tunnel:
        args.serve = True
    proc = ensure_sidecar(mock=args.mock)
    tunnel = None
    print(f"Presage sidecar: {sidecar_mode()} mode" + (" (started by run.py)" if proc else " (already running)"))
    try:
        if args.serve:
            import threading
            import webbrowser

            import uvicorn

            url = f"http://127.0.0.1:{args.port}"
            open_url = url
            if args.tunnel:
                token = ensure_access_token()
                # The tunnel can connect before the server is up; requests only start once the phone opens the link.
                tunnel, public_url = start_tunnel(args.port)
                show_phone_link(public_url, token)
                open_url = f"{public_url}/?key={token}"   # the laptop uses the same public address, key included
            print(f"Demo page: {url}   (Ctrl+C to stop; the page only works while this is running)")
            if not args.no_browser:
                threading.Timer(1.5, webbrowser.open, args=[open_url]).start()
            uvicorn.run("src.app:app", host="127.0.0.1", port=args.port, log_level="warning")
            return 0

        video = args.video or newest_video()
        if not video or not video.exists():
            print("No video found. Put an .mp4 in inputs/ or pass a path.", file=sys.stderr)
            return 1

        raw = video.read_bytes()
        t0 = time.time()
        small = downsample_video(raw)
        print(f"{video.name}: {len(raw) / 1e6:.1f} MB -> {len(small) / 1e6:.1f} MB in {time.time() - t0:.0f}s")
        print("Running Presage (plays the video in real time, so this takes about as long as the clip)...")
        t1 = time.time()
        result = extract_vitals_from_video(small)
        presage_s = time.time() - t1
        print(f"Done in {presage_s:.0f}s")
        print(result.model_dump_json(indent=2, exclude={"diagnostics": {"pulse_series", "breathing_series"}}))
        log_path = log_result(
            video.name,
            {"original": round(len(raw) / 1e6, 1), "sent": round(len(small) / 1e6, 1)},
            {"downsample": round(t1 - t0, 1), "presage": round(presage_s, 1)},
            result,
            saved_file=save_recording("video", small, "mp4", label=video.name),
        )
        print(f"Logged to {log_path}")
        return 0
    finally:
        if tunnel:
            tunnel.terminate()
        if proc:
            proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
