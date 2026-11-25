---
description: Print the pull request evidence block and deterministic verdict for the current change
---
Generate the verification evidence for the current code state.

1. Run `aqp-memory evidence --brief` (or `aqp-memory evidence` for the full report) and `aqp-memory verdict` (if `aqp-memory` is not on PATH, use `python3 .agents/skills/long-horizon/scripts/memory.py`).
2. Print the evidence block and the verdict (`SUPPORTED` or `UNKNOWN`, with the reason) without altering the recorded status.
3. Highlight any items listed under `Not verified` or any `HIGH` review risk.
