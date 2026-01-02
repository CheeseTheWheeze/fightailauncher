import importlib
import importlib.util
import json
import time
from pathlib import Path

from engine.errors import KnownError
from engine.tracking import TrackManager

MAX_HOLD_FRAMES = 45
CONF_DECAY = 0.95
EMA_ALPHA = 0.4
PRIMARY_DROP_FRAMES = 45
NUM_POSES = 4
MIN_BBOX_HEIGHT_PX = 120
MIN_BBOX_HEIGHT_RATIO = 0.12
CROP_TRIGGER_PX = 180
CROP_TRIGGER_RATIO = 0.18
CROP_MARGIN = 0.25
CROP_TARGET_HEIGHT = 640
HEIGHT_WINDOW = 30
ASSIGNMENT_THRESHOLD = 2.5


def extract_pose(video_path: Path, outputs_dir: Path, logger, primary_tracks: int = 2, model_path: str | None = None) -> dict:
    pose_path = outputs_dir / "pose.json"
    pose_raw_path = outputs_dir / "pose_raw.json"
    started = time.time()

    if importlib.util.find_spec("cv2") is None:
        raise KnownError(
            "E_CV2_IMPORT",
            "OpenCV import failed.",
            "Engine bundle may be missing OpenCV DLLs. Use the Release zip; do not run from source.",
        )

    if importlib.util.find_spec("mediapipe") is None or importlib.util.find_spec("mediapipe.tasks") is None:
        raise KnownError(
            "E_MEDIAPIPE_MISSING",
            "MediaPipe Tasks is required for pose extraction.",
            "This release is missing mediapipe in engine.exe; rebuild release.",
        )

    cv2 = importlib.import_module("cv2")
    mp = importlib.import_module("mediapipe")
    mp_python = importlib.import_module("mediapipe.tasks.python")
    vision = importlib.import_module("mediapipe.tasks.python.vision")

    model_asset = _resolve_model_path(model_path, mp, logger)
    base_options = mp_python.BaseOptions(model_asset_path=str(model_asset))
    options_video = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_poses=NUM_POSES,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    options_image = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    landmarker_video = vision.PoseLandmarker.create_from_options(options_video)
    landmarker_image = vision.PoseLandmarker.create_from_options(options_image)
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

    tracker = TrackManager(
        primary_track_count=primary_tracks,
        max_hold_frames=MAX_HOLD_FRAMES,
        primary_drop_frames=PRIMARY_DROP_FRAMES,
        ema_alpha=EMA_ALPHA,
        conf_decay=CONF_DECAY,
        height_window=HEIGHT_WINDOW,
        assignment_threshold=ASSIGNMENT_THRESHOLD,
    )

    frames: list[dict] = []
    raw_frames: list[dict] = []
    raw_detections_total = 0
    frames_total = 0

    frame_index = 0
    while True:
        success, frame = cap.read()
        if not success:
            break

        timestamp_ms = int(frame_index * 1000 / fps) if fps else int(cap.get(cv2.CAP_PROP_POS_MSEC))
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = landmarker_video.detect_for_video(mp_image, timestamp_ms)

        detections = _detections_from_result(result, landmark_names, width, height)
        raw_detections_total += len(detections)
        raw_frames.append(
            {
                "frame_index": frame_index,
                "timestamp_ms": timestamp_ms,
                "detections": detections,
            }
        )

        tracker.update_tracks(detections, frame_index)

        _refine_primary_tracks(
            tracker,
            landmarker_image,
            frame,
            landmark_names,
            width,
            height,
            frame_index,
        )

        frame_tracks = tracker.build_primary_frame(frame_index, timestamp_ms)
        frames.append(
            {
                "frame_index": frame_index,
                "timestamp_ms": timestamp_ms,
                "tracks": frame_tracks,
            }
        )

        frame_index += 1
        frames_total += 1

    cap.release()
    landmarker_video.close()
    landmarker_image.close()

    raw_detections_per_frame_avg = raw_detections_total / frames_total if frames_total else 0.0
    tracking_summary = tracker.tracking_summary()
    primary_track_ids = tracking_summary.get("primary_track_ids", [])
    pose_metrics = _build_pose_metrics(tracker, frames_total, primary_track_ids)
    tracking_metrics = {
        **tracking_summary,
        "min_bbox_threshold_px": MIN_BBOX_HEIGHT_PX,
    }

    pose_data = {
        "schema_version": 2,
        "video": {
            "fps": fps,
            "width": width,
            "height": height,
            "duration": duration,
        },
        "primary_track_ids": primary_track_ids,
        "primary_track_count": primary_tracks,
        "frames": frames,
        "pose_metrics": pose_metrics,
        "tracking_metrics": tracking_metrics,
    }

    pose_raw = {
        "schema_version": 1,
        "video": {
            "fps": fps,
            "width": width,
            "height": height,
            "duration": duration,
        },
        "frames": raw_frames,
        "raw_detections_per_frame_avg": round(raw_detections_per_frame_avg, 4),
    }

    pose_path.write_text(json.dumps(pose_data, indent=2))
    pose_raw_path.write_text(json.dumps(pose_raw, indent=2))

    total_landmarks = sum(len(track.get("landmarks", [])) for frame in frames for track in frame.get("tracks", []))
    frames_with_detections = sum(
        1 for frame in frames if any(track.get("landmarks") for track in frame.get("tracks", []))
    )

    return {
        "pose_path": str(pose_path),
        "pose_raw_path": str(pose_raw_path),
        "pose_status": "ok" if total_landmarks > 0 else "ok_no_detections",
        "pose_duration_ms": int((time.time() - started) * 1000),
        "pose_frames_with_detections": frames_with_detections,
        "pose_metrics": pose_metrics,
        "tracking_metrics": tracking_metrics,
        "raw_detections_per_frame_avg": round(raw_detections_per_frame_avg, 4),
        "primary_track_ids": primary_track_ids,
        "primary_track_count": primary_tracks,
    }


