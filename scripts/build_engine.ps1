$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$specPath = Join-Path $repoRoot "engine/pyinstaller.spec"

pyinstaller --noconfirm $specPath

$modelSource = Join-Path $repoRoot "engine/models"
$modelTarget = Join-Path $repoRoot "dist/engine/models"
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
$modelFiles = Get-ChildItem -Path $modelSource -Filter "*.task" -ErrorAction SilentlyContinue
if (-not $modelFiles) {
    Write-Error "No pose models found in $modelSource"
    exit 1
}
Copy-Item -Force $modelFiles $modelTarget
