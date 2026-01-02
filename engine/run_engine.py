import argparse
import json
import logging
import shutil
import sys
import time
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

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
    RunPaths,
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
    if args.outdir:
        run_dir = Path(args.outdir)
        run_paths = RunPaths(
            base_dir=run_dir,
            run_dir=run_dir,
            input_dir=run_dir / "input",
            outputs_dir=run_dir / "outputs",
            logs_dir=run_dir / "logs",
        )
    else:
        run_paths = get_run_paths(run_id)
    ensure_run_dirs(run_paths)

    return run_paths, run_paths.outputs_dir, run_paths.logs_dir


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
            "pose_raw_json": "pose_raw.json",
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

        pose_result = extract_pose(
            video_path,
            outputs_dir,
            logger,
            primary_tracks=args.primary_tracks,
            model_path=args.model,
            num_poses=args.num_poses,
            crop_refine=args.crop_refine,
        )
        overlay_result = render_overlay(video_path, outputs_dir, logger)
        result["outputs"]["pose_json"] = _relative_to(outputs_dir, pose_result["pose_path"])
        result["outputs"]["pose_raw_json"] = _relative_to(outputs_dir, pose_result["pose_raw_path"])
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
        result["pose_status"] = pose_result["pose_status"]
        result["overlay_status"] = overlay_result["overlay_status"]
        result["pose_metrics"] = pose_result.get("pose_metrics", {})
        result["tracking_metrics"] = pose_result.get("tracking_metrics", {})
        result["raw_detections_per_frame_avg"] = pose_result.get("raw_detections_per_frame_avg", 0.0)
        result["primary_track_ids"] = pose_result.get("primary_track_ids", [])
        result["primary_track_count"] = pose_result.get("primary_track_count", args.primary_tracks)
        result["pose_frames_with_detections"] = pose_result.get("pose_frames_with_detections", 0)
        result["overlay_bytes"] = overlay_result.get("overlay_bytes", 0)

        write_result_ok(result)
        exit_code = 0
        logger.info("Analysis completed successfully.")
    except KnownError as exc:
        stack = traceback.format_exc()
        write_result_error(result, exc.code, exc.message, exc.hint)
        result["error"]["traceback"] = stack
        result["error_code"] = exc.code
        result["message"] = exc.message
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
        result["error"]["traceback"] = stack
        result["error_code"] = "E_UNEXPECTED"
        result["message"] = "Unexpected engine crash."
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


def _peek_arg_value(argv: list[str], name: str) -> str | None:
    prefix = f"{name}="
    for idx, arg in enumerate(argv):
        if arg == name and idx + 1 < len(argv):
            return argv[idx + 1]
        if arg.startswith(prefix):
            return arg.split("=", 1)[1]
    return None


def _build_base_result(run_id: str, outputs_dir: Path, logs_dir: Path) -> dict:
    return {
        "status": ResultStatus.ERROR,
        "run_id": run_id,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "version": read_version(),
        "inputs": {
            "run_id": run_id,
        },
        "outputs": {
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


def _write_error_contract(result: dict, outputs_dir: Path, logger: logging.Logger) -> None:
    result["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    safe_write_json(outputs_dir / "result.json", result)
    if result.get("error"):
        safe_write_json(outputs_dir / "error.json", result["error"])
    _flush_logger(logger)


def main() -> int:
    argv = sys.argv[1:]
    run_id = _peek_arg_value(argv, "--run-id") or uuid.uuid4().hex
    outdir = _peek_arg_value(argv, "--outdir")
    run_paths, outputs_dir, logs_dir = resolve_outputs_logs(run_id, SimpleNamespace(outdir=outdir))
    engine_log = logs_dir / "engine.log"
    engine_log.touch(exist_ok=True)
    logger = setup_logging(engine_log)

    parser = argparse.ArgumentParser(description="Fighting Overlay Engine", exit_on_error=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a video")
    analyze_parser.add_argument("--video", required=True)
    analyze_parser.add_argument("--run-id", required=False)
    analyze_parser.add_argument("--outdir", required=False)
    analyze_parser.add_argument("--model", required=False)
    analyze_parser.add_argument("--primary-tracks", type=int, default=2)
    analyze_parser.add_argument("--num-poses", type=int, default=4)
    analyze_parser.add_argument(
        "--crop-refine",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable crop refinement for small detections.",
    )

    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as exc:
        message = str(exc)
        stack = traceback.format_exc()
        result = _build_base_result(run_id, outputs_dir, logs_dir)
        write_result_error(result, "E_ARGPARSE", "Invalid arguments.", message)
        result["error"]["traceback"] = stack
        result["error_code"] = "E_ARGPARSE"
        result["message"] = "Invalid arguments."
        logger.error("Argparse failure: %s", message)
        _write_error_contract(result, outputs_dir, logger)
        return 2
    except SystemExit as exc:
        message = str(exc)
        stack = traceback.format_exc()
        result = _build_base_result(run_id, outputs_dir, logs_dir)
        write_result_error(result, "E_ARGPARSE", "Invalid arguments.", message)
        result["error"]["traceback"] = stack
        result["error_code"] = "E_ARGPARSE"
        result["message"] = "Invalid arguments."
        logger.error("Argparse exit: %s", message)
        _write_error_contract(result, outputs_dir, logger)
        return 2

    if not args.run_id:
        args.run_id = run_id

    if args.command == "analyze":
        return analyze(args)
    result = _build_base_result(run_id, outputs_dir, logs_dir)
    write_result_error(result, "E_COMMAND", "Unknown command.", f"Unknown command: {args.command}")
    result["error"]["traceback"] = ""
    result["error_code"] = "E_COMMAND"
    result["message"] = "Unknown command."
    logger.error("Unknown command: %s", args.command)
    _write_error_contract(result, outputs_dir, logger)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
