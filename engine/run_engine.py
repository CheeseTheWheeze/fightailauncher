import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.storage_paths import (  # noqa: E402
    ensure_clip_dirs,
    ensure_global_dirs,
    get_clip_paths,
    get_global_paths,
)

from engine.pose import extract_pose  # noqa: E402
from engine.overlay import render_overlay  # noqa: E402


class EngineError(Exception):
    def __init__(self, message, hints=None, exit_code=2):
        super().__init__(message)
        self.message = message
        self.hints = hints or []
        self.exit_code = exit_code


def setup_logging(global_log: Path, clip_log: Path):
    logger = logging.getLogger("engine")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    global_handler = logging.FileHandler(global_log)
    global_handler.setFormatter(formatter)

    clip_handler = logging.FileHandler(clip_log)
    clip_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(global_handler)
    logger.addHandler(clip_handler)
    return logger


def write_error(outputs_dir: Path, message: str, exc: Exception, hints=None):
    error_path = outputs_dir / "error.json"
    error_payload = {
        "message": message,
        "exception": repr(exc),
        "stack": getattr(exc, "__traceback__", None) and "see logs",
        "hints": hints or [],
    }
    error_path.write_text(json.dumps(error_payload, indent=2))


def analyze(args: argparse.Namespace) -> int:
    started = time.time()
    clip_paths = get_clip_paths(args.athlete, args.clip)
    global_paths = get_global_paths()
    ensure_clip_dirs(clip_paths)
    ensure_global_dirs(global_paths)

    outputs_dir = Path(args.outdir) if args.outdir else clip_paths.outputs_dir
    outputs_dir.mkdir(parents=True, exist_ok=True)

    logs_dir = clip_paths.logs_dir
    if args.outdir:
        logs_dir = Path(args.outdir).parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(
        global_paths.logs_dir / "engine.log",
        logs_dir / "engine.log",
    )

    logger.info("Starting analysis for athlete=%s clip=%s", args.athlete, args.clip)

    video_path = Path(args.video)
    if not video_path.exists():
        raise EngineError("Video file does not exist.", [str(video_path)])

    input_copy = clip_paths.input_dir / video_path.name
    if input_copy.resolve() != video_path.resolve():
        shutil.copyfile(video_path, input_copy)

    pose_result = extract_pose(video_path, outputs_dir, logger)
    overlay_result = render_overlay(video_path, outputs_dir, logger)

    result = {
        "status": "ok",
        "athlete_id": args.athlete,
        "clip_id": args.clip,
        "video": str(video_path),
        "outputs": {
            "pose": pose_result["pose_path"],
            "overlay": overlay_result["overlay_path"],
        },
        "timings_ms": {
            "total": int((time.time() - started) * 1000),
            "pose": pose_result["pose_duration_ms"],
        },
        "details": {
            "pose_status": pose_result["pose_status"],
            "overlay_status": overlay_result["overlay_status"],
        },
    }

    (outputs_dir / "result.json").write_text(json.dumps(result, indent=2))
    logger.info("Analysis completed successfully.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fighting Overlay Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a video")
    analyze_parser.add_argument("--video", required=True)
    analyze_parser.add_argument("--athlete", required=True)
    analyze_parser.add_argument("--clip", required=True)
    analyze_parser.add_argument("--outdir", required=False)
    analyze_parser.add_argument("--model", required=False)

    args = parser.parse_args()

    try:
        if args.command == "analyze":
            return analyze(args)
        raise EngineError("Unknown command.")
    except EngineError as exc:
        clip_paths = get_clip_paths(args.athlete, args.clip)
        ensure_clip_dirs(clip_paths)
        outputs_dir = Path(args.outdir) if args.outdir else clip_paths.outputs_dir
        outputs_dir.mkdir(parents=True, exist_ok=True)
        global_paths = get_global_paths()
        ensure_global_dirs(global_paths)
        logs_dir = clip_paths.logs_dir
        if args.outdir:
            logs_dir = Path(args.outdir).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        logger = setup_logging(
            global_paths.logs_dir / "engine.log",
            logs_dir / "engine.log",
        )
        logger.error("Handled error: %s", exc.message)
        write_error(outputs_dir, exc.message, exc, exc.hints)
        return exc.exit_code
    except Exception as exc:  # unexpected
        clip_paths = get_clip_paths(args.athlete, args.clip)
        ensure_clip_dirs(clip_paths)
        outputs_dir = Path(args.outdir) if args.outdir else clip_paths.outputs_dir
        outputs_dir.mkdir(parents=True, exist_ok=True)
        global_paths = get_global_paths()
        ensure_global_dirs(global_paths)
        logs_dir = clip_paths.logs_dir
        if args.outdir:
            logs_dir = Path(args.outdir).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        logger = setup_logging(
            global_paths.logs_dir / "engine.log",
            logs_dir / "engine.log",
        )
        logger.exception("Unexpected error")
        write_error(outputs_dir, "Unexpected error", exc, ["Check engine.log"])
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
