$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$enginePath = Join-Path $repoRoot "engine\dist\engine\engine.exe"
if (-not (Test-Path $enginePath)) {
    Write-Error "engine.exe not found. Run pyinstaller to build engine/engine.exe first."
    exit 1
}
$env:FIGHTING_OVERLAY_ENGINE_PATH = $enginePath

dotnet run --project (Join-Path $repoRoot "apps\desktop\FightingOverlay.Desktop.csproj")
