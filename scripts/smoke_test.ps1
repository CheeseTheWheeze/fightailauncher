param(
    [string]$EnginePath
)

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnginePath) {
    $EnginePath = Join-Path $repoRoot "dist\engine\engine.exe"
}

if (-not (Test-Path $EnginePath)) {
    Write-Error "Engine executable not found at $EnginePath"
    exit 1
}

$tempRoot = Join-Path $env:TEMP ("fight-overlay-smoke-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

try {
    $videoPath = Join-Path $tempRoot "test.mp4"
    Write-Host "Generating test video at: $videoPath"
    python (Join-Path $repoRoot "scripts\generate_test_video.py") --output $videoPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "generate_test_video.py failed with exit code $LASTEXITCODE"
        exit 1
    }

    if (-not (Test-Path $videoPath)) {
        Write-Error "Test video not found at $videoPath"
        exit 1
    }

    if ((Get-Item $videoPath).Length -le 0) {
        Write-Error "Test video is empty at $videoPath"
        exit 1
    }

    $athleteId = "smoke-athlete"
    $clipId = "smoke-clip"
    $outputDir = Join-Path $tempRoot "outputs"

    $resultJson = Join-Path $outputDir "result.json"
    & $EnginePath analyze --video $videoPath --athlete $athleteId --clip $clipId --outdir $outputDir
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Engine exited with non-zero."
        exit 1
    }

    if (-not (Test-Path $resultJson)) {
        Write-Error "result.json missing"
        exit 1
    }

    $payload = Get-Content $resultJson -Raw | ConvertFrom-Json
    if ($payload.status -ne "ok") {
        Write-Error "result.json status not ok"
        exit 1
    }

    $overlay = Join-Path $outputDir "overlay.mp4"
    if (-not (Test-Path $overlay)) {
        Write-Error "overlay.mp4 missing"
        exit 1
    }

    if ((Get-Item $overlay).Length -le 0) {
        Write-Error "overlay.mp4 empty"
        exit 1
    }

    $negativeClipId = "smoke-clip-missing"
    $negativeOutputDir = Join-Path $tempRoot "outputs-missing"
    $missingVideo = Join-Path $tempRoot "does-not-exist.mp4"

    & $EnginePath analyze --video $missingVideo --athlete $athleteId --clip $negativeClipId --outdir $negativeOutputDir
    if ($LASTEXITCODE -ne 2) {
        Write-Error "Engine missing-video run exited with $LASTEXITCODE (expected 2)."
        exit 1
    }

    $negativeResult = Join-Path $negativeOutputDir "result.json"
    if (-not (Test-Path $negativeResult)) {
        Write-Error "result.json missing for negative test"
        exit 1
    }

    $negativePayload = Get-Content $negativeResult -Raw | ConvertFrom-Json
    if ($negativePayload.status -ne "error") {
        Write-Error "negative result.json status not error"
        exit 1
    }

    if ($negativePayload.error.code -ne "E_VIDEO_MISSING") {
        Write-Error "negative result.json error.code not E_VIDEO_MISSING"
        exit 1
    }

    Write-Host "Smoke test passed."
    exit 0
} finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $tempRoot
}
