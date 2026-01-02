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
class RunPaths:
    base_dir: Path
    run_dir: Path
    input_dir: Path
    outputs_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class GlobalPaths:
    base_dir: Path
    logs_dir: Path
    profiles_pool_dir: Path
    profiles_pool_path: Path


def get_global_paths() -> GlobalPaths:
    base_dir = base_data_dir()
    profiles_pool_dir = base_dir / "profiles_pool"
    return GlobalPaths(
        base_dir=base_dir,
        logs_dir=base_dir / "logs",
        profiles_pool_dir=profiles_pool_dir,
        profiles_pool_path=profiles_pool_dir / "profiles.json",
    )


def get_run_paths(run_id: str) -> RunPaths:
    base_dir = base_data_dir()
    run_dir = base_dir / "runs" / run_id
    return RunPaths(
        base_dir=base_dir,
        run_dir=run_dir,
        input_dir=run_dir / "input",
        outputs_dir=run_dir / "outputs",
        logs_dir=run_dir / "logs",
    )


def ensure_run_dirs(run_paths: RunPaths) -> None:
    run_paths.input_dir.mkdir(parents=True, exist_ok=True)
    run_paths.outputs_dir.mkdir(parents=True, exist_ok=True)
    run_paths.logs_dir.mkdir(parents=True, exist_ok=True)


def ensure_global_dirs(global_paths: GlobalPaths) -> None:
    global_paths.logs_dir.mkdir(parents=True, exist_ok=True)
    global_paths.profiles_pool_dir.mkdir(parents=True, exist_ok=True)
