---
description: Initialize AI Quality Pack memory and propose .agent-memory/gate.json for this project (a person puts it in place)
---
Set up the AI Quality Pack in the current repository.

1. Run `aqp-memory init` (if `aqp-memory` is not on PATH, run `python3 .agents/skills/long-horizon/scripts/memory.py init`).
2. Check if `.agent-memory/gate.json` already exists. If it does, do not change it: go to step 6.
3. Detect the project stack from root files and choose the matching commands:
   - Python (`pyproject.toml`, `requirements.txt`, `setup.py`, `uv.lock`): `["uv run ruff check .", "uv run pyright", "uv run pytest -q"]` (or the project's actual test/lint runner).
   - TypeScript (`package.json`, `tsconfig.json`): `["npx eslint . --max-warnings=0", "npx tsc --noEmit", "npm test --silent"]`.
   - Go (`go.mod`): `["go vet ./...", "go test ./..."]`.
   - Rust (`Cargo.toml`): `["cargo fmt --all -- --check", "cargo clippy --workspace --all-targets -- -D warnings", "cargo test --workspace"]`.
   - Use `{"commands": [...], "max_output": 3000, "timeout": 900, "max_changed_lines": 400}`.
4. Write the result to `.agent-memory/gate.proposed.json`. Do not write `.agent-memory/gate.json` yourself, with a file tool or with a shell command: the gate file is one of the files that check your work, and the guard hook blocks you. A person puts it in place.
5. Show the content of `.agent-memory/gate.proposed.json` to the user. Ask them to review it and to run this command themselves (in Claude Code, a line that starts with `!`):
   `mv .agent-memory/gate.proposed.json .agent-memory/gate.json`
   Then stop and wait for the user.
6. When `.agent-memory/gate.json` exists, run `aqp-memory doctor` to verify that the commands exist on PATH. Ask the user to commit the file.
