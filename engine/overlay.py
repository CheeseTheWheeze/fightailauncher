import shutil
import subprocess
from pathlib import Path


def render_overlay(video_path: Path, outputs_dir: Path, logger) -> dict:
    overlay_path = outputs_dir / "overlay.mp4"
    ffmpeg_path = shutil.which("ffmpeg")
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
        logger.warning("OpenCV not available: %s", exc)

    shutil.copyfile(video_path, overlay_path)
    return {"overlay_path": str(overlay_path), "overlay_status": "copied"}
