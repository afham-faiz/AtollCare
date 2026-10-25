import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg") or "ffmpeg"


def _sniff_image(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalise_image(data: bytes, max_side: int = 2000, max_bytes: int = 4_000_000) -> tuple[bytes, str]:
    """Return (bytes, mime) ready for a vision model.

    Normal-sized JPEG/PNG/WEBP photos are sent untouched so small print stays sharp. Big photos and
    other formats are converted to a JPEG capped at max_side pixels (phone rotation applied).
    Raises ValueError if the file is not an image ffmpeg can read.
    """
    mime = _sniff_image(data)
    if mime and len(data) <= max_bytes:
        return data, mime
    scale = f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'"
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.bin"), os.path.join(tmp, "out.jpg")
        with open(src, "wb") as f:
            f.write(data)
        cmd = [_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", src, "-frames:v", "1", "-vf", scale, "-q:v", "3", dst]
        try:
            subprocess.run(cmd, check=True, timeout=120, capture_output=True)
            with open(dst, "rb") as f:
                return f.read(), "image/jpeg"
        except (subprocess.SubprocessError, OSError) as exc:
            if mime:  # could not shrink it, but the original is still a usable image
                return data, mime
            raise ValueError("Could not read that file as an image.") from exc


@dataclass
class Frame:
    index: int      # 1-based, as shown to the model and to the user
    t_s: float
    jpeg: bytes


_DURATION = re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)")


def _duration_s(path: str) -> float | None:
    probe = subprocess.run([_ffmpeg_exe(), "-i", path], capture_output=True, text=True, timeout=60)
    m = _DURATION.search(probe.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def sample_frames(video: bytes, every_s: float, max_frames: int, max_side: int = 768) -> list[Frame]:
    """Evenly spaced JPEG stills from a video (phone rotation applied). Raises ValueError if unreadable.

    One frame every `every_s` seconds, widened if needed so there are never more than `max_frames`.
    """
    scale = f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'"
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.bin")
        with open(src, "wb") as f:
            f.write(video)
        try:
            duration = _duration_s(src)
            interval = max(every_s, duration / max_frames) if duration else every_s
            cmd = [_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", src, "-an",
                   "-vf", f"fps=1/{interval},{scale}", "-frames:v", str(max_frames), "-q:v", "4",
                   os.path.join(tmp, "f_%03d.jpg")]
            subprocess.run(cmd, check=True, timeout=900, capture_output=True)
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError("Could not read frames from that video.") from exc
        files = sorted(p for p in os.listdir(tmp) if p.startswith("f_"))
        frames = []
        for i, name in enumerate(files):
            with open(os.path.join(tmp, name), "rb") as f:
                frames.append(Frame(index=i + 1, t_s=round(i * interval, 1), jpeg=f.read()))
    if not frames:
        raise ValueError("That video has no frames.")
    return frames


def audio_to_pcm(data: bytes) -> bytes:
    """Decode any audio (or video) upload to 16 kHz mono 16-bit PCM. Raises ValueError if unreadable."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.bin")
        with open(src, "wb") as f:
            f.write(data)
        cmd = [_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
        try:
            out = subprocess.run(cmd, check=True, timeout=600, capture_output=True).stdout
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError("Could not read that file as audio.") from exc
    if not out:
        raise ValueError("That file contains no audio.")
    return out


def downsample_video(video_bytes: bytes, max_side: int = 1280, crf: int = 26) -> bytes:
    """Shrink a phone video (applies rotation, caps long side, drops audio).

    Fails soft: if ffmpeg is missing or errors, the original bytes are returned.
    """
    scale = f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'"
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.mp4"), os.path.join(tmp, "out.mp4")
        with open(src, "wb") as f:
            f.write(video_bytes)
        cmd = [
            _ffmpeg_exe(), "-y", "-loglevel", "error", "-i", src, "-an", "-vf", scale,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p", dst,
        ]
        try:
            subprocess.run(cmd, check=True, timeout=600, capture_output=True)
            with open(dst, "rb") as f:
                return f.read()
        except (subprocess.SubprocessError, OSError):
            return video_bytes
