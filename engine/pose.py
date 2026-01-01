import json
import time
from pathlib import Path


def extract_pose(video_path: Path, outputs_dir: Path, logger) -> dict:
    """Extract pose data using MediaPipe if available; otherwise emit stub."""
    pose_path = outputs_dir / "pose.json"
    started = time.time()
    pose_data = {
        "status": "stub",
        "frames": [],
        "source": str(video_path),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        import mediapipe as mp  # noqa: F401
        # Placeholder for actual MediaPipe implementation.
        pose_data["status"] = "mediapipe_unimplemented"
        pose_data["frames"] = [
            {
                "timestamp_ms": 0,
                "landmarks": [],
            }
        ]
        logger.info("MediaPipe available; using placeholder pose extraction.")
    except Exception as exc:
        logger.warning("MediaPipe not available; using stub pose output: %s", exc)
        pose_data["frames"] = [
            {
                "timestamp_ms": 0,
                "landmarks": [
                    {"x": 0.5, "y": 0.5, "z": 0.0, "name": "stub"}
                ],
            }
        ]
    pose_data["duration_ms"] = int((time.time() - started) * 1000)
    pose_path.write_text(json.dumps(pose_data, indent=2))
    return {
        "pose_path": str(pose_path),
        "pose_status": pose_data["status"],
        "pose_duration_ms": pose_data["duration_ms"],
    }
