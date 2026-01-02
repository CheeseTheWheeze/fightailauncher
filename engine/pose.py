import json
import time
from pathlib import Path

from engine.errors import KnownError


def extract_pose(video_path: Path, outputs_dir: Path, logger) -> dict:
    pose_path = outputs_dir / "pose.json"
    started = time.time()

    try:
        import cv2
    except Exception as exc:
        raise KnownError(
            "E_CV2_IMPORT",
            "OpenCV import failed.",
            "Engine bundle may be missing OpenCV DLLs. Use the Release zip; do not run from source.",
        ) from exc

    try:
        import mediapipe as mp
    except Exception as exc:
        raise KnownError(
            "E_MEDIAPIPE_MISSING",
            "MediaPipe is required for pose extraction.",
            "This release is missing mediapipe in engine.exe; rebuild release.",
        ) from exc

    mp_pose = mp.solutions.pose
    landmark_names = [landmark.name for landmark in mp_pose.PoseLandmark]

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise KnownError("E_VIDEO_OPEN", "Unable to open video.", "Check codec support and file path.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps else 0.0

    frames: list[dict] = []
    total_landmarks = 0

    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        frame_index = 0
        while True:
            success, frame = cap.read()
            if not success:
                break

            timestamp_ms = int(frame_index * 1000 / fps) if fps else int(cap.get(cv2.CAP_PROP_POS_MSEC))
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb_frame)

            landmarks_payload = []
            if result.pose_landmarks:
                for idx, lm in enumerate(result.pose_landmarks.landmark):
                    name = landmark_names[idx] if idx < len(landmark_names) else f"LANDMARK_{idx}"
                    conf = getattr(lm, "visibility", None)
                    landmarks_payload.append(
                        {
                            "name": name,
                            "x": float(lm.x),
                            "y": float(lm.y),
                            "z": float(lm.z),
                            "conf": float(conf) if conf is not None else None,
                        }
                    )

            if landmarks_payload:
                total_landmarks += len(landmarks_payload)

            frames.append(
                {
                    "frame_index": frame_index,
                    "timestamp_ms": timestamp_ms,
                    "landmarks": landmarks_payload,
                }
            )
            frame_index += 1

    cap.release()

    pose_data = {
        "schema_version": 1,
        "video": {
            "fps": fps,
            "width": width,
            "height": height,
            "duration": duration,
        },
        "frames": frames,
    }

    pose_path.write_text(json.dumps(pose_data, indent=2))
    return {
        "pose_path": str(pose_path),
        "pose_status": "ok" if total_landmarks > 0 else "no_pose",
        "pose_duration_ms": int((time.time() - started) * 1000),
    }
