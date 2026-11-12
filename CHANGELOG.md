# Changelog

## Unreleased — evolution plan, second batch (docs/EVOLUTION.md: E1, E6)
- **The evaluator does not read the author's narrative.** It reads the requirement first and writes what must be true, reads the change with the new `memory.py diff-view` (the comments that the change added are hidden), and treats the recorded criteria as the implementer's reading. Its task is to find defects. The third verdict is `UNKNOWN`, and it does not let a feature pass. Not measured on the benchmark yet.
- **New `criteria` subagent** (read-only tools): writes acceptance criteria from the requirement before the implementation, and asks when the requirement is ambiguous.
- **`install.py --with-ci`**: a GitHub Actions workflow that runs the gate on pull requests with the base branch's `gate.json`, and shows gate warnings as annotations. Actions are pinned by commit.
- `--upgrade` also replaces the pack's subagents (old copy backed up).
- The pack's own CI pins its actions by commit, and runs once per pull request (push runs only on `main`).
- `memory.py` and `skill_eval.py` write UTF-8 to a pipe and never fail on a character that a console cannot show.
- 5 tests.

## Unreleased — evolution plan, first features (docs/EVOLUTION.md: E2, E4, E5, F1)
- **`memory.py repro`**: shows a fix with a test that fails on the base commit and passes on the current code. The base runs in a throw-away git worktree with the test files copied onto it. Results: `verified`, `not-reproduced` (the test passes on the base), `wrong-failure` (`--expect` text missing), `still-failing`, `base-timeout`. `repro --check` is true only for exactly the verified code. Limit: files that git does not track are not in the base checkout.
- **The gate runs the committed `gate.json`.** An edit that is not committed does not count, and the gate reports it. `--ref` or `AGENT_GATE_REF` selects the ref (in CI, the base branch).
- **The gate reports deleted test files and new skip markers** since that ref. It reports them and does not block. The next session digest shows them under "Needs you".
- **`memory.py doctor`**: checks git, memory, `.gitignore`, the hook commands and scripts, and that each gate command can run. It says that hooks do not run in `claude -p --bare`.
- **`skill-eval`**: the report gives the 95% interval of the paired per-task difference and the share of tasks where every run passed (pass^k). New `skill-eval power` gives the number of tasks needed to detect a change.
- 7 tests.

## Unreleased — observability follow-ups
- **A Stop-hook release is `released-green` only when the gate passed for exactly the final code.** The hook looked only for the `.gate-pass` file, so a pass from before the last edit was logged as green. New `memory.py gate --check` runs nothing and exits 0 only for a pass on the current workspace.
- **`memory.py init` no longer joins its new `.gitignore` lines to a last line that has no newline.** `evals/results/` became `evals/results/events.jsonl`, and the results and the run log were no longer ignored.
- 2 tests.

## Unreleased — observability
- **Run log.** `memory.py` and the hooks append to `.agent-memory/events.jsonl` (local, git-ignored): session start, gate pass/fail/skip with duration and the failing command, feature gradings, lesson adds and votes, Stop-hook blocks and releases. Each line has the agent session id (from the SessionStart hook input, or `AGENT_SESSION_ID`). No prompt or code text. `AGENT_MEMORY_EVENTS=0` turns it off; a log that cannot be written never fails a command.
- **`memory.py stats`** (`--days`, `--json`): gate failure rate and top failing commands, evaluator rounds per pass, who verified, features marked as passing while the gate was not green, stops released on a red gate.
- **The Stop hook's one-time release is no longer silent.** A stop on a red gate is logged as `released-red` and reported under "Needs you" in the next digest, until a gate pass.
- **`skill-eval` keeps each agent transcript** and, when the agent prints a JSON result, records tokens, cost and turns per run. The cost ratio uses money, else tokens, else runtime (`cost_basis` in the report).
- `--upgrade` also replaces the pack's hook scripts (old copy backed up), so an older install gets the new Stop hook.
- README: how to join the run log with Claude Code's own OpenTelemetry export by session id.
- 7 tests.

## Unreleased — proposed fix P1 (benchmark report, 2026-11-11)
- **Hook commands no longer depend on the agent's current directory.** The installer wrote `python3 .claude/hooks/gate_on_stop.py`. Claude Code runs a hook in the current directory, which follows the agent's `cd`. After `cd tests` the script was not found, the CLI reported "Stop hook error" and the agent stopped without the gate. The commands are now `python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/...`. The 0.4.2 fix moved into the project root inside the script, but the script never started. Seen in 2 of 10 benchmark runs on SWE-bench.
- **The installer repairs the commands of an older install** in place, without adding a second copy.
- **The session-start digest reports hooks that will not run** (script missing, or relative path) under "Needs you".
- `memory.py` works from the project root when it is started in a subfolder and `CLAUDE_PROJECT_DIR` is set.
- 4 regression tests. `test_stop_hook_command_blocks_from_a_subfolder` runs the command line of `settings.json` through a shell, as the CLI does; the 0.4.2 test called the script by its absolute path and so did not see the problem.

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
