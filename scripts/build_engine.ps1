$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$specPath = Join-Path $repoRoot "engine/pyinstaller.spec"

& python -m pyinstaller --noconfirm $specPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$modelSource = Join-Path $repoRoot "engine/models"
$modelTarget = Join-Path $repoRoot "dist/engine/models"
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
$modelFiles = Get-ChildItem -Path $modelSource -Filter "*.task" -ErrorAction SilentlyContinue
if (-not $modelFiles) {
    Write-Error "No pose models found in $modelSource"
    exit 1
}
Copy-Item -Force $modelFiles $modelTarget

function Write-EngineListings {
    $engineRoot = Join-Path $repoRoot "dist/engine"
    $modelRoot = Join-Path $engineRoot "models"
    Write-Host "dist/engine listing:"
    Get-ChildItem -Path $engineRoot -ErrorAction SilentlyContinue | Format-Table | Out-String | Write-Host
    Write-Host "dist/engine/models listing:"
    Get-ChildItem -Path $modelRoot -ErrorAction SilentlyContinue | Format-Table | Out-String | Write-Host
}

$engineExe = Join-Path $repoRoot "dist/engine/engine.exe"
if (-not (Test-Path $engineExe)) {
    Write-Error "Engine executable not found at $engineExe"
    Write-EngineListings
    exit 1
}

$mediapipeDir = Join-Path $repoRoot "dist/engine/mediapipe"
if (-not (Test-Path $mediapipeDir)) {
    Write-Error "Mediapipe assets missing at $mediapipeDir"
    Write-EngineListings
    exit 1
}

$ffmpegCandidates = Get-ChildItem -Path (Join-Path $repoRoot "dist/engine") -Recurse -Filter "*ffmpeg*.exe" -ErrorAction SilentlyContinue
if (-not $ffmpegCandidates) {
    Write-Error "imageio_ffmpeg binaries not found under dist/engine"
    Write-EngineListings
    exit 1
}

$modelPath = Join-Path $modelTarget "pose_landmarker_full.task"
if (-not (Test-Path $modelPath)) {
    Write-Error "pose_landmarker_full.task missing at $modelPath"
    Write-EngineListings
    exit 1
}
