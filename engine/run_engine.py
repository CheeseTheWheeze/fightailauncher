import argparse
import json
import logging
import shutil
import sys
import time
import traceback
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.errors import KnownError  # noqa: E402
from engine.overlay import render_overlay  # noqa: E402
from engine.pose import extract_pose  # noqa: E402
from engine.result_contract import (  # noqa: E402
    ResultStatus,
    safe_write_json,
    write_result_error,
    write_result_ok,
)
from shared.storage_paths import (  # noqa: E402
    ensure_global_dirs,
    ensure_run_dirs,
    get_global_paths,
    get_run_paths,
)


def setup_logging(engine_log: Path) -> logging.Logger:
    logger = logging.getLogger("engine")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(engine_log)
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger


def read_version() -> str:
    version_path = REPO_ROOT / "shared" / "version.json"
    if version_path.exists():
        try:
            payload = json.loads(version_path.read_text())
            return payload.get("version", "unknown")
        except Exception:
            return "unknown"
    return "unknown"


def resolve_outputs_logs(run_id: str, args: argparse.Namespace):
    run_paths = get_run_paths(run_id)
    ensure_run_dirs(run_paths)

    outputs_dir = Path(args.outdir) if args.outdir else run_paths.outputs_dir
    outputs_dir.mkdir(parents=True, exist_ok=True)

    logs_dir = run_paths.logs_dir
    if args.outdir:
        logs_dir = Path(args.outdir).parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    return run_paths, outputs_dir, logs_dir


def analyze(args: argparse.Namespace) -> int:
    started = time.time()
    run_id = args.run_id or uuid.uuid4().hex
    run_paths, outputs_dir, logs_dir = resolve_outputs_logs(run_id, args)
    global_paths = get_global_paths()
    ensure_global_dirs(global_paths)

    engine_log = logs_dir / "engine.log"
    engine_log.touch(exist_ok=True)
    logger = setup_logging(engine_log)

    video_path = Path(args.video)
    result = {
        "status": ResultStatus.ERROR,
        "run_id": run_id,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": read_version(),
        "inputs": {
            "video": str(video_path),
            "run_id": run_id,
        },
        "outputs": {
            "overlay_mp4": "overlay.mp4",
            "pose_json": "pose.json",
            "result_json": "result.json",
            "error_json": "error.json",
            "outputs_dir": str(outputs_dir),
        },
        "logs": {
            "engine_log": "engine.log",
            "logs_dir": str(logs_dir),
        },
        "warnings": [],
    }

    exit_code = 3
    try:
        logger.info("Starting analysis for run_id=%s", run_id)

        if not video_path.exists():
            raise KnownError(
                "E_VIDEO_MISSING",
                "Video file does not exist.",
                f"Check the path: {video_path}",
            )

        if not video_path.is_file():
            raise KnownError(
                "E_VIDEO_INVALID",
                "Video path is not a file.",
                f"Check the path: {video_path}",
            )

        input_copy = run_paths.input_dir / video_path.name
        if input_copy.resolve() != video_path.resolve():
            shutil.copyfile(video_path, input_copy)

        pose_result = extract_pose(video_path, outputs_dir, logger)
        overlay_result = render_overlay(video_path, outputs_dir, logger)
        result["outputs"]["pose_json"] = _relative_to(outputs_dir, pose_result["pose_path"])
        result["outputs"]["overlay_mp4"] = _relative_to(outputs_dir, overlay_result["overlay_path"])
        result["timings_ms"] = {
            "total": int((time.time() - started) * 1000),
            "pose": pose_result["pose_duration_ms"],
        }
        result["pose_extraction"] = {
            "status": pose_result["pose_status"],
            "frames_with_detections": pose_result.get("pose_frames_with_detections", 0),
        }
        result["overlay"] = {
            "status": overlay_result["overlay_status"],
            "bytes": overlay_result.get("overlay_bytes", 0),
        }
        result["pose_frames_with_detections"] = pose_result.get("pose_frames_with_detections", 0)
        result["overlay_bytes"] = overlay_result.get("overlay_bytes", 0)

        write_result_ok(result)
        exit_code = 0
        logger.info("Analysis completed successfully.")
    except KnownError as exc:
        write_result_error(result, exc.code, exc.message, exc.hint)
        exit_code = 2
        logger.error("Handled error: %s (%s)", exc.message, exc.code)
    except Exception as exc:
        stack = traceback.format_exc()
        write_result_error(
            result,
            "E_UNEXPECTED",
            "Unexpected engine crash.",
            "Check engine.log for details.",
        )
        result["error"]["details"] = {
            "exception": f"{type(exc).__name__}: {exc}",
            "stack": stack,
        }
        exit_code = 3
        logger.exception("Unexpected error")
    finally:
        result["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result["duration_ms"] = int((time.time() - started) * 1000)
        safe_write_json(outputs_dir / "result.json", result)
        if result.get("status") == ResultStatus.ERROR:
            safe_write_json(outputs_dir / "error.json", result.get("error", {}))
        _flush_logger(logger)

    return exit_code


def _relative_to(outputs_dir: Path, path_value: str) -> str:
    try:
        return str(Path(path_value).resolve().relative_to(outputs_dir.resolve()))
    except Exception:
        return str(path_value)


def _flush_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fighting Overlay Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a video")
    analyze_parser.add_argument("--video", required=True)
    analyze_parser.add_argument("--run-id", required=False)
    analyze_parser.add_argument("--outdir", required=False)
    analyze_parser.add_argument("--model", required=False)

    args = parser.parse_args()

    if args.command == "analyze":
        return analyze(args)
    raise SystemExit("Unknown command.")


if __name__ == "__main__":
    raise SystemExit(main())
