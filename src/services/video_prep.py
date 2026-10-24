import os
import shutil
import subprocess
import tempfile


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg") or "ffmpeg"


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
