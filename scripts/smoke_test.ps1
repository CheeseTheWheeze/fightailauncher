param(
    [string]$EnginePath,
    [string]$ModelPath,
    [string]$OutputRoot,
    [switch]$KeepTemp
)

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EnginePath) {
    $EnginePath = Join-Path $repoRoot "dist\engine\engine.exe"
}

if (-not (Test-Path $EnginePath)) {
    Write-Error "Engine executable not found at $EnginePath"
    exit 1
}

$baseRoot = if ($OutputRoot) { $OutputRoot } else { $env:TEMP }
if ($OutputRoot -and -not (Test-Path $baseRoot)) {
    New-Item -ItemType Directory -Force -Path $baseRoot | Out-Null
}
$tempRoot = Join-Path $baseRoot ("fight-overlay-smoke-" + [Guid]::NewGuid().ToString("N"))
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

    $runId = "smoke-run"
    $runRoot = Join-Path $tempRoot "run"
    $outputDir = Join-Path $runRoot "outputs"
    $logDir = Join-Path $runRoot "logs"
    if (-not $ModelPath) {
        $ModelPath = Join-Path (Split-Path $EnginePath -Parent) "models" "pose_landmarker_full.task"
    }
    $modelPath = $ModelPath
    if (-not (Test-Path $modelPath)) {
        Write-Error "Model not found at $modelPath"
        exit 1
    }

    $resultJson = Join-Path $outputDir "result.json"
    $engineLog = Join-Path $logDir "engine.log"
    & $EnginePath analyze --video $videoPath --run-id $runId --outdir $runRoot --model $modelPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Engine exited with non-zero."
        exit 1
    }

    if (-not (Test-Path $resultJson)) {
        Write-Error "result.json missing"
        exit 1
    }
    if (-not (Test-Path $engineLog)) {
        Write-Error "engine.log missing"
        exit 1
    }

    $payload = Get-Content $resultJson -Raw | ConvertFrom-Json
    Write-Host ("result.json status: {0}" -f $payload.status)
    Write-Host ("result.json overlay.status: {0}" -f $payload.overlay.status)
    if ($payload.overlay.bytes -ne $null) {
        Write-Host ("result.json overlay.bytes: {0}" -f $payload.overlay.bytes)
    }
    if ($payload.pose_extraction) {
        Write-Host ("result.json pose_extraction.status: {0}" -f $payload.pose_extraction.status)
        Write-Host ("result.json pose_extraction.frames_with_detections: {0}" -f $payload.pose_extraction.frames_with_detections)
    }
    if ($payload.status -ne "ok") {
        Write-Error "result.json status not ok"
        exit 1
    }
    if ($payload.overlay.status -ne "ok") {
        Write-Error "result.json overlay status not ok"
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

    $poseJson = Join-Path $outputDir "pose.json"
    if (-not (Test-Path $poseJson)) {
        Write-Error "pose.json missing"
        exit 1
    }
    $poseRawJson = Join-Path $outputDir "pose_raw.json"
    if (-not (Test-Path $poseRawJson)) {
        Write-Error "pose_raw.json missing"
        exit 1
    }

    $posePayload = Get-Content $poseJson -Raw | ConvertFrom-Json
    if (-not $posePayload.frames -or $posePayload.frames.Count -eq 0) {
        Write-Error "pose.json frames empty"
        exit 1
    }
    Write-Host ("pose.json frame count: {0}" -f $posePayload.frames.Count)

    $negativeRunId = "smoke-run-missing"
    $negativeRunRoot = Join-Path $tempRoot "run-missing"
    $negativeOutputDir = Join-Path $negativeRunRoot "outputs"
    $negativeLogDir = Join-Path $negativeRunRoot "logs"
    $missingVideo = Join-Path $tempRoot "does-not-exist.mp4"

    & $EnginePath analyze --video $missingVideo --run-id $negativeRunId --outdir $negativeRunRoot --model $modelPath
    if ($LASTEXITCODE -ne 2) {
        Write-Error "Engine missing-video run exited with $LASTEXITCODE (expected 2)."
        exit 1
    }

    $negativeResult = Join-Path $negativeOutputDir "result.json"
    if (-not (Test-Path $negativeResult)) {
        Write-Error "result.json missing for negative test"
        exit 1
    }
    $negativeLog = Join-Path $negativeLogDir "engine.log"
    if (-not (Test-Path $negativeLog)) {
        Write-Error "engine.log missing for negative test"
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

    $argFailRunRoot = Join-Path $tempRoot "run-argfail"
    $argFailOutputDir = Join-Path $argFailRunRoot "outputs"
    $argFailLogDir = Join-Path $argFailRunRoot "logs"
    & $EnginePath analyze --video $videoPath --run-id "argfail" --outdir $argFailRunRoot --bad-flag
    if ($LASTEXITCODE -ne 2) {
        Write-Error "Engine invalid-arg run exited with $LASTEXITCODE (expected 2)."
        exit 1
    }

    $argFailResult = Join-Path $argFailOutputDir "result.json"
    $argFailLog = Join-Path $argFailLogDir "engine.log"
    if (-not (Test-Path $argFailResult)) {
        Write-Error "result.json missing for invalid-arg test"
        exit 1
    }
    if (-not (Test-Path $argFailLog)) {
        Write-Error "engine.log missing for invalid-arg test"
        exit 1
    }

    $versionOutput = & $EnginePath version
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Engine version command exited with $LASTEXITCODE"
        exit 1
    }
    if (-not $versionOutput) {
        Write-Error "Engine version command returned empty output"
        exit 1
    }

    Write-Host "Smoke test passed."
    exit 0
} finally {
    if ($KeepTemp) {
        Write-Host "Preserving smoke test artifacts at $tempRoot"
    } else {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $tempRoot
    }
}
