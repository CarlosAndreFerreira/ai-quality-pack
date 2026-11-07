---
name: code-review
description: Use when asked to review a diff, PR, branch or file, or before declaring a non-trivial change done. Produces a ranked list of verified findings (bugs first, style last). Not for writing new features.
license: MIT
---
# Code review

## Scope
1. Get the actual diff: `git diff <base>...HEAD` (or the files named). Review what changed plus the code it calls and is called by.
2. Read the tests that cover the change. Missing tests are a finding.

## Order of attention (stop polishing style while correctness issues exist)
1. **Correctness** — wrong logic, off-by-one, wrong condition, unhandled None/null, wrong error swallowed, broken invariants.
2. **Concurrency & state** — races, shared mutable state, non-idempotent retries, transactions not committed/rolled back, missing awaits.
3. **Failure modes** — timeouts, partial failure, resource leaks (files, connections, locks), unbounded memory/queues.
4. **Security** — injection, authz checks, secrets in code/logs, unsafe deserialisation, SSRF. (Use `security-review` skill for a deep pass.)
5. **Contracts** — public API/type/schema changes, backwards compatibility, migrations.
6. **Performance** — N+1 queries, O(n²) on real sizes, sync I/O in async paths. Only when it matters at expected scale.
7. **Maintainability** — naming, duplication, dead code, misleading comments.

## Verify before reporting
For each candidate finding, build a concrete failure scenario: input/state → wrong result. If you cannot build one, drop it or mark it `PLAUSIBLE`. Do not report speculation as a bug. Run the code or a test when cheap.

## Output
Ranked, most severe first. One finding per item:

```
[SEVERITY] path:line — one-sentence defect
  Scenario: concrete input/state → wrong output/crash
  Fix: smallest correct change
```

Severity: BLOCKER (wrong results / data loss / security), MAJOR, MINOR, NIT. Max 3 NITs.
If there are no real findings, say so in one line. Do not invent findings to fill the list.
