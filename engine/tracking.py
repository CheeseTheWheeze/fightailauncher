from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import hypot
from typing import Deque


@dataclass
class TrackState:
    track_id: int
    last_center: tuple[float, float] | None = None
    last_bbox: dict | None = None
    velocity: tuple[float, float] = (0.0, 0.0)
    last_landmarks: list[dict] | None = None
    last_smoothed: list[dict] | None = None
    current_detection: dict | None = None
    last_seen_frame: int = -1
    missed_frames: int = 0
    hold_frames: int = 0
    current_dropout: int = 0
    longest_dropout: int = 0
    detected_frames: int = 0
    predicted_frames: int = 0
    height_history: Deque[float] = field(default_factory=lambda: deque(maxlen=30))
    height_history_above: Deque[float] = field(default_factory=lambda: deque(maxlen=30))

    @property
    def average_height(self) -> float:
        if not self.height_history:
            return 0.0
        return sum(self.height_history) / len(self.height_history)

    @property
    def average_height_above(self) -> float:
        if not self.height_history_above:
            return 0.0
        return sum(self.height_history_above) / len(self.height_history_above)

    @property
    def has_above_threshold(self) -> bool:
        return len(self.height_history_above) > 0


class TrackManager:
    def __init__(
        self,
        primary_track_count: int,
        max_hold_frames: int,
        primary_drop_frames: int,
        ema_alpha: float,
        conf_decay: float,
        height_window: int = 30,
        assignment_threshold: float = 2.5,
    ) -> None:
        self.primary_track_count = primary_track_count
        self.max_hold_frames = max_hold_frames
        self.primary_drop_frames = primary_drop_frames
        self.ema_alpha = ema_alpha
        self.conf_decay = conf_decay
        self.assignment_threshold = assignment_threshold
        self.tracks: dict[int, TrackState] = {}
        self.primary_track_ids: list[int] = []
        self._next_id = 1
        self._height_window = height_window

    def update_tracks(self, detections: list[dict], frame_index: int) -> None:
        track_ids = list(self.tracks.keys())
        used_tracks: set[int] = set()
        used_detections: set[int] = set()

        pair_candidates: list[tuple[float, int, int]] = []
        for track_id in track_ids:
            track = self.tracks[track_id]
            if not track.last_center or not track.last_bbox:
                continue
            for det_idx, detection in enumerate(detections):
                cost = _assignment_cost(track, detection)
                if cost <= self.assignment_threshold:
                    pair_candidates.append((cost, track_id, det_idx))

        pair_candidates.sort(key=lambda item: item[0])

        for _, track_id, det_idx in pair_candidates:
            if track_id in used_tracks or det_idx in used_detections:
                continue
            self._apply_detection(track_id, detections[det_idx], frame_index)
            used_tracks.add(track_id)
            used_detections.add(det_idx)

        for det_idx, detection in enumerate(detections):
            if det_idx in used_detections:
                continue
            track_id = self._create_track(detection, frame_index)
            used_tracks.add(track_id)
            used_detections.add(det_idx)

        for track_id, track in self.tracks.items():
            if track_id in used_tracks:
                continue
            track.current_detection = None
            track.missed_frames += 1

        self._refresh_primary_tracks()

    def override_detection(self, track_id: int, detection: dict, frame_index: int) -> None:
        if track_id not in self.tracks:
            return
        self._apply_detection(track_id, detection, frame_index)

    def build_primary_frame(self, frame_index: int, timestamp_ms: int) -> list[dict]:
        frame_tracks: list[dict] = []
        for track_id in self.primary_track_ids:
            track = self.tracks.get(track_id)
            if not track:
                continue
            output = self._build_track_output(track, frame_index, timestamp_ms)
            frame_tracks.append(output)
        return frame_tracks

    def tracking_summary(self) -> dict:
        return {
            "num_tracks_total": len(self.tracks),
            "num_tracks_above_threshold": sum(1 for track in self.tracks.values() if track.has_above_threshold),
            "primary_track_ids": list(self.primary_track_ids),
        }

    def _create_track(self, detection: dict, frame_index: int) -> int:
        track_id = self._next_id
        self._next_id += 1
        track = TrackState(track_id=track_id)
        track.height_history = deque(maxlen=self._height_window)
        track.height_history_above = deque(maxlen=self._height_window)
        self.tracks[track_id] = track
        self._apply_detection(track_id, detection, frame_index)
        return track_id

    def _apply_detection(self, track_id: int, detection: dict, frame_index: int) -> None:
        track = self.tracks[track_id]
        track.current_detection = detection
        track.last_seen_frame = frame_index
        track.missed_frames = 0
        track.velocity = _velocity(track.last_center, detection["center"])
        track.last_center = detection["center"]
        track.last_bbox = detection["bbox"]
        track.height_history.append(detection["bbox"]["height"])
        if detection.get("above_threshold"):
            track.height_history_above.append(detection["bbox"]["height"])

    def _refresh_primary_tracks(self) -> None:
        if not self.primary_track_ids:
            self.primary_track_ids = self._select_primary_tracks()
            return

        refreshed: list[int] = []
        for track_id in self.primary_track_ids:
            track = self.tracks.get(track_id)
            if not track:
                continue
            if track.missed_frames > self.primary_drop_frames:
                continue
            refreshed.append(track_id)

        if len(refreshed) < self.primary_track_count:
            refreshed = self._select_primary_tracks()

        self.primary_track_ids = refreshed

    def _select_primary_tracks(self) -> list[int]:
        candidates = [track for track in self.tracks.values() if track.has_above_threshold]
        candidates.sort(key=lambda t: t.average_height_above, reverse=True)
        return [track.track_id for track in candidates[: self.primary_track_count]]

    def _build_track_output(self, track: TrackState, frame_index: int, timestamp_ms: int) -> dict:
        detection = track.current_detection
        if detection and detection.get("above_threshold"):
            landmarks = detection["landmarks"]
            smoothed = smooth_landmarks(landmarks, track.last_smoothed, self.ema_alpha)
            track.last_smoothed = smoothed
            track.last_landmarks = smoothed
            track.hold_frames = 0
            track.current_dropout = 0
            track.detected_frames += 1
            return {
                "track_id": track.track_id,
                "frame_index": frame_index,
                "timestamp_ms": timestamp_ms,
                "landmarks": smoothed,
                "is_predicted": False,
                "too_small": False,
                "bbox": detection["bbox"],
            }

        if detection and detection.get("too_small"):
            track.current_dropout += 1
            track.longest_dropout = max(track.longest_dropout, track.current_dropout)
            track.hold_frames = 0
            return {
                "track_id": track.track_id,
                "frame_index": frame_index,
                "timestamp_ms": timestamp_ms,
                "landmarks": [],
                "is_predicted": False,
                "too_small": True,
                "bbox": detection["bbox"],
            }

        track.current_dropout += 1
        track.longest_dropout = max(track.longest_dropout, track.current_dropout)
        is_predicted = False
        landmarks_payload: list[dict] = []
        if track.last_landmarks and track.hold_frames < self.max_hold_frames:
            track.hold_frames += 1
            decay_factor = self.conf_decay**track.hold_frames
            landmarks_payload = apply_conf_decay(track.last_landmarks, decay_factor)
            is_predicted = True
            track.predicted_frames += 1
        return {
            "track_id": track.track_id,
            "frame_index": frame_index,
            "timestamp_ms": timestamp_ms,
            "landmarks": landmarks_payload,
            "is_predicted": is_predicted,
            "too_small": bool(detection and detection.get("too_small")),
            "bbox": detection["bbox"] if detection else None,
        }


def smooth_landmarks(current: list[dict], previous: list[dict] | None, alpha: float) -> list[dict]:
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


def apply_conf_decay(landmarks: list[dict], decay_factor: float) -> list[dict]:
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


def _ema(current_value, previous_value, alpha: float):
    if current_value is None:
        return previous_value
    if previous_value is None:
        return current_value
    return (alpha * current_value) + ((1 - alpha) * previous_value)


def _velocity(previous_center: tuple[float, float] | None, current_center: tuple[float, float]) -> tuple[float, float]:
    if not previous_center:
        return (0.0, 0.0)
    return (current_center[0] - previous_center[0], current_center[1] - previous_center[1])


def _assignment_cost(track: TrackState, detection: dict) -> float:
    track_bbox = track.last_bbox or {}
    track_height = track_bbox.get("height", 0.0) or 0.0
    det_height = detection["bbox"]["height"]
    dx = detection["center"][0] - track.last_center[0]
    dy = detection["center"][1] - track.last_center[1]
    norm = track_height if track_height > 0 else 1.0
    dist_cost = hypot(dx, dy) / norm
    size_cost = abs(det_height - track_height) / norm
    return dist_cost + size_cost
