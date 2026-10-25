"""Transcribe an audio (or video) file with the speech model set in inputs/.env.

    python transcribe_file.py path/to/recording.m4a

Accepts anything ffmpeg can read (wav, mp3, m4a, ogg, webm, mp4...). The attempt is saved to
recordings/ and logged to logs/transcripts.json, exactly like the demo page's upload button.
"""
import sys
from pathlib import Path

from src.services.recordings import save_recording
from src.services.transcript_log import log_transcript
from src.services.transcription import transcribe_pcm, wav_bytes
from src.services.video_prep import audio_to_pcm


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    pcm = audio_to_pcm(path.read_bytes())
    entry = {"source": "file", "filename": path.name, "audio_file": save_recording("upload", wav_bytes(pcm), "wav", label=path.name)}
    try:
        result = transcribe_pcm(pcm)
    except Exception as exc:
        log_transcript({**entry, "error": f"{exc.__class__.__name__}: {exc}", "transcript": "", "segments": [], "duration_s": round(len(pcm) / 32000, 1)})
        print(f"Failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    log_transcript({**result, **entry})
    print(f"{result['duration_s']}s of audio, model: {result['model'] or 'mock'}")
    print(result["transcript"] or "(no speech recognised)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