def _resolve_model_path(model_path: str | None, mp_module, logger) -> Path:
    if model_path:
        candidate = Path(model_path)
        if candidate.exists():
            return candidate
        raise KnownError(
            "E_MODEL_MISSING",
            "Pose landmarker model not found.",
            f"Provided model path does not exist: {candidate}",
        )

    mp_root = Path(mp_module.__file__).resolve().parent
    candidates = [
        mp_root / "modules" / "pose_landmarker" / "pose_landmarker_heavy.task",
        mp_root / "modules" / "pose_landmarker" / "pose_landmarker_full.task",
        mp_root / "modules" / "pose_landmarker" / "pose_landmarker_lite.task",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    logger.error("Pose landmarker model not found in mediapipe package.")
    raise KnownError(
        "E_MODEL_MISSING",
        "Pose landmarker model not found.",
        "Bundle pose_landmarker_full.task (or lite/heavy) and pass --model to the engine.",
    )


def _detections_from_result(result, landmark_names: list[str], width: int, height: int) -> list[dict]:
    detections: list[dict] = []
    if not result.pose_landmarks:
        return detections
    for pose_landmarks in result.pose_landmarks:
        landmarks = _landmarks_from_result(pose_landmarks, landmark_names)
        bbox = _bbox_from_landmarks(landmarks, width, height)
        detections.append(
            {
                "landmarks": landmarks,
                "bbox": bbox,
                "center": ((bbox["x_min"] + bbox["x_max"]) / 2, (bbox["y_min"] + bbox["y_max"]) / 2),
                "scale": bbox["height"],
                "too_small": not bbox["above_threshold"],
                "above_threshold": bbox["above_threshold"],
            }
        )
    return detections


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


def _bbox_from_landmarks(landmarks: list[dict], width: int, height: int) -> dict:
    xs = [landmark["x"] for landmark in landmarks if landmark.get("x") is not None]
    ys = [landmark["y"] for landmark in landmarks if landmark.get("y") is not None]
    if not xs or not ys:
        return {
            "x_min": 0.0,
            "y_min": 0.0,
            "x_max": 0.0,
            "y_max": 0.0,
            "height": 0.0,
            "height_px": 0.0,
            "height_ratio": 0.0,
            "above_threshold": False,
        }
    x_min = max(min(xs), 0.0)
    y_min = max(min(ys), 0.0)
    x_max = min(max(xs), 1.0)
    y_max = min(max(ys), 1.0)
    height_ratio = max(y_max - y_min, 0.0)
    height_px = height_ratio * height
    above_threshold = height_px >= MIN_BBOX_HEIGHT_PX or height_ratio >= MIN_BBOX_HEIGHT_RATIO
    return {
        "x_min": x_min,
        "y_min": y_min,
        "x_max": x_max,
        "y_max": y_max,
        "height": height_ratio,
        "height_px": height_px,
        "height_ratio": height_ratio,
        "above_threshold": above_threshold,
    }


def _refine_primary_tracks(
    tracker: TrackManager,
    landmarker_image,
    frame,
    landmark_names: list[str],
    frame_width: int,
    frame_height: int,
    frame_index: int,
) -> None:
    for track_id in tracker.primary_track_ids:
        track = tracker.tracks.get(track_id)
        if not track:
            continue
        detection = track.current_detection
        bbox = None
        if detection:
            bbox = detection.get("bbox")
        if not bbox:
            bbox = track.last_bbox
        if not bbox:
            continue
        if not _should_refine(bbox):
            continue
        refined = _run_crop_pose(
            landmarker_image,
            frame,
            landmark_names,
            bbox,
            frame_width,
            frame_height,
        )
        if refined:
            tracker.override_detection(track_id, refined, frame_index)


def _should_refine(bbox: dict) -> bool:
    return bbox.get("height_px", 0.0) < CROP_TRIGGER_PX or bbox.get("height_ratio", 0.0) < CROP_TRIGGER_RATIO


def _run_crop_pose(
    landmarker_image,
    frame,
    landmark_names: list[str],
    bbox: dict,
    frame_width: int,
    frame_height: int,
) -> dict | None:
    import cv2
    import mediapipe as mp

    x_min = int(bbox["x_min"] * frame_width)
    x_max = int(bbox["x_max"] * frame_width)
    y_min = int(bbox["y_min"] * frame_height)
    y_max = int(bbox["y_max"] * frame_height)

    box_width = max(x_max - x_min, 1)
    box_height = max(y_max - y_min, 1)
    margin_x = int(box_width * CROP_MARGIN)
    margin_y = int(box_height * CROP_MARGIN)

    crop_x1 = max(x_min - margin_x, 0)
    crop_y1 = max(y_min - margin_y, 0)
    crop_x2 = min(x_max + margin_x, frame_width)
    crop_y2 = min(y_max + margin_y, frame_height)

    if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
        return None

    crop = frame[crop_y1:crop_y2, crop_x1:crop_x2]
    crop_height = crop.shape[0]
    crop_width = crop.shape[1]
    if crop_height == 0 or crop_width == 0:
        return None

    if crop_height < CROP_TARGET_HEIGHT:
        scale = CROP_TARGET_HEIGHT / crop_height
        resized = cv2.resize(crop, (int(crop_width * scale), int(crop_height * scale)))
    else:
        resized = crop

    rgb_crop = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_crop)
    result = landmarker_image.detect(mp_image)
    if not result.pose_landmarks:
        return None

    landmarks = _landmarks_from_result(result.pose_landmarks[0], landmark_names)
    mapped = _map_landmarks_to_full(landmarks, crop_x1, crop_y1, crop_width, crop_height, frame_width, frame_height)
    bbox_full = _bbox_from_landmarks(mapped, frame_width, frame_height)
    return {
        "landmarks": mapped,
        "bbox": bbox_full,
        "center": ((bbox_full["x_min"] + bbox_full["x_max"]) / 2, (bbox_full["y_min"] + bbox_full["y_max"]) / 2),
        "scale": bbox_full["height"],
        "too_small": not bbox_full["above_threshold"],
        "above_threshold": bbox_full["above_threshold"],
        "source": "crop",
    }


