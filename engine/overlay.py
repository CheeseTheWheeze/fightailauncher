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
    try:
        import mediapipe as mp
        from mediapipe.framework.formats import landmark_pb2
    except Exception as exc:
        raise KnownError(
            "E_MEDIAPIPE_MISSING",
            "MediaPipe is required for overlay rendering.",
            "This release is missing mediapipe in engine.exe; rebuild release.",
        ) from exc

    if not pose_path.exists():
        raise KnownError("E_POSE_MISSING", "pose.json missing.", "Run pose extraction before overlay rendering.")

    pose_data = json.loads(pose_path.read_text())
    frames = pose_data.get("frames", [])

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
    for frame in frames:
        frame_index = frame.get("frame_index")
        if frame_index is None:
            continue
        frame_map.setdefault(frame_index, []).append(frame)

    mp_pose = mp.solutions.pose
    drawing_utils = mp.solutions.drawing_utils
    drawing_styles = mp.solutions.drawing_styles
    name_to_index = {landmark.name: landmark.value for landmark in mp_pose.PoseLandmark}
    drawn_frames = 0

    frame_index = 0
    while True:
        success, frame = cap.read()
        if not success:
            break

        for track_frame in frame_map.get(frame_index, []):
            landmarks = track_frame.get("landmarks", [])
            if not landmarks:
                continue
            landmark_list = _build_landmark_list(landmarks, name_to_index, landmark_pb2)
            drawing_utils.draw_landmarks(
                frame,
                landmark_list,
                mp_pose.POSE_CONNECTIONS,
                drawing_styles.get_default_pose_landmarks_style(),
            )
            drawn_frames += 1

        writer.write(frame)
        frame_index += 1

    cap.release()
    writer.release()

    return {"overlay_path": str(overlay_path), "overlay_status": "ok" if drawn_frames > 0 else "no_pose"}


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
