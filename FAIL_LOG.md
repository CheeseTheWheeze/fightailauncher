# Failure Log

Track recurring failures and mitigations to avoid regressions.

## 2025-02-14
- **Symptom:** Launcher does nothing / window doesn’t open.
- **Root cause:** Startup exited during `EnsureInstalled` relaunch path (junction/delete/relaunch failures could throw or fail silently).
- **Fix:** Make install/relaunch non-fatal, log errors, show GUI even when relaunch fails.
- **Prevention:** Guard startup/installer paths with logging and fall back to in-place execution.

## 2025-02-16
- **Symptom:** mklink exited with code 1; launcher opens but warns.
- **Root cause:** Install detection used `BaseDirectory`; junction removal was non-deterministic; mklink stderr was not logged.
- **Fix:** Use `MainModule` exe path, deterministic rmdir/rename, capture mklink stdout/stderr, install_failed marker backoff.
- **Prevention:** Never use `BaseDirectory` for install path; always log mklink stdout/stderr; back off on repeated failures.

## 2025-02-18
- **Symptom:** Overlay contained no skeleton.
- **Root cause:** Overlay renderer copied video; pose extractor defaulted to stub output when MediaPipe was missing.
- **Fix:** Implement real MediaPipe pose extraction, draw skeleton overlays, and fail loudly if MediaPipe is missing.
- **Prevention:** Keep pose extraction as required dependency and ensure overlay renderer always draws joints/bones.

## 2025-02-20
- **Symptom:** Overlay rendered but showed no skeleton.
- **Root cause:** MediaPipe was not bundled into the engine build and overlay generation reused the input frames.
- **Fix:** Bundle MediaPipe, implement MediaPipe pose extraction, and draw skeleton landmarks/bones in overlay output.
- **Prevention:** Smoke test asserts pose landmarks are present and overlay_status is ok.

## 2025-02-24
- **Symptom:** Only one skeleton, limb confusion between two athletes, skeleton disappears when far away.
- **Root cause:** Single-person pose + no per-person tracking; wide shots reduce detection.
- **Fix:** Multi-pose landmarker + per-person tracking IDs + size gating + crop-and-rescale for small subjects.
- **Prevention:** Metrics per track; require two primary tracks when two large subjects present.

## 2026-01-02
- **Symptom:** Windows CI failed with “Model directory missing” / `E_MODEL_MISSING`.
- **Root cause:** Pose landmarker model was not copied into `dist/engine/models`, so the packaged engine could not resolve the model.
- **Fix:** Bundle the pose landmarker model under `engine/models`, copy it into `dist/engine/models` during packaging, and pass the model path in smoke tests.
- **Prevention:** Workflow verifies `.task` models exist and smoke tests enforce result/log outputs for invalid args.

## 2026-01-05
- **Symptom:** Windows CI intermittently failed during build/package; release zips missing engine assets or used the wrong publish path.
- **Root cause:** LFS model files were sometimes checked out as pointer text, and packaging depended on SDK-version-specific publish paths.
- **Fix:** Enable LFS + full git history in CI, validate `pose_landmarker_full.task` is a real binary, and publish desktop output to `dist/desktop_publish`.
- **Prevention:** Add explicit engine/desktop/package assertions, validate release layout before zipping, and always upload diagnostics artifacts.
