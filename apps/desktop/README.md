# Fighting Overlay Desktop

## Run (Development)
```powershell
# From repo root
scripts\dev_run.ps1
```

## Build
```powershell
dotnet build apps\desktop\FightingOverlay.Desktop.csproj -c Release
```

## Notes
- The UI launches the engine via `FIGHTING_OVERLAY_ENGINE_PATH`.
- Logs are written to `%LOCALAPPDATA%\FightingOverlay\data\logs\desktop.log`.
