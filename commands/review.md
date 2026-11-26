---
description: Run an independent review of the current diff using the evaluator subagent or review skills
---
Review the current workspace changes against the task requirement.

1. Run `aqp-memory diff-view` (or `git diff HEAD`) to inspect the changed lines without added comments.
2. If you have a requirement or feature ID, delegate to the `evaluator` subagent in a fresh context. Pass only the requirement text, feature ID, base ref, and test commands — never your summary or reasoning.
3. If no feature is open, run the `aqp-code-review` and `aqp-security-review` checks on the diff and report verified findings only, ranked by severity with file and line numbers.
