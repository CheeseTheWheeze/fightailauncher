import json
from pathlib import Path

from engine.errors import KnownError


def render_overlay(video_path: Path, outputs_dir: Path, logger) -> dict:
    overlay_path = outputs_dir / "overlay.mp4"
    pose_path = outputs_dir / "pose.json"

    try:
        import cv2
    except Exception as exc:
        raise KnownError(
            "E_CV2_IMPORT",
            "OpenCV import failed.",
            "Engine bundle may be missing OpenCV DLLs. Use the Release zip; do not run from source.",
        ) from exc

    if not pose_path.exists():
        raise KnownError("E_POSE_MISSING", "pose.json missing.", "Run pose extraction before overlay rendering.")

    pose_data = json.loads(pose_path.read_text())
    tracks = pose_data.get("tracks", [])

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

    frame_map: dict[int, list[dict]] = {}
    track_colors = {}
    for idx, track in enumerate(tracks):
        track_id = track.get("track_id")
        track_colors[track_id] = idx
        for frame in track.get("frames", []):
            frame_index = frame.get("frame_index")
            if frame_index is None:
                continue
            frame_map.setdefault(frame_index, []).append(
                {
                    "track_id": track_id,
                    "landmarks": frame.get("landmarks", []),
                }
            )

    connections = _pose_connections()
    color_palette = [
        (0, 255, 255),
        (255, 0, 255),
        (255, 255, 0),
        (0, 255, 0),
        (0, 128, 255),
    ]

    frame_index = 0
    while True:
        success, frame = cap.read()
        if not success:
            break

        for track_frame in frame_map.get(frame_index, []):
            track_id = track_frame.get("track_id")
            color_index = track_colors.get(track_id, 0)
            color = color_palette[color_index % len(color_palette)]
            _draw_skeleton(frame, track_frame.get("landmarks", []), connections, color)

        writer.write(frame)
        frame_index += 1

    cap.release()
    writer.release()

    return {"overlay_path": str(overlay_path), "overlay_status": "rendered"}


def _pose_connections() -> list[tuple[str, str]]:
    try:
        from mediapipe.solutions.pose import POSE_CONNECTIONS, PoseLandmark

        name_map = {landmark.value: landmark.name for landmark in PoseLandmark}
        return [(name_map[a], name_map[b]) for a, b in POSE_CONNECTIONS]
    except Exception:
        return [
            ("LEFT_SHOULDER", "RIGHT_SHOULDER"),
            ("LEFT_SHOULDER", "LEFT_ELBOW"),
            ("LEFT_ELBOW", "LEFT_WRIST"),
            ("RIGHT_SHOULDER", "RIGHT_ELBOW"),
            ("RIGHT_ELBOW", "RIGHT_WRIST"),
            ("LEFT_SHOULDER", "LEFT_HIP"),
            ("RIGHT_SHOULDER", "RIGHT_HIP"),
            ("LEFT_HIP", "RIGHT_HIP"),
            ("LEFT_HIP", "LEFT_KNEE"),
            ("LEFT_KNEE", "LEFT_ANKLE"),
            ("RIGHT_HIP", "RIGHT_KNEE"),
            ("RIGHT_KNEE", "RIGHT_ANKLE"),
        ]


def _draw_skeleton(frame, landmarks: list[dict], connections: list[tuple[str, str]], color: tuple[int, int, int]):
    import cv2

    if not landmarks:
        return

    height, width = frame.shape[:2]
    points = {}
    for lm in landmarks:
        name = lm.get("name")
        if name is None:
            continue
        x = lm.get("x")
        y = lm.get("y")
        if x is None or y is None:
            continue
        px = int(x * width)
        py = int(y * height)
        points[name] = (px, py)
        cv2.circle(frame, (px, py), 5, color, thickness=-1)

    for start, end in connections:
        if start in points and end in points:
            cv2.line(frame, points[start], points[end], color, thickness=3)
