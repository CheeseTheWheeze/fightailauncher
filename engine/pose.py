import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.errors import KnownError
from shared.storage_paths import base_data_dir


POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/"
    "pose_landmarker_full.task"
)


@dataclass
class TrackState:
    track_id: str
    last_center: tuple[float, float]
    last_frame_index: int


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
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except Exception as exc:
        raise KnownError(
            "E_MEDIAPIPE_MISSING",
            "MediaPipe is required for pose extraction.",
            "Install the bundled engine build that includes MediaPipe.",
        ) from exc

    model_path = _ensure_pose_model(logger)
    base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
    running_mode = vision.RunningMode.VIDEO if hasattr(vision, "RunningMode") else vision.VisionRunningMode.VIDEO
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=running_mode,
        num_poses=5,
        output_segmentation_masks=False,
    )

    landmarker = vision.PoseLandmarker.create_from_options(options)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise KnownError("E_VIDEO_OPEN", "Unable to open video.", "Check codec support and file path.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps if fps else 0.0

    track_counter = 1
    tracks: dict[str, list[dict[str, Any]]] = {}
    track_states: list[TrackState] = []

    landmark_names = _landmark_names(mp)

    frame_index = 0
    while True:
        success, frame = cap.read()
        if not success:
            break

        timestamp_ms = int(frame_index * 1000 / fps) if fps else int(cap.get(cv2.CAP_PROP_POS_MSEC))
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = landmarker.detect_for_video(mp_image, timestamp_ms)

        detections = []
        for pose_landmarks in result.pose_landmarks:
            landmarks_payload = []
            xs = []
            ys = []
            confidences = []
            for idx, lm in enumerate(pose_landmarks):
                name = landmark_names[idx] if idx < len(landmark_names) else f"LANDMARK_{idx}"
                conf = getattr(lm, "visibility", None)
                if conf is not None:
                    confidences.append(float(conf))
                xs.append(float(lm.x))
                ys.append(float(lm.y))
                landmarks_payload.append(
                    {
                        "name": name,
                        "x": float(lm.x),
                        "y": float(lm.y),
                        "z": float(lm.z),
                        "conf": float(conf) if conf is not None else None,
                    }
                )

            center = (sum(xs) / len(xs), sum(ys) / len(ys)) if xs and ys else (0.5, 0.5)
            overall_conf = sum(confidences) / len(confidences) if confidences else None
            detections.append(
                {
                    "center": center,
                    "landmarks": landmarks_payload,
                    "overall_conf": overall_conf,
                }
            )

        assignments = _assign_tracks(detections, track_states)
        for detection, track_state in assignments:
            frame_payload = {
                "frame_index": frame_index,
                "timestamp_ms": timestamp_ms,
                "landmarks": detection["landmarks"],
                "overall_conf": detection["overall_conf"],
            }
            tracks.setdefault(track_state.track_id, []).append(frame_payload)
            track_state.last_center = detection["center"]
            track_state.last_frame_index = frame_index

        for detection in detections:
            if detection.get("assigned"):
                continue
            track_id = f"t{track_counter}"
            track_counter += 1
            new_track = TrackState(track_id=track_id, last_center=detection["center"], last_frame_index=frame_index)
            track_states.append(new_track)
            tracks.setdefault(track_id, []).append(
                {
                    "frame_index": frame_index,
                    "timestamp_ms": timestamp_ms,
                    "landmarks": detection["landmarks"],
                    "overall_conf": detection["overall_conf"],
                }
            )

        frame_index += 1

    cap.release()
    landmarker.close()

    pose_data = {
        "schema_version": 1,
        "video": {
            "fps": fps,
            "width": width,
            "height": height,
            "duration": duration,
        },
        "tracks": [
            {
                "track_id": track_id,
                "frames": tracks[track_id],
            }
            for track_id in sorted(tracks.keys())
        ],
    }

    pose_path.write_text(json.dumps(pose_data, indent=2))
    return {
        "pose_path": str(pose_path),
        "pose_status": "ok",
        "pose_duration_ms": int((time.time() - started) * 1000),
    }


def _ensure_pose_model(logger) -> Path:
    model_dir = base_data_dir() / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "pose_landmarker_full.task"
    if model_path.exists():
        return model_path

    try:
        import urllib.request

        logger.info("Downloading MediaPipe pose model to %s", model_path)
        urllib.request.urlretrieve(POSE_MODEL_URL, model_path)
    except Exception as exc:
        raise KnownError(
            "E_MEDIAPIPE_MODEL_MISSING",
            "MediaPipe pose model is missing.",
            "Ensure network access to download the pose_landmarker_full.task model.",
        ) from exc

    return model_path


def _landmark_names(mp) -> list[str]:
    try:
        from mediapipe.solutions.pose import PoseLandmark

        return [landmark.name for landmark in PoseLandmark]
    except Exception:
        return []


def _assign_tracks(detections: list[dict[str, Any]], track_states: list[TrackState]) -> list[tuple[dict[str, Any], TrackState]]:
    assignments = []
    used_tracks: set[str] = set()
    for detection in detections:
        best_state = None
        best_distance = None
        for state in track_states:
            if state.track_id in used_tracks:
                continue
            distance = _distance(detection["center"], state.last_center)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_state = state
        if best_state is not None and best_distance is not None and best_distance < 0.15:
            detection["assigned"] = True
            assignments.append((detection, best_state))
            used_tracks.add(best_state.track_id)
    return assignments


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
