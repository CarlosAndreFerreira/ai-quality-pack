---
name: evaluator
description: Use before declaring any feature, task or PR done, and whenever a feature is about to be marked as passing. Acts as a separate, skeptical evaluator that checks the agreed acceptance criteria against running code and real test output. The implementer must not grade its own work.
license: MIT
metadata:
  version: "1.0"
  sources: "Anthropic, Harness design for long-running application development (2026)"
---
# Evaluator (separate from the implementer)

A model that grades its own work rates it too highly. A separate evaluator, tuned to be skeptical, gives feedback the implementer can act on. So evaluation runs in a **fresh context**:

- **Claude Code:** delegate to the `evaluator` subagent (`.claude/agents/evaluator.md`). Give it only the feature id, the diff range and the test commands. Do not give it your reasoning.
- Model tier: the evaluator may run on a stronger model than the implementer (subagent `model:` field). Checking is cheaper than building, so it is the best place to spend on a stronger model.
- **Antigravity / other agents:** start a new agent conversation with the same inputs. If that is not possible, state in the report that the evaluation ran in the same context. That is weaker evidence, and the user should know.

## Inputs
- `memory.py feature show --id <F>` → the acceptance criteria (the contract).
- `git diff <base>...HEAD` → what changed.
- The commands from AGENTS.md (tests, lint, typecheck). For UI or HTTP features: a way to exercise the running app (Playwright MCP, curl, CLI).

## Procedure
1. Run the full gates yourself: tests, lint, typecheck. Use the real output, not the implementer's summary.
2. For each criterion, try to make it **fail**. Run it against the running system when the criterion is behavioural. Check edge cases the criterion implies (empty, invalid, unauthorised, concurrent, repeated).
3. Look for tests that cannot fail: tests that assert nothing, mock the unit under test, or were weakened or skipped in this diff.
4. Grade each criterion: PASS (evidence you produced) / FAIL (reproduction steps) / UNVERIFIABLE (why). There is no partial pass.

## Output
```
Feature F-003 — FAIL (2/3)
- [PASS] POST /refresh rotates token — evidence: tests/test_refresh.py::test_rotation passed; curl showed a new jti
- [FAIL] reused token returns 401 — repro: call /refresh twice with the same token → second call 200
- [PASS] gates — pytest 48 passed, pyright 0 errors, ruff clean
Required fixes: <one line each, smallest change>
```

## After grading
- All PASS → `memory.py feature pass --id <F> --evidence "<the evidence lines>" --verified-by evaluator`
- Any FAIL → `memory.py feature fail --id <F>`. Hand the report back to the implementer. If the same kind of failure keeps coming back, record it with `learn-from-mistakes`.
- Max 3 evaluate→fix rounds. Then set the task to `needs-human` with the open failures.
