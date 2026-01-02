import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    engine_exe = repo_root / "dist" / "engine" / "engine.exe"
    engine_py = repo_root / "engine" / "run_engine.py"
    sample_dir = Path(tempfile.mkdtemp(prefix="fight-overlay-smoke-"))
    try:
        video_path = sample_dir / "sample.mp4"
        video_path.write_bytes(b"FAKE-MP4")

        athlete_id = "smoke-athlete"
        clip_id = "smoke-clip"
        output_dir = sample_dir / "outputs"

        command = [
            "analyze",
            "--video",
            str(video_path),
            "--athlete",
            athlete_id,
            "--clip",
            clip_id,
            "--outdir",
            str(output_dir),
        ]
        if engine_exe.exists():
            args = [str(engine_exe)] + command
        else:
            args = [sys.executable, str(engine_py)] + command
        result = subprocess.run(args, capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr, file=sys.stderr)

        if result.returncode != 0:
            print("Engine exited with non-zero.")
            return 1

        overlay = output_dir / "overlay.mp4"
        result_json = output_dir / "result.json"
        if not overlay.exists() or overlay.stat().st_size == 0:
            print("overlay.mp4 missing or empty")
            return 1
        if not result_json.exists():
            print("result.json missing")
            return 1
        payload = json.loads(result_json.read_text())
        if payload.get("status") != "ok":
            print("result.json status not ok")
            return 1
        print("Smoke test passed")
        return 0
    finally:
        shutil.rmtree(sample_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
