# Failure Log

Track recurring failures and mitigations to avoid regressions.

## 2025-02-14
- **Symptom:** Launcher does nothing / window doesn’t open.
- **Root cause:** Startup exited during `EnsureInstalled` relaunch path (junction/delete/relaunch failures could throw or fail silently).
- **Fix:** Make install/relaunch non-fatal, log errors, show GUI even when relaunch fails.
- **Prevention:** Guard startup/installer paths with logging and fall back to in-place execution.
