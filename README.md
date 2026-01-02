# Fighting Overlay Launcher

## Overview
This repo contains a Windows-only desktop UI and a Python engine for local-first fighting overlay analysis.

## Download & Run (Windows)
1. Download `FightAILauncher-Windows.zip` from the latest GitHub Release.
2. Extract and run `FightAILauncher.exe`.
3. The app self-installs to `%LOCALAPPDATA%\FightingOverlay\app\current\` on first run.

The Update button checks the latest GitHub Release and safely swaps to the new version after restart.

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
engine\dist\engine\engine.exe analyze --video "C:\path\video.mp4" --athlete "athlete_id" --clip "clip_id"
```

```powershell
python engine\run_engine.py analyze --video "C:\path\video.mp4" --athlete "athlete_id" --clip "clip_id"
```

## Logs & Storage
Data is stored under `%LOCALAPPDATA%\FightingOverlay\data`.
The app install root lives under `%LOCALAPPDATA%\FightingOverlay\app\current\` and updates stage in `app\versions`.

## Build Locally
```powershell
# Build engine.exe
pip install -r engine\requirements.txt
pip install pyinstaller
pyinstaller engine\pyinstaller.spec

# Publish desktop app
dotnet publish apps\desktop\FightingOverlay.Desktop.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```
