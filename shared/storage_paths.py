import os
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "FightingOverlay"


def base_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME / "data"
    return Path.home() / ".local" / "share" / APP_NAME / "data"


@dataclass(frozen=True)
class ClipPaths:
    base_dir: Path
    profile_dir: Path
    clip_dir: Path
    input_dir: Path
    outputs_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class GlobalPaths:
    base_dir: Path
    logs_dir: Path


def get_global_paths() -> GlobalPaths:
    base_dir = base_data_dir()
    return GlobalPaths(
        base_dir=base_dir,
        logs_dir=base_dir / "logs",
    )


def get_clip_paths(athlete_id: str, clip_id: str) -> ClipPaths:
    base_dir = base_data_dir()
    profile_dir = base_dir / "profiles" / athlete_id
    clip_dir = profile_dir / "clips" / clip_id
    return ClipPaths(
        base_dir=base_dir,
        profile_dir=profile_dir,
        clip_dir=clip_dir,
        input_dir=clip_dir / "input",
        outputs_dir=clip_dir / "outputs",
        logs_dir=clip_dir / "logs",
    )


def ensure_clip_dirs(clip_paths: ClipPaths) -> None:
    clip_paths.input_dir.mkdir(parents=True, exist_ok=True)
    clip_paths.outputs_dir.mkdir(parents=True, exist_ok=True)
    clip_paths.logs_dir.mkdir(parents=True, exist_ok=True)


def ensure_global_dirs(global_paths: GlobalPaths) -> None:
    global_paths.logs_dir.mkdir(parents=True, exist_ok=True)
