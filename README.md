# AI Quality Pack

A portable quality layer for AI coding agents (Claude Code, Google Antigravity, Codex, OpenCode, and any [Agent Skills](https://agentskills.io/specification) client). It covers deterministic gates, minimal rules, long-horizon memory, an independent evaluator, learning from mistakes, and **measured**, human-approved skill evolution.

> Status: v0.4, experimental. The design follows published work (see [Design sources](#design-sources)), but the pack's own effect on outcomes has **not** been measured yet. Use `skill-eval` on your tasks to find out.

## Why

Coding agents fail in predictable ways. They declare victory early, grade their own work too kindly, forget earlier sessions, repeat mistakes, and drift when instructions grow. This pack addresses each failure with the smallest mechanism that can be checked:

| Failure | Mechanism |
|---|---|
| "Done" without proof | Completion **gate** (lint/typecheck/tests) + optional Claude Code Stop hook |
| Self-grading bias | Separate, skeptical **evaluator** (fresh context). It alone marks features as passing |
| Vague scope | **Acceptance criteria** agreed before code; design review via Google's Elephant-Goldfish Model (optional) |
| Lost context across sessions | File memory: tasks, features, progress, playbook, plus a session-start digest |
| Repeated mistakes | **Playbook** of root-caused rules, de-duplicated, scored helpful/harmful |
| Skill drift / overfitting | `skill-evolve` proposes a diff; `skill-eval` measures it (noise floor, guards, holdout); **a human approves** |
| Insecure code | `security-review` mapped to OWASP Top 10:2025 and the OWASP LLM Top 10 2025 |
| No record of what happened | Local **run log** (`events.jsonl`) + `memory.py stats`; eval transcripts with tokens and cost |

## Install

Requires Python 3.9+ and git. No other dependencies. Works on Linux, macOS and Windows.

```bash
git clone https://github.com/CarlosAndreFerreira/ai-quality-pack
python3 ai-quality-pack/install.py project /path/to/your/repo          # auto-detects python / typescript / go / rust
python3 ai-quality-pack/install.py project . --with-stop-gate           # enforce the gate before Claude Code finishes
python3 ai-quality-pack/install.py project . --with-egm                 # + Google Elephant-Goldfish design review
python3 ai-quality-pack/install.py project . --link .codex/skills       # expose skills to another agent folder
python3 ai-quality-pack/install.py project . --dry-run                  # show what would change
python3 ai-quality-pack/install.py global                               # Antigravity plugin + Claude Code skills
```

### Claude Code plugin

```bash
claude plugin marketplace add CarlosAndreFerreira/ai-quality-pack
claude plugin install ai-quality-pack@ai-quality-pack
```

- The plugin gives Claude Code the skills, the `evaluator` and `criteria` subagents and the three hooks. It writes nothing in your repository.
- Run `aqp-memory init` in a repository to start the memory. Add `.agent-memory/gate.json` with `{"commands": [...]}` to turn on the completion gate. Without this file, the Stop hook does nothing.
- `aqp-memory` is `memory.py`. Use it where the instructions name `python3 .agents/skills/long-horizon/scripts/memory.py`.
- The plugin does not add `AGENTS.md`, `CLAUDE.md`, the CI workflow or the language profiles. Use `install.py` for these. In a project that has the `install.py` hooks, the plugin's hooks do nothing.
- This repository is private: `git` must have a stored credential for it (`gh auth login`, then `gh auth setup-git`).
- Limits: `claude plugin validate` passes, but no agent session has been run with the plugin yet. The hook launcher is a shell script, and it has not been run on Windows. Use `install.py` there.
- `claude plugin uninstall ai-quality-pack` removes it.

The installer never overwrites your files. It merges `.claude/settings.json` instead of replacing it. `--upgrade` replaces pack-owned skills and keeps a backup. Where symlinks are unavailable (Windows without developer mode), it copies.

## What gets installed

```
.agents/skills/            pack skills + pinned upstream skills (.claude/skills → symlink)
AGENTS.md                  minimal: profile commands, definition of done, memory, rules
CLAUDE.md                  @AGENTS.md
.claude/settings.json      SessionStart → memory digest · PostToolUse → formatter · (opt.) Stop → gate
.claude/agents/evaluator.md
.agent-memory/             tasks.jsonl · features.json · lessons.jsonl · progress.md · gate.json · evals/
                           events.jsonl (run log, local, not committed)
```

## Skills

| Skill | Purpose |
|---|---|
| `long-horizon` | Session ritual; tasks `T-0001…` with status, notes, links; resume after interruption; stuck detection; isolated git worktrees |
| `plan-before-code` | Routes small changes to an inline plan and large ones to EGM; always ends with testable acceptance criteria |
| `tdd-loop` | Strict red → green → refactor |
| `evaluator` | Independent, skeptical grading of each criterion against the running code |
| `code-review` | Ranked findings, each with a concrete failure scenario |
| `security-review` | OWASP Top 10:2025 (A01–A10) + OWASP LLM Top 10 (LLM01–LLM10) |
| `ui-ux-review` | Grades the running UI (WCAG 2.2 AA, heuristics, visual quality); optional pattern research with citations |
| `learn-from-mistakes` | Turns mistakes and non-obvious wins into scored playbook rules |
| `skill-evolve` | Curates the playbook; proposes skill diffs; protected core; never self-applies |
| `skill-eval` | A/B, A/A calibration and ablation of skills on verifiable tasks |
| `ste-writing` | Docs in ~80% ASD-STE100 Simplified Technical English, with a linter |

Upstream (MIT, [mattpocock/skills](https://github.com/mattpocock/skills), pinned to a reviewed commit, dependencies resolved automatically): `grill-me`, `grilling`, `grill-with-docs`, `domain-modeling`, `improve-codebase-architecture`, `codebase-design`, `handoff`.

## The loop

```
request → task open → acceptance criteria → implement → gate → evaluator (fresh context)
                                                          │ fail ×3 → ⚑ needs-human
                                                          └ pass → feature pass --verified-by evaluator → commit → progress
mistake / win → lesson add (dedup) → digest every session → helpful/harmful votes
             recurring or harmful → skill-evolve proposal → skill-eval verdict → human approves → commit (revertible)
```

## Measuring skill changes (`skill-eval`)

```bash
export SKILL_EVAL_AGENT_CMD='claude -p {prompt}'          # any headless agent; run inside a sandbox
python3 .agents/skills/skill-eval/scripts/skill_eval.py init        # write 3–10 verifiable tasks (~1/3 holdout)
python3 .agents/skills/skill-eval/scripts/skill_eval.py calibrate   # A/A run → noise band
python3 .agents/skills/skill-eval/scripts/skill_eval.py run --proposal .agent-memory/proposals/<p>.md --annotate
python3 .agents/skills/skill-eval/scripts/skill_eval.py ablate --skill <name>   # is this skill still worth it?
```
Verdicts: `IMPROVES`, `IMPROVES (weak evidence)`, `INCONCLUSIVE`, `REGRESSES`, `PRUNABLE`/`KEEP`. Four guards block a change regardless of its headline gain:
- a task the baseline always passed now fails;
- protected test files were tampered with;
- the holdout dropped beyond the noise band;
- the proposal leaks task-specific content.

## Observability

The memory files hold the state of the work. The run log holds what happened in each run. `memory.py` and the hooks write one line to `.agent-memory/events.jsonl` for each session start, gate run, feature grading, lesson vote, and Stop-hook block or release. Each line has the agent session id.

The log has ids, outcomes and durations. It has no prompt text and no code. It stays on your machine (git-ignored), and `AGENT_MEMORY_EVENTS=0` turns it off.

```bash
python3 .agents/skills/long-horizon/scripts/memory.py stats            # last 30 days; --days N, --json
```
```
# Run statistics: last 30 days (41 events, 6 sessions)
gate: 12 runs · 4 failed (33%) · 9 skipped (unchanged) · median 41.0s
  3× failed: uv run pytest -q
stop hook: 3 blocked · 1 released without a passing gate
features: 5 passed · 4 failed gradings · 1.8 evaluator rounds per pass · verified by: evaluator 4, human 1
  ⚠ marked as passing while the gate was not green for that workspace: F-3
lessons: 3 added · 2 recurred · votes +4/-1
```

Two cases that were silent before are now visible:
- The Stop hook blocks one time only, so that it cannot loop. If the agent then stops without a gate pass for its final code, the log records `released-red` and the next session digest shows it under "Needs you".
- `feature pass --verified-by evaluator` is a statement by the agent. The log records if the gate was green for that workspace at that moment, and `stats` lists the features where it was not.

`skill-eval` keeps the output of each agent run in `.agent-memory/evals/results/<run>-transcripts/`. If the agent prints a JSON result (`claude -p {prompt} --output-format json`), each run also records tokens, cost and turns, and the cost ratio of a verdict uses money or tokens instead of wall-clock time.

For tokens, cost and tool calls of your normal sessions, use the telemetry that Claude Code already has. The pack does not copy it. The `session.id` attribute there is the `session` field of the run log, so you can join the two.

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317    # your collector
```
See [Claude Code: monitoring usage](https://code.claude.com/docs/en/monitoring-usage). Other agents (Antigravity, Codex) get the run log but no session id, unless you set `AGENT_SESSION_ID`.

## Reproduction check, gate guards and doctor

```bash
python3 .agents/skills/long-horizon/scripts/memory.py repro --test "pytest tests/test_bug.py" --test-file tests/test_bug.py
python3 .agents/skills/long-horizon/scripts/memory.py doctor
python3 .agents/skills/skill-eval/scripts/skill_eval.py power --delta 0.15 --rho 0.6 --tasks 20
```

- `repro` runs the test on the base commit and on the current code. The result is `verified` only if the test fails on the base and passes now. A fix without a verified reproduction is not proved: say so in the report.
- The base runs in a temporary git worktree. Files that git does not track are not there. Use `--expect` to name text that the failure must print.
- The gate uses the committed `gate.json`. It ignores an edit that is not committed, and it reports the edit.
- The gate reports deleted test files and new skip markers. It does not block them. The next session digest shows them.
- `doctor` finds hooks that will not run and gate commands that are not installed.
- Hooks do not run in `claude -p --bare`. In CI, run `memory.py gate` as a separate step. In unattended runs, use `gated-run` (see below).
- `skill-eval power` gives the number of tasks that a comparison needs. Run it before you spend tokens.
- `diff-view` shows the change without the comments that it added. The evaluator reads this view.
- `install.py project . --with-ci` adds a GitHub Actions workflow. It runs the gate on each pull request with the `gate.json` of the base branch.
- The `criteria` subagent writes the acceptance criteria from the requirement. It does not see the implementation.
- `memory.py evidence` prints a Markdown block for a pull request. It lists what the checks recorded for this code and what is not verified.
- `skill-eval judge --cases cases.jsonl --judge-cmd "claude -p {prompt}"` measures the evaluator on cases with a known answer. The main number is the rate of wrong work that the evaluator approved.

### Unattended runs: the gate without hooks

```bash
python3 .agents/skills/long-horizon/scripts/memory.py gated-run \
  --agent-cmd "claude -p --bare --permission-mode acceptEdits" --prompt-file task.md --retries 2
```

- `gated-run` runs the agent command with the task on stdin. Then it runs the gate.
- If the gate fails, it runs the agent again with the gate output and the task. `--retry-cmd` sets a different command for these rounds.
- Exit code 0: the gate passed. Exit code 1: the gate still fails after the last round. The work is not done.
- It needs `.agent-memory/gate.json`. Without a gate file it stops with exit code 2.

### Uninstall

```bash
python3 ai-quality-pack/install.py uninstall /path/to/your/repo --dry-run   # shows the list; changes nothing
python3 ai-quality-pack/install.py uninstall /path/to/your/repo
python3 ai-quality-pack/install.py uninstall --global
```

- It removes the pack's skills, subagents, hook scripts, hook entries in `.claude/settings.json`, the CI workflow and `CLAUDE.md`.
- It keeps a file that differs from the pack's copy, because the changes are yours. `--force` removes these files also.
- It keeps `AGENTS.md` and `.agent-memory/`. `--purge-memory` removes `.agent-memory/`.
- It keeps your other hooks and settings.

### Python version

The scripts need Python 3.9 or newer. If the project's `python` is older (3.6 to 3.8), each script starts again with a newer Python from `PATH` (`python3.9` to `python3.15`, `python3`, `python`). Set `AGENT_PACK_PYTHON` to select one. If none is found, the script prints the cause and exits with code 1.

### Checks before a push

The CI of this repository runs on a manual trigger. Run these three commands before a push:

```bash
python -m unittest discover -s tests
python skills/skill-evolve/scripts/validate_skills.py skills --strict
python skills/ste-writing/scripts/ste_lint.py README.md --lang en --threshold 60
```

## Robustness
- Atomic writes plus a cross-process lock (tested with 16 concurrent writers).
- Append-only logs with `merge=union`. Duplicates and conflict markers are folded on read, and task-id collisions after a merge are flagged.
- The memory digest is sanitised and wrapped as data (`<project-memory>`). Obvious secrets are refused at write time.
- `unittest` suite (installer, memory, gate, evals, concurrency). CI on Linux, macOS and Windows (Python 3.9 and 3.13).

## Limitations
- **Not measured end to end.** The design sources report gains for *their* systems, not for this pack.
- **Antigravity**: `install.py global` installs a native Antigravity plugin (`~/.gemini/config/plugins/ai-quality-pack/`) with `plugin.json`, global `rules/AGENTS.md`, and the isolated `evaluator` subagent (`agents/evaluator.md`).
- **No sandbox.** Agents run with your permissions. Use a devcontainer or VM for unattended runs.
- The run log sees only what goes through `memory.py` and the pack hooks. It does not see the agent's reasoning or its other tool calls. Two sessions in one checkout at the same time share one session id file, so their events can get the wrong id.
- Recurrence counting depends on the agent reusing lesson keys. Duplicate detection is lexical, not semantic.

## Design sources
- Anthropic: [Effective harnesses for long-running agents](https://anthropic.com/engineering/effective-harnesses-for-long-running-agents) · [Harness design for long-running application development](https://anthropic.com/engineering/harness-design-long-running-apps)
- [Evaluating AGENTS.md (ICLR 2026)](https://arxiv.org/abs/2602.11988): keep context files minimal
- [ACE: Agentic Context Engineering (ICLR 2026)](https://arxiv.org/abs/2510.04618): itemised playbooks with incremental updates
- [Google Research RRSI](https://github.com/google-research/rrsi): regularised harness self-improvement (noise floor, guards, holdout)
- [GEPA / gskill](https://github.com/gepa-ai/gepa): measuring skills on verifiable repo tasks
- [Google Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model): fresh-context design review
- DeepSeek Super-agent, Prime Agent, LongHorizon-Harness: task IDs and recovery, completion gate, stuck detection
- [Test-Driven Development for Code Generation](https://arxiv.org/abs/2402.13521); [OWASP Top 10:2025](https://owasp.org/Top10/2025/)

Evaluated projects and why each was or was not adopted: [docs/extensions.md](docs/extensions.md).

## License
MIT. Upstream skills keep their own licenses (copied into each folder with a `.upstream` provenance file).
