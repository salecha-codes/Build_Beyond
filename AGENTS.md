# Project collaboration

The user explicitly requests multiple subagents for this project and future tasks. Delegate independent work with clear file ownership, and integrate the results in the parent agent. Preserve concurrent edits and coordinate shared files.

The app targets offline use on budget Android phones. Keep inference, saved observations and bundled speech on the device; do not introduce a required cloud API or server database. Preserve real model outputs and the unvalidated-diagnosis gate.

The user prefers to do the final interactive testing. Complete the build and asset-integrity checks needed for a reviewable handoff, and avoid lengthy full test/emulator runs unless requested or needed to resolve a failure.

Source lives in `android`, `frontend`, `backend`, `models`, `database`, `content`, and `ml`. Model checkpoints for speech generation are build-time tools outside the repository; ship their audio outputs only.

GitHub updates and the generated `gh-pages` branch were authorized. Keep pushes sequential: this environment's Git transport has failed when two pushes to the same repository overlapped. Do not force-push or change repository visibility.
