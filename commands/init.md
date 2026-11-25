---
description: Initialize AI Quality Pack memory and create .agent-memory/gate.json for this project
---
Set up the AI Quality Pack in the current repository.

1. Run `aqp-memory init` (if `aqp-memory` is not on PATH, run `python3 .agents/skills/long-horizon/scripts/memory.py init`).
2. Check if `.agent-memory/gate.json` already exists. Do not overwrite an existing file.
3. If `.agent-memory/gate.json` is missing, detect the project stack from root files and create it with the matching commands:
   - Python (`pyproject.toml`, `requirements.txt`, `setup.py`, `uv.lock`): `["uv run ruff check .", "uv run pyright", "uv run pytest -q"]` (or the project's actual test/lint runner).
   - TypeScript (`package.json`, `tsconfig.json`): `["npx eslint . --max-warnings=0", "npx tsc --noEmit", "npm test --silent"]`.
   - Go (`go.mod`): `["go vet ./...", "go test ./..."]`.
   - Rust (`Cargo.toml`): `["cargo fmt --all -- --check", "cargo clippy --workspace --all-targets -- -D warnings", "cargo test --workspace"]`.
   - Use `{"commands": [...], "max_output": 3000, "timeout": 900, "max_changed_lines": 400}`.
4. Run `aqp-memory doctor` to verify the commands exist on PATH.
5. Show `.agent-memory/gate.json` to the user and ask them to review and commit it.