def _map_landmarks_to_full(
    landmarks: list[dict],
    crop_x: int,
    crop_y: int,
    crop_width: int,
    crop_height: int,
    frame_width: int,
    frame_height: int,
) -> list[dict]:
    mapped: list[dict] = []
    for landmark in landmarks:
        mapped.append(
            {
                "name": landmark.get("name"),
                "x": (crop_x + (landmark.get("x", 0.0) * crop_width)) / frame_width,
                "y": (crop_y + (landmark.get("y", 0.0) * crop_height)) / frame_height,
                "z": landmark.get("z"),
                "conf": landmark.get("conf"),
            }
        )
    return mapped


def _build_pose_metrics(tracker: TrackManager, frames_total: int, primary_track_ids: list[int]) -> dict:
    track_metrics = []
    for track_id in primary_track_ids[:2]:
        track = tracker.tracks.get(track_id)
        if track:
            track_metrics.append(
                {
                    "frames_detected": track.detected_frames,
                    "frames_predicted": track.predicted_frames,
                    "longest_dropout": track.longest_dropout,
                }
            )
        else:
            track_metrics.append({"frames_detected": 0, "frames_predicted": 0, "longest_dropout": 0})

    while len(track_metrics) < 2:
        track_metrics.append({"frames_detected": 0, "frames_predicted": 0, "longest_dropout": 0})

    track_a = track_metrics[0]
    track_b = track_metrics[1]
    detect_pct_a = track_a["frames_detected"] / frames_total if frames_total else 0.0
    detect_pct_b = track_b["frames_detected"] / frames_total if frames_total else 0.0

    return {
        "frames_total": frames_total,
        "frames_detected_trackA": track_a["frames_detected"],
        "frames_detected_trackB": track_b["frames_detected"],
        "detect_pct_trackA": round(detect_pct_a, 4),
        "detect_pct_trackB": round(detect_pct_b, 4),
        "longest_dropout_trackA": track_a["longest_dropout"],
        "longest_dropout_trackB": track_b["longest_dropout"],
        "frames_predicted_trackA": track_a["frames_predicted"],
        "frames_predicted_trackB": track_b["frames_predicted"],
    }
