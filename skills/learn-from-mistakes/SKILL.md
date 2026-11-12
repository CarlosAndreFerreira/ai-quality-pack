---
name: learn-from-mistakes
description: Use right after a mistake is detected (user correction, failure after you said done, revert, evaluator FAIL, same tool error twice) and after a non-obvious approach clearly worked. Records a root-caused rule or strategy in the playbook, de-duplicated and scored, so future sessions reuse it.
license: MIT
metadata:
  version: "2.0"
  sources: "ACE — Agentic Context Engineering (ICLR 2026); Reflexion-style self-reflection"
---
# Learn from mistakes (and from what worked)

The playbook (`.agent-memory/lessons.jsonl`) grows by small **delta updates**. It is never rewritten as a whole. Full rewrites lose detail over time ("context collapse") and push towards vague summaries ("brevity bias").

## Triggers
- **Mistake** (`--kind mistake`): the user corrects you; tests, CI, a hook or the evaluator fail after you said done; a change is reverted; the same tool error happens twice.
- **Strategy** (`--kind strategy`): a non-obvious approach solved a problem that a first attempt did not. Example: "Use `uv run --frozen` in CI; plain `uv run` re-resolves and flakes".

Normal red→green TDD failures are not mistakes. Obvious practices are not strategies.

## Steps
1. Fix the immediate problem first.
2. Root cause in one sentence. Ask "why" until the cause is something you control.
3. Write the rule as one imperative, checkable sentence.
   - Bad: "Be careful with async."
   - Good: "Await every `AsyncSession` call; grep for un-awaited coroutines before done."
4. Reuse before you create: run `memory.py lesson list`. If the same cause exists, use its key. The script also refuses near-duplicate rules (exit 5) and names the existing key.
5. Record it:
   ```bash
   python3 .agents/skills/long-horizon/scripts/memory.py lesson add --kind mistake \
     --key missing-await-async-session --skill tdd-loop \
     --trigger "evaluator: handler hung on /refresh" --cause "assumed sync ORM API" \
     --rule "Await every AsyncSession call; grep for un-awaited coroutines before done."
   ```
6. Link it to the current task: `memory.py task link --id T-000N --link lesson:<key>`.
7. Tell the user in one line: what went wrong (or worked) and the rule recorded.

## Feedback on existing items (keeps the playbook honest)
When you apply a playbook item from the digest, vote on whether it helped:
`memory.py lesson vote --key <k> --vote helpful|harmful`.
Items voted more harmful than helpful show up in the digest for review. Retire wrong items with `lesson status --key <k> --status retired`.

## Escalation
Count ≥ 2, or harmful > helpful → run `skill-evolve`.

## Limits
One lesson per event. No speculative lessons. No secrets, customer data or personal data.

A lesson that you record is not in the session digest yet. A person confirms it with `memory.py lesson confirm --key <k>` in a terminal. Tell the user which lessons wait. Do not confirm a lesson yourself.
