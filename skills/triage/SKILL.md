---
name: triage
description: Use at the start of a task that comes from an issue or a short request, before a plan and before code. Decides if the requirement is ready for work. If it is not, the result is a question to the user, not code.
license: MIT
metadata:
  version: "1.0"
  sources: "Ambig-SWE (arXiv 2502.13069): agents rarely ask when the task is underspecified, and interaction recovers most of the lost performance"
---
# Triage: is the requirement ready?

An agent that is not made to ask usually does not ask. It guesses, and the work is wrong. This skill makes the question an explicit step.

## Steps
1. Run the text check: `python3 .agents/skills/long-horizon/scripts/memory.py triage --file <issue file>` (plugin install: `aqp-memory triage --file <issue file>`). Exit code 4 means that the text is too thin: give its questions to the user and stop.
2. If the check passes, use the `triage` subagent with the requirement as the user wrote it. In an agent without subagents, do its steps yourself before you read your own plan.
3. `TRIAGE: ASK`: give the questions to the user, each with your recommended answer. Change no code. In an unattended run, write the questions to `.agent-question.md` and stop.
4. `TRIAGE: READY`: record the assumptions with the acceptance criteria (`plan-before-code`), and continue.

## Rules
- Ask only what changes the result and what the repository does not answer.
- At most 3 questions. Each has options and a recommended answer.
- One issue is one change. Separate changes go to separate issues.
- The text check is a first filter. It finds an empty issue. It does not find a subtle ambiguity: step 2 does.
