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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", nargs="?", type=Path, help="video file (default: newest .mp4 in inputs/)")
    parser.add_argument("--serve", action="store_true", help="start the demo web page")
    parser.add_argument("--mock", action="store_true", help="mock Presage (fake vitals)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="with --serve, do not open the browser")
    args = parser.parse_args()

    from src.services.recordings import save_recording
    from src.services.results_log import log_result
    from src.services.rppg_extractor import extract_vitals_from_video
    from src.services.sidecar_manager import ensure_sidecar, sidecar_mode
    from src.services.video_prep import downsample_video

    proc = ensure_sidecar(mock=args.mock)
    print(f"Presage sidecar: {sidecar_mode()} mode" + (" (started by run.py)" if proc else " (already running)"))
    try:
        if args.serve:
            import threading
            import webbrowser

            import uvicorn

            url = f"http://127.0.0.1:{args.port}"
            print(f"Demo page: {url}   (Ctrl+C to stop; the page only works while this is running)")
            if not args.no_browser:
                threading.Timer(1.5, webbrowser.open, args=[url]).start()
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
        if proc:
            proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
