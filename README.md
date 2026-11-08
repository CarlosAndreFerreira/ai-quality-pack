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

The installer never overwrites your files. It merges `.claude/settings.json` instead of replacing it. `--upgrade` replaces pack-owned skills and keeps a backup. Where symlinks are unavailable (Windows without developer mode), it copies.

## What gets installed

```
.agents/skills/            pack skills + pinned upstream skills (.claude/skills → symlink)
AGENTS.md                  minimal: profile commands, definition of done, memory, rules
CLAUDE.md                  @AGENTS.md
.claude/settings.json      SessionStart → memory digest · PostToolUse → formatter · (opt.) Stop → gate
.claude/agents/evaluator.md
.agent-memory/             tasks.jsonl · features.json · lessons.jsonl · progress.md · gate.json · evals/
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

## Robustness
- Atomic writes plus a cross-process lock (tested with 16 concurrent writers).
- Append-only logs with `merge=union`. Duplicates and conflict markers are folded on read, and task-id collisions after a merge are flagged.
- The memory digest is sanitised and wrapped as data (`<project-memory>`). Obvious secrets are refused at write time.
- `unittest` suite (installer, memory, gate, evals, concurrency). CI on Linux, macOS and Windows (Python 3.9 and 3.13).

## Limitations
- **Not measured end to end.** The design sources report gains for *their* systems, not for this pack.
- **Antigravity**: `install.py global` installs a native Antigravity plugin (`~/.gemini/config/plugins/ai-quality-pack/`) with `plugin.json`, global `rules/AGENTS.md`, and the isolated `evaluator` subagent (`agents/evaluator.md`).
- **No sandbox.** Agents run with your permissions. Use a devcontainer or VM for unattended runs.
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
