$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$enginePath = Join-Path $repoRoot "engine\run_engine.py"
$env:FIGHTING_OVERLAY_ENGINE_PATH = $enginePath

dotnet run --project (Join-Path $repoRoot "apps\desktop\FightingOverlay.Desktop.csproj")
