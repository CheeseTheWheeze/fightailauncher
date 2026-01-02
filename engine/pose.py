import json
import time
from pathlib import Path

from engine.errors import KnownError

MAX_HOLD_FRAMES = 15
CONF_DECAY = 0.95
EMA_ALPHA = 0.4


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
    frames_with_detections = 0
    frames_total = 0
    longest_dropout_frames = 0
    current_dropout_frames = 0
    hold_frames = 0
    last_pose: list[dict] | None = None
    last_smoothed: list[dict] | None = None

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

            landmarks_payload: list[dict] = []
            is_predicted = False
            if result.pose_landmarks:
                landmarks_payload = _landmarks_from_result(result.pose_landmarks.landmark, landmark_names)
                landmarks_payload = _smooth_landmarks(landmarks_payload, last_smoothed, EMA_ALPHA)
                last_smoothed = landmarks_payload
                last_pose = landmarks_payload
                total_landmarks += len(landmarks_payload)
                frames_with_detections += 1
                hold_frames = 0
                current_dropout_frames = 0
            else:
                current_dropout_frames += 1
                longest_dropout_frames = max(longest_dropout_frames, current_dropout_frames)
                if last_pose is not None and hold_frames < MAX_HOLD_FRAMES:
                    hold_frames += 1
                    decay_factor = CONF_DECAY**hold_frames
                    landmarks_payload = _apply_conf_decay(last_pose, decay_factor)
                    is_predicted = True
                else:
                    hold_frames = min(hold_frames + 1, MAX_HOLD_FRAMES + 1)

            frames_total += 1

            frames.append(
                {
                    "frame_index": frame_index,
                    "timestamp_ms": timestamp_ms,
                    "landmarks": landmarks_payload,
                    "is_predicted": is_predicted,
                }
            )
            frame_index += 1

    cap.release()

    detect_pct = frames_with_detections / frames_total if frames_total else 0.0
    pose_metrics = {
        "frames_total": frames_total,
        "frames_detected": frames_with_detections,
        "detect_pct": round(detect_pct, 4),
        "longest_dropout_frames": longest_dropout_frames,
    }

    pose_data = {
        "schema_version": 1,
        "video": {
            "fps": fps,
            "width": width,
            "height": height,
            "duration": duration,
        },
        "frames": frames,
        "pose_metrics": pose_metrics,
    }

    pose_path.write_text(json.dumps(pose_data, indent=2))
    return {
        "pose_path": str(pose_path),
        "pose_status": "ok" if total_landmarks > 0 else "ok_no_detections",
        "pose_duration_ms": int((time.time() - started) * 1000),
        "pose_frames_with_detections": frames_with_detections,
        "pose_metrics": pose_metrics,
    }


def _landmarks_from_result(landmarks, landmark_names: list[str]) -> list[dict]:
    payload = []
    for idx, lm in enumerate(landmarks):
        name = landmark_names[idx] if idx < len(landmark_names) else f"LANDMARK_{idx}"
        conf = getattr(lm, "visibility", None)
        payload.append(
            {
                "name": name,
                "x": float(lm.x),
                "y": float(lm.y),
                "z": float(lm.z),
                "conf": float(conf) if conf is not None else None,
            }
        )
    return payload


def _smooth_landmarks(current: list[dict], previous: list[dict] | None, alpha: float) -> list[dict]:
    if not previous:
        return current
    previous_map = {landmark.get("name"): landmark for landmark in previous}
    smoothed = []
    for landmark in current:
        name = landmark.get("name")
        prev = previous_map.get(name)
        if not prev:
            smoothed.append(landmark)
            continue
        smoothed.append(
            {
                "name": name,
                "x": _ema(landmark.get("x"), prev.get("x"), alpha),
                "y": _ema(landmark.get("y"), prev.get("y"), alpha),
                "z": _ema(landmark.get("z"), prev.get("z"), alpha),
                "conf": _ema(landmark.get("conf"), prev.get("conf"), alpha),
            }
        )
    return smoothed


def _ema(current_value, previous_value, alpha: float):
    if current_value is None:
        return previous_value
    if previous_value is None:
        return current_value
    return (alpha * current_value) + ((1 - alpha) * previous_value)


def _apply_conf_decay(landmarks: list[dict], decay_factor: float) -> list[dict]:
    decayed = []
    for landmark in landmarks:
        conf = landmark.get("conf")
        if conf is not None:
            conf = float(conf) * decay_factor
        decayed.append(
            {
                "name": landmark.get("name"),
                "x": float(landmark.get("x", 0.0)),
                "y": float(landmark.get("y", 0.0)),
                "z": float(landmark.get("z", 0.0)),
                "conf": conf,
            }
        )
    return decayed
