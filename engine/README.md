# Fighting Overlay Engine

## Overview
The engine is a Python CLI responsible for pose extraction, overlay rendering, and writing deterministic outputs.

## CLI
```bash
engine.exe analyze \
  --video "C:\path\video.mp4" \
  --athlete "athlete_id" \
  --clip "clip_id" \
  --outdir "C:\path\outputs"
```

```bash
python engine/run_engine.py analyze \
  --video "C:\path\video.mp4" \
  --athlete "athlete_id" \
  --clip "clip_id" \
  --outdir "C:\path\outputs"
```

### Exit Codes
- `0` Success
- `2` Expected failure with `error.json`
- `3` Unexpected crash with `error.json`

## Outputs
```
outputs/
  pose.json
  overlay.mp4
  result.json
  error.json (on failure)
logs/
  engine.log
```

## Dependencies
- OpenCV (bundled in engine.exe)
- FFmpeg (bundled in engine.exe via imageio-ffmpeg)
- MediaPipe (optional)

If optional dependencies are missing, the engine produces stub outputs so UI flow remains testable.
