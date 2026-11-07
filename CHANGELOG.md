# Changelog

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
