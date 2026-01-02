import argparse
import subprocess
import sys
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe


def generate_video(path: Path, width: int, height: int, fps: int, seconds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:d={seconds}:r={fps}",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write("ffmpeg failed to generate test video.\n")
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a tiny MP4 for smoke tests.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--seconds", type=int, default=1)
    args = parser.parse_args()

    generate_video(
        Path(args.output),
        width=args.width,
        height=args.height,
        fps=args.fps,
        seconds=args.seconds,
    )


if __name__ == "__main__":
    main()
