---
name: skill-evolve
description: Use when the session digest reports a lesson that recurred 2+ times or was voted more harmful than helpful, when the user asks to improve a skill, or when a skill proved wrong or outdated. Curates the playbook and writes a validated proposal to update a SKILL.md, applied only after explicit user approval.
license: MIT
metadata:
  version: "2.0"
  sources: "ACE curator role (ICLR 2026); Agent Skills open standard (agentskills.io)"
---
# Skill evolve (curate, propose, never self-apply)

Skills change how every future session behaves, so a bad edit spreads. This skill **proposes** a change; the user decides.

## 0. Read the history first
`python3 .agents/skills/skill-eval/scripts/skill_eval.py history --skill <name>`. Do not re-propose a change whose hypothesis was already measured as `REGRESSES` or `INCONCLUSIVE` unless you have new evidence. If several proposals in a row went nowhere, look at skills you have not touched yet.

## 1. Curate the playbook
```bash
python3 .agents/skills/long-horizon/scripts/memory.py lesson candidates
```
- **Recurring** (count ≥ 2): the rule alone is not enough. Encode it in a skill.
- **Harmful > helpful**: the rule is wrong or too broad. Propose to retire or narrow it (`lesson status --status retired`). Ask the user first.
- **Near-duplicates**: keep one key and retire the others.

## 2. Pick the smallest change that fits
1. Edit a step in the target SKILL.md so the mistake becomes hard to repeat (a check, a command, a stop condition).
2. Add one checklist line. Do not add prose.
3. AGENTS.md line, only if it applies to every task in the repo and fits in one line. Context files cost tokens in every session.
4. New skill, only for a new recurring task type, never for a single rule.

Constraints:
- **Protected core (never proposed for edit):** the AGENTS.md "Rules" section, `evaluator`, `security-review`, and the approval steps of this skill. The learning loop edits the layer around them.
- Never remove or weaken safety, security, test-integrity or approval rules.
- SKILL.md body under ~150 lines. Move long material to `references/` (one level deep).
- Keep `description` accurate: it is what agents read to decide whether to load the skill.
- Use portable frontmatter only (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`). Bump `metadata.version`.
- Upstream skills (folders with a `.upstream` file, e.g. `grill-me`) are overwritten on update. Never edit them. Propose a local wrapper skill or an AGENTS.md line instead.

## 3. Write the proposal
`.agent-memory/proposals/<YYYY-MM-DD>-<skill>.md`, max one pending proposal per skill:
```markdown
# Proposal: update <skill> (v<old> → v<new>)
Evidence: lessons <key> (N×, +h/-x) — triggers: <short list>
Problem: <what the current skill fails to prevent>
Change: <one sentence>
Risk: <what could get worse; state "none known" explicitly if so>
## Diff
<unified diff against .agents/skills/<skill>/SKILL.md>
```

## 4. Validate, measure, present
```bash
python3 .agents/skills/skill-evolve/scripts/validate_skills.py .agents/skills
```
If `.agent-memory/evals/tasks.jsonl` exists, measure the proposal with the `skill-eval` skill (`--annotate` writes the result into the proposal). Do not present a `REGRESSES` proposal. If there is no task set, write "Effect: unmeasured" in the proposal.
Show the user the Problem, the Change, the Diff and the measurement, and ask explicitly for approval.

## 5. Apply only after an explicit "yes"
Apply the diff → validate again → `lesson status --key <k> --status promoted` for each covered lesson → delete the proposal → commit `skills(<skill>): <change> [lessons: <keys>]` → set `"decision": "accepted"` on its line in `.agent-memory/skill-history.jsonl`.
Rollback: every accepted change is one commit. `git revert <sha>` undoes it, and you record `"decision": "reverted"` with the reason.
If the user declines: delete the proposal, record `"decision": "declined"`. The lessons stay active.
Periodic pruning: `skill_eval.py ablate --skill <name>`. A `PRUNABLE` skill is proposed for removal, which also needs approval.
