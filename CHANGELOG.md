# Changelog

## [0.0.12] - 2026-11-20

### Fixed

- Prevent chat rows from being dropped at batch boundaries.
- Restart chat reading when the configured log file changes, retry file errors, and continue past malformed chat rows.
- Stop the chat reader cleanly and process queued rows before saving on shutdown.
- Keep the selected chat log path when the file chooser is cancelled.

### Changed

- Use a bounded, thread-safe queue for chat rows and show reader errors in the status bar.
- Remove the unused `tailer` and `win-unicode-console` dependencies.
