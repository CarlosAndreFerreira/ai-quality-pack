# Changelog

## 0.4.2 — 2026-11-08
Pre-publication security and edge-case review.
- **Gate cache now covers `gate.json`.** Editing the gate commands after a pass used to report "workspace unchanged — skipped" without running the new commands.
- **Stop hook fails closed on timeout.** A gate that exceeded the hook's fixed 1800 s let the agent finish silently; the budget is now sized from `gate.json` and a timeout blocks the stop.
- **Hooks run from the project root** (`CLAUDE_PROJECT_DIR`). Started from a subfolder, the Stop hook found no gate and let the agent stop.
- **Formatter no longer syncs the project on every edit** (`uv run --no-sync`), and falls back to `ruff` on PATH when the project doesn't pin it.
- Installer leaves a `settings.json` with an unexpected shape untouched instead of crashing.
- CI lints the README as English (it was linted with the Portuguese rules and passed vacuously).
- 3 regression tests, each verified to fail without its fix.

## 0.4.1 — 2026-11-07
- Native Google Antigravity plugin support in `install.py global` (`~/.gemini/config/plugins/ai-quality-pack/` with `plugin.json`, `agents/evaluator.md`, `rules/AGENTS.md`, and `assets/logo.svg`).
- Added `rust` language profile (`Cargo.toml` auto-detection, `cargo fmt`, `cargo clippy`, `cargo test` gates).
- Union-merge-safe `features.jsonl` event log alongside `features.json`.
- Fixed `install_egm()` fallback and `EgmTests` PATH isolation when broken/stub CLIs are present in `/usr/bin`.

## 0.4.0 — 2026-11-07
- `skill-eval`: A/B, A/A noise calibration, ablation, holdout split, non-compensatory guards, leakage critic, reward-hacking guard, history (RRSI, GEPA/gskill, Prime Agent).
- Completion gate (`memory.py gate`) with change detection + opt-in Claude Code Stop hook; stuck detection after 3 evaluator failures.
- `plan-before-code` routes large changes to Google's Elephant-Goldfish Model (`--with-egm`).
- New `ui-ux-review` skill.
- Security: upstream skills pinned to a reviewed SHA; memory digest sanitised and delimited; Windows-safe quoting; task-id collision warnings.

## 0.3.0
- Evaluator skill + subagent; tasks with IDs, notes, links, worktrees; ACE-style playbook; OWASP 2025 mapping; language profiles; cross-platform installer; tests + CI.

## 0.2.0
- Long-horizon memory, lessons, skill-evolve proposals, upstream grill-me.

## 0.1.0
- Base skills, AGENTS.md template, ruff/pyright/pytest gates, STE linter.
