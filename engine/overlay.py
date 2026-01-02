import shutil
import subprocess
import sys
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe

from engine.errors import KnownError


def resolve_ffmpeg_path(logger) -> str | None:
    try:
        return get_ffmpeg_exe()
    except Exception as exc:
        logger.warning("Bundled FFmpeg not available: %s", exc)

    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    candidate = base_dir / "ffmpeg.exe"
    if candidate.exists():
        return str(candidate)
    return None


def render_overlay(video_path: Path, outputs_dir: Path, logger) -> dict:
    overlay_path = outputs_dir / "overlay.mp4"
    ffmpeg_path = resolve_ffmpeg_path(logger)

    if ffmpeg_path:
        logger.info("FFmpeg detected; copying video with metadata.")
        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(video_path),
                "-c",
                "copy",
                str(overlay_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {"overlay_path": str(overlay_path), "overlay_status": "copied"}
        logger.warning("FFmpeg copy failed; stderr: %s", result.stderr)

    try:
        import cv2  # noqa: F401
        logger.info("OpenCV detected; fallback to direct copy for now.")
    except Exception as exc:
        logger.error("OpenCV not available: %s", exc)
        raise KnownError(
            "E_CV2_IMPORT",
            "OpenCV import failed.",
            "Engine bundle may be missing OpenCV DLLs. Use the Release zip; do not run from source.",
        ) from exc

    shutil.copyfile(video_path, overlay_path)
    return {"overlay_path": str(overlay_path), "overlay_status": "copied"}
