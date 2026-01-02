import importlib
import importlib.util
import json
from pathlib import Path

from engine.errors import KnownError


def render_overlay(video_path: Path, outputs_dir: Path, logger) -> dict:
    overlay_path = outputs_dir / "overlay.mp4"
    pose_path = outputs_dir / "pose.json"

    if importlib.util.find_spec("cv2") is None:
        raise KnownError(
            "E_CV2_IMPORT",
            "OpenCV import failed.",
            "Engine bundle may be missing OpenCV DLLs. Use the Release zip; do not run from source.",
        )
    if importlib.util.find_spec("mediapipe") is None:
        raise KnownError(
            "E_MEDIAPIPE_MISSING",
            "MediaPipe is required for overlay rendering.",
            "This release is missing mediapipe in engine.exe; rebuild release.",
        )

    cv2 = importlib.import_module("cv2")
    mp = importlib.import_module("mediapipe")
    landmark_pb2 = importlib.import_module("mediapipe.framework.formats.landmark_pb2")

    if not pose_path.exists():
        raise KnownError("E_POSE_MISSING", "pose.json missing.", "Run pose extraction before overlay rendering.")

    pose_data = json.loads(pose_path.read_text())
    frames = pose_data.get("frames", [])
    primary_track_ids = pose_data.get("primary_track_ids", [])

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise KnownError("E_VIDEO_OPEN", "Unable to open video.", "Check codec support and file path.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(overlay_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise KnownError("E_OVERLAY_WRITE", "Failed to open overlay writer.", "Check codec availability.")

    frame_map: dict[int, dict] = {}
    for frame in frames:
        frame_index = frame.get("frame_index")
        if frame_index is None:
            continue
        frame_map[frame_index] = frame

    mp_pose = mp.solutions.pose
    drawing_utils = mp.solutions.drawing_utils
    name_to_index = {landmark.name: landmark.value for landmark in mp_pose.PoseLandmark}

    frame_index = 0
    track_colors = _build_track_colors(primary_track_ids)
    while True:
        success, frame = cap.read()
        if not success:
            break

        frame_data = frame_map.get(frame_index)
        if frame_data:
            for track_frame in frame_data.get("tracks", []):
                landmarks = track_frame.get("landmarks", [])
                if not landmarks:
                    continue
                track_id = track_frame.get("track_id")
                is_predicted = bool(track_frame.get("is_predicted"))
                color = track_colors.get(track_id, (255, 255, 255))
                landmark_list = _build_landmark_list(landmarks, name_to_index, landmark_pb2)
                if is_predicted:
                    drawing_utils.draw_landmarks(
                        frame,
                        landmark_list,
                        mp_pose.POSE_CONNECTIONS,
                        drawing_utils.DrawingSpec(color=color, thickness=1, circle_radius=1),
                        drawing_utils.DrawingSpec(color=color, thickness=1, circle_radius=1),
                    )
                    _draw_pred_label(frame, track_frame.get("bbox"), color)
                else:
                    drawing_utils.draw_landmarks(
                        frame,
                        landmark_list,
                        mp_pose.POSE_CONNECTIONS,
                        drawing_utils.DrawingSpec(color=color, thickness=2, circle_radius=2),
                        drawing_utils.DrawingSpec(color=color, thickness=2, circle_radius=2),
                    )
        writer.write(frame)
        frame_index += 1

    cap.release()
    writer.release()

    overlay_bytes = overlay_path.stat().st_size if overlay_path.exists() else 0
    overlay_status = "ok" if overlay_bytes > 0 else "error"
    if overlay_bytes == 0:
        logger.error("Overlay generation produced empty file.")
    return {
        "overlay_path": str(overlay_path),
        "overlay_status": overlay_status,
        "overlay_bytes": overlay_bytes,
    }


def _build_landmark_list(landmarks: list[dict], name_to_index: dict[str, int], landmark_pb2):
    ordered = [None] * (max(name_to_index.values()) + 1 if name_to_index else len(landmarks))
    for landmark in landmarks:
        name = landmark.get("name")
        if not name:
            continue
        idx = name_to_index.get(name)
        if idx is None:
            continue
        ordered[idx] = landmark_pb2.NormalizedLandmark(
            x=float(landmark.get("x", 0.0)),
            y=float(landmark.get("y", 0.0)),
            z=float(landmark.get("z", 0.0)),
            visibility=float(landmark.get("conf", 0.0) or 0.0),
        )

    filled = [
        lm
        if lm is not None
        else landmark_pb2.NormalizedLandmark(x=0.0, y=0.0, z=0.0, visibility=0.0)
        for lm in ordered
    ]
    return landmark_pb2.NormalizedLandmarkList(landmark=filled)


def _build_track_colors(primary_track_ids: list[int]) -> dict[int, tuple[int, int, int]]:
    palette = [
        (0, 200, 255),  # Track A (orange-ish)
        (0, 255, 100),  # Track B (green)
    ]
    return {track_id: palette[idx % len(palette)] for idx, track_id in enumerate(primary_track_ids)}


def _draw_pred_label(frame, bbox: dict | None, color: tuple[int, int, int]) -> None:
    import cv2

    if bbox:
        x = int(bbox.get("x_min", 0.0) * frame.shape[1])
        y = int(bbox.get("y_min", 0.0) * frame.shape[0])
        pos = (max(x, 0), max(y - 10, 10))
    else:
        pos = (10, 30)
    cv2.putText(
        frame,
        "PRED",
        pos,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        1,
        cv2.LINE_AA,
    )
