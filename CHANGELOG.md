# Changelog

## [0.0.13] - 2026-11-23

### Added

- Add Mayhem MF amplifiers, RDI Energy Amplifier Gamma variants, and Omegaton C-120 BGH variants to the loadout data.

### Fixed

- Recognize whole-number PED values in loot messages.
- Correct the Mayhem MF-Amplifier Alpha name while preserving existing loadouts.
- Preserve loot messages written to the chat log in multiple pieces.
- Avoid counting old combat log entries as new run costs.
- Load wrapped and flat JSON game data from the source and packaged asset locations.
- Report the original startup import error instead of masking it with a `Config` error.
- Bundle the game data files in the executable build.

## [0.0.12] - 2026-11-20

### Fixed

- Prevent chat rows from being dropped at batch boundaries.
- Restart chat reading when the configured log file changes, retry file errors, and continue past malformed chat rows.
- Stop the chat reader cleanly and process queued rows before saving on shutdown.
- Keep the selected chat log path when the file chooser is cancelled.

### Changed

- Use a bounded, thread-safe queue for chat rows and show reader errors in the status bar.
- Remove the unused `tailer` and `win-unicode-console` dependencies.
