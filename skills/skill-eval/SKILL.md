---
name: skill-eval
description: Use before presenting or applying a skill-evolve proposal, when the user asks whether a skill change or an existing skill actually helps, or for periodic pruning. Measures skills on verifiable tasks in throw-away git worktrees, with noise calibration, non-compensatory guards, a held-out split, a leakage critic and an auditable history.
license: MIT
metadata:
  version: "2.0"
  sources: "GEPA/gskill; Google Research RRSI (regularised recursive self-improvement, 2026); Prime Agent (reward-hacking guard)"
---
# Skill eval (measure before you trust a skill change)

Script: `python3 .agents/skills/skill-eval/scripts/skill_eval.py <command> --help` — do not read the source.

## 1. Task set (once per repo)
`skill_eval.py init` creates `.agent-memory/evals/tasks.jsonl`. Help the user write **3–10 tasks**:
- `check`: an objective command that exits 0 only on success.
- `protect`: the files that judge the task (tests). They are restored before the check, and any edit to them fails the run, so the agent cannot game them.
- `split`: mark about 1/3 as `"holdout"`. Holdout tasks are reported separately, and a drop there blocks the change (overfitting guard).
- Use real work from this repo, including the kind of mistake the proposal targets. An SRS-based benchmark such as `viriato-bench` works well.

## 2. Agent command
`export SKILL_EVAL_AGENT_CMD='<template>'`. Placeholders: `{prompt}`, `{prompt_file}`, `{workdir}`.
- Claude Code: `claude -p {prompt} --output-format json`, plus the permission flags your setup needs for unattended edits, only inside a sandbox or container. With the JSON result, each run records its tokens, cost and turns, and the cost ratio uses money (or tokens) instead of wall-clock time.
- No headless mode (some IDE agents): this measurement is not available for that agent. Say so.

## 3. Calibrate noise (once, and again after the model or task set changes)
`skill_eval.py calibrate --repeats 3` runs baseline vs baseline. Agents are stochastic, and the disagreement rate becomes the **noise band**. Without it, a 10% default is used.

## 4. Measure
- Proposal: `skill_eval.py run --proposal .agent-memory/proposals/<file>.md --annotate`
- Existing skill (pruning): `skill_eval.py ablate --skill <name>`
- Each run keeps the agent's output in `.agent-memory/evals/results/<run>-transcripts/` (git-ignored). Read the transcript of a failed run before you explain a `REGRESSES` or `INCONCLUSIVE` verdict.
- Past results: `skill_eval.py history [--skill <name>]`. Read this before you propose, so you do not re-propose a falsified idea.
Runs = tasks × repeats × 2. Above 20 the script asks for `--yes`. **Ask the user first**: it costs tokens.

## 5. Verdicts
| Verdict | Rule | Action |
|---|---|---|
| `REGRESSES` | Any guard fired: a task the baseline always passed now fails, protected files were tampered with, or the holdout dropped beyond noise | Do not propose it |
| `INCONCLUSIVE` | Gain within the noise band, or a small gain that costs >25% more (money, tokens or runtime), or a cost above `--max-cost-per-pass` | Present it as "no measurable effect"; prefer the smaller skill |
| `IMPROVES (weak evidence)` | Gain above noise, sign test p > 0.1 | Present it with the numbers and the caveat |
| `IMPROVES` | Gain above noise, p ≤ 0.1, no guard fired | Present it with the numbers |
| `PRUNABLE` / `KEEP` (ablate) | Removing the skill changed nothing / hurt | Propose removal to the user / keep it |
| `NOT-USED` (ablate) | The agent never used the skill in the runs that had it | The result says nothing about the skill. Improve its description, or propose removal |

When you present a measurement, quote the `reliability at cost` line of each variant: the share of tasks where each run passed, with its interval, and the cost for each passed run.

The leakage critic refuses a proposal whose added lines mention task ids, protected files or check paths (exit 6). Rewrite the rule in general terms.

A verdict is evidence for the user, not permission. `skill-evolve` still needs an explicit "yes". After the user decides, record the decision in `.agent-memory/skill-history.jsonl` (`"decision": "accepted"|"declined"`).

## Advanced: GEPA / gskill
To *search* for better skills rather than test one change, use GEPA's gskill (see `docs/extensions.md`). Candidates still go through this skill and user approval.
