import importlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

from engine.errors import KnownError
from shared.storage_paths import get_global_paths


def assign_tracks_to_profiles(video_path: Path, pose_path: Path, logger) -> list[dict[str, str]]:
    if importlib.util.find_spec("cv2") is None:
        raise KnownError(
            "E_CV2_IMPORT",
            "OpenCV import failed.",
            "Engine bundle may be missing OpenCV DLLs. Use the Release zip; do not run from source.",
        )

    importlib.import_module("cv2")

    if not pose_path.exists():
        raise KnownError("E_POSE_MISSING", "pose.json missing.", "Run pose extraction before profile assignment.")

    pose_data = json.loads(pose_path.read_text())
    tracks = _group_tracks(pose_data.get("frames", []))

    global_paths = get_global_paths()
    profiles_path = global_paths.profiles_pool_path
    profiles_path.parent.mkdir(parents=True, exist_ok=True)

    pool = _load_pool(profiles_path)
    assignments: list[dict[str, str]] = []

    if not tracks:
        _save_pool(profiles_path, pool)
        return assignments

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("Failed to open video for profile pool assignment.")
        _save_pool(profiles_path, pool)
        return assignments

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    for track in tracks:
        track_id = track.get("track_id")
        frames = track.get("frames", [])
        signature = _compute_signature(cap, frames, width, height)
        if signature is None:
            logger.warning("No signature computed for track %s", track_id)
            continue

        profile_id = _match_profile(pool, signature)
        if profile_id is None:
            profile_id = _next_profile_id(pool)
            pool.append({"profile_id": profile_id, "signature": signature})
        assignments.append({"track_id": track_id, "profile_id": profile_id})

    cap.release()
    _save_pool(profiles_path, pool)
    return assignments


def _group_tracks(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    track_map: dict[str, list[dict[str, Any]]] = {}
    for frame in frames:
        for track in frame.get("tracks", []):
            track_id = track.get("track_id")
            if track_id is None:
                continue
            track_map.setdefault(str(track_id), []).append(track)
    return [{"track_id": track_id, "frames": track_frames} for track_id, track_frames in track_map.items()]


def _compute_signature(cap, frames: list[dict[str, Any]], width: int, height: int) -> list[float] | None:
    import cv2

    sample_frames = [f for f in frames if f.get("landmarks")][:3]
    if not sample_frames:
        return None

    histograms: list[list[float]] = []
    for frame in sample_frames:
        frame_index = frame.get("frame_index")
        if frame_index is None:
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        success, image = cap.read()
        if not success or image is None:
            continue

        crop = _crop_from_landmarks(image, frame.get("landmarks", []), width, height)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        histograms.append(hist.flatten().astype(float).tolist())

    if not histograms:
        return None

    averaged = [0.0] * len(histograms[0])
    for hist in histograms:
        for idx, value in enumerate(hist):
            averaged[idx] += float(value)
    return [value / len(histograms) for value in averaged]


def _crop_from_landmarks(image, landmarks: list[dict[str, Any]], width: int, height: int):
    import cv2

    if not landmarks:
        return image

    xs = [lm["x"] for lm in landmarks if lm.get("x") is not None]
    ys = [lm["y"] for lm in landmarks if lm.get("y") is not None]
    if not xs or not ys:
        return image

    min_x = max(min(xs) - 0.1, 0.0)
    max_x = min(max(xs) + 0.1, 1.0)
    min_y = max(min(ys) - 0.1, 0.0)
    max_y = min(max(ys) + 0.1, 1.0)

    x1 = int(min_x * width)
    x2 = int(max_x * width)
    y1 = int(min_y * height)
    y2 = int(max_y * height)

    if x2 <= x1 or y2 <= y1:
        return image

    return image[y1:y2, x1:x2]


def _match_profile(pool: list[dict[str, Any]], signature: list[float]) -> str | None:
    best_id = None
    best_score = 0.0
    for profile in pool:
        existing = profile.get("signature")
        if not existing:
            continue
        score = _cosine_similarity(existing, signature)
        if score > best_score:
            best_score = score
            best_id = profile.get("profile_id")
    if best_score >= 0.9:
        return best_id
    return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _next_profile_id(pool: list[dict[str, Any]]) -> str:
    max_id = 0
    for profile in pool:
        profile_id = profile.get("profile_id", "")
        if profile_id.startswith("p_"):
            try:
                max_id = max(max_id, int(profile_id.split("_")[1]))
            except Exception:
                continue
    return f"p_{max_id + 1:04d}"


def _load_pool(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text()).get("profiles", [])
    except Exception:
        return []


def _save_pool(path: Path, pool: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": 1,
        "profiles": pool,
    }
    path.write_text(json.dumps(payload, indent=2))
