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
