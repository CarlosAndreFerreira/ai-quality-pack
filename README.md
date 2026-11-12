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
- Checked: `claude plugin validate --strict` passes. In two agent sessions on Linux, the three hooks ran, and the agent and the `evaluator` subagent used `aqp-memory`.
- Limits: the hook launcher is a shell script, and it has not been run on Windows. Use `install.py` there.
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

### From an issue to a draft pull request

```bash
python3 ai-quality-pack/install.py project . --with-issue-workflow      # adds .github/workflows/agent-issue.yml
python3 .agents/skills/long-horizon/scripts/memory.py pr --title "Fix add" --issue 12 --dry-run
```

- The workflow starts when a person adds the label `agent` to an issue. The agent works on the branch `agent/issue-<number>`, with a limit of turns and of US dollars.
- The workflow runs the gate and opens the pull request. The agent does not push, does not open the pull request and does not merge.
- `memory.py pr` opens a draft pull request with the evidence block. It needs the GitHub CLI (`gh`).
- It stops without a pull request if the gate is red (exit code 1), if an open pull request has the same branch or closes the same issue (exit code 3), or if work is not committed (exit code 2). The workflow then writes a comment on the issue.
- The evidence block has a review risk: `HIGH` for changes to CI, hooks, the gate, dependencies, migrations, infrastructure or security code, for changed tests and for more than 400 lines. `MEDIUM` for more than 100 lines or 5 files, or for a check without a record. `LOW` for the rest. The label is a guide for the reviewer, not a proof.
- `--cost-usd` puts the cost of the run in the block.
- Limit: the workflow template was not run on GitHub. Run it on a test issue first, and read the comments at the top of the file.

### Triage: is the issue ready for work?

```bash
python3 .agents/skills/long-horizon/scripts/memory.py triage --file issue.md
```

- Exit code 0: the text is ready for work. Exit code 4: the text is too thin, and the output is the questions for the issue.
- The issue workflow runs this check first. A thin issue gets the questions as a comment, and no agent run starts.
- The check is a set of text rules. It finds an empty or one-line issue. It does not find a subtle ambiguity.
- The `triage` subagent does the real check: it reads the repository and gives `TRIAGE: READY` with its assumptions, or `TRIAGE: ASK` with at most 3 questions. It has read-only tools.
- Measured: the text check passed 53 of 53 valid SWE-bench Verified issues, after three rules were adjusted on the same issues. It stopped 9 of 9 thin requests that we wrote. The subagent is not measured.

### Factory report

```bash
python3 .agents/skills/long-horizon/scripts/memory.py factory --days 30
```

- From GitHub (branches `agent/*`): pull requests opened, merged and closed, the merge rate with a 95% interval, the median time to merge, the cost, the review risk, and the merged pull requests that were reverted.
- From the local run log: pull requests refused for a red gate (work that ended as "done" with a red gate), unattended runs, triage results.
- The cost for each merged pull request shows only when each pull request has a cost in its text.
- Limit: the local run log is on one machine. A CI runner does not keep it.

### Merge readiness

- The evaluator checks what a maintainer checks: the written rules of the project, the style of the code next to the change, one purpose, size, documentation. It writes `MERGE-READY: YES` or `MERGE-READY: NO` after the overall result. Only a broken written rule changes the overall result.
- `"max_changed_lines": 400` in `gate.json` makes the gate warn about a larger change. It does not block.
- `doctor` says when the gate has no lint or type check command.
- Not measured: the effect of these checks on the share of pull requests that maintainers merge.

### Secrets, provenance and audit

```bash
python3 .agents/skills/long-horizon/scripts/memory.py secrets --base origin/main
python3 .agents/skills/long-horizon/scripts/memory.py provenance --set "Assisted-by: AI coding agent"
python3 .agents/skills/long-horizon/scripts/memory.py provenance --check origin/main
python3 .agents/skills/long-horizon/scripts/memory.py audit --out audit.jsonl
```

- The gate scans the lines that the change added, before it runs the project's commands. A line that looks like a secret stops the gate. The output names the file, the line and the rule, never the value.
- Rules: private keys, AWS, GitHub, Slack, Google and `sk-` keys, JSON web tokens, and a password, token or key in an assignment. Placeholders do not count. For a false alarm, put `pack:allow-secret` on the line. `"secret_scan": false` in `gate.json` turns the scan off.
- The scan is a set of patterns. It does not replace a dedicated scanner such as gitleaks: add one to the gate commands if you have it.
- `provenance` is off until a person sets a trailer. Then the agent adds the trailer to its commits, `--check` finds commits without it, and `memory.py pr` puts it in the pull request text.
- `audit` writes the run log (sessions, gate runs, gradings, pull requests, triage) with a checksum. The issue workflow keeps it as an artifact for 90 days.

### Memory: small and confirmed

- The session digest has a size limit of 6000 characters (`memory.py start --max-chars`). The most urgent items come first, so the cut removes the end.
- A lesson that an agent records is not in the digest until a person confirms it: `memory.py lesson confirm --key <key>`, in a terminal. Text that a model wrote does not become a standing instruction without a person.
- Each new lesson records who wrote it (agent or human), the commit and the session. `memory.py lesson list` shows the lessons that wait.
- Lessons from before this version stay in the digest.
- Limit: the terminal check stops an agent that confirms by habit. It is not a security boundary: `AGENT_MEMORY_HUMAN=1` passes it.

### Complexity of the change

```bash
python3 .agents/skills/long-horizon/scripts/memory.py complexity --base origin/main --max 10
```

- It reports the Python functions that the change made more complex than the limit. A function that was over the limit before, and did not grow, is not reported.
- `"max_complexity": 10` in `gate.json` makes the gate show these functions as warnings. It does not block. The installer sets it for Python projects, with `"max_changed_lines": 400`.
- The count is an approximation of cyclomatic complexity. Python only. For other languages, put the linter's rule in the gate commands.

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
