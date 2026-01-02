$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$specPath = Join-Path $repoRoot "engine/pyinstaller.spec"

pyinstaller --noconfirm $specPath
