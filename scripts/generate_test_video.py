import argparse
from pathlib import Path

import cv2
import numpy as np


def generate_video(path: Path, width: int, height: int, fps: int, seconds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    frame_count = fps * seconds
    for i in range(frame_count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            f"Frame {i}",
            (10, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )
        writer.write(frame)
    writer.release()


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
