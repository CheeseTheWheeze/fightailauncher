param(
    [string]$ExePath
)

if (-not $ExePath) {
    $candidate = Join-Path $PSScriptRoot "..\apps\desktop\bin\Release\net8.0-windows\FightAILauncher.exe"
    $resolved = Resolve-Path $candidate -ErrorAction SilentlyContinue
    if ($resolved) {
        $ExePath = $resolved.Path
    }
}

if (-not $ExePath -or -not (Test-Path $ExePath)) {
    Write-Error "Executable not found. Provide -ExePath to the built desktop exe."
    exit 1
}

$process = Start-Process -FilePath $ExePath -PassThru
Start-Sleep -Seconds 3
$process.Refresh()

if ($process.HasExited) {
    Write-Error "Launcher exited before showing a window."
    exit 1
}

$process.WaitForInputIdle(1000) | Out-Null
$process.Refresh()

if ($process.MainWindowHandle -eq 0) {
    Write-Error "Launcher process is running but no visible window was detected."
    try {
        $process.CloseMainWindow() | Out-Null
        Start-Sleep -Seconds 1
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
        }
    }
    catch {
        Stop-Process -Id $process.Id -Force
    }
    exit 1
}

Write-Host "Launcher smoke test passed."
try {
    $process.CloseMainWindow() | Out-Null
}
catch {
}
