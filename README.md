# Fighting Overlay Launcher

## Overview
This repo contains a Windows-only desktop UI and a Python engine for local-first fighting overlay analysis.

## Layout
```
apps/desktop/   # WPF desktop UI
engine/         # Python engine CLI
shared/         # Shared schemas/version
scripts/        # Dev scripts
```

## Local Run (Development)
```powershell
scripts\dev_run.ps1
```

## Engine CLI
```powershell
python engine\run_engine.py analyze --video "C:\path\video.mp4" --athlete "athlete_id" --clip "clip_id"
```

## Logs & Storage
Data is stored under `%LOCALAPPDATA%\FightingOverlay\data`.
