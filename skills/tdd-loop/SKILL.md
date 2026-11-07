---
name: tdd-loop
description: Use when implementing a new function, endpoint, module or bugfix in an existing codebase. Drives a strict red→green→refactor loop with the project's test runner. Not for throwaway spikes or pure config changes.
license: MIT
---
# TDD loop

## Before the first test
1. Find the test command in AGENTS.md / CLAUDE.md / package.json / pyproject.toml. Do not guess it.
2. Run the existing suite once. If it is already red, stop and report. Do not build on a red baseline.

## Loop (one behaviour per iteration)
1. **Red** — Write ONE test for the next behaviour. Run it. Confirm it fails, and fails for the expected reason (assertion, not ImportError/typo).
2. **Green** — Write the minimum code that makes it pass. Run the full suite, not only the new test.
3. **Refactor** — Clean names, duplication and structure with tests green. Run lint + typecheck.
4. Repeat until the acceptance criteria are covered.

## Coverage of a behaviour (decide per case, do not pad)
- Happy path.
- Boundaries that are real for this input (empty, zero, max, unicode, timezone) — only those that apply.
- Error paths the caller can trigger. Assert the error type and message, not only "raises".
- For bugfixes: the first test reproduces the bug. It must fail before the fix.

## Rules
- Test behaviour through the public interface. Do not test private helpers or mock what you own.
- Mock only at system boundaries (network, clock, filesystem, external APIs).
- Never weaken, skip or delete a test to make the suite pass. If a test is wrong, say why and ask.
- Never edit expected values to match output you have not checked by reasoning.
- Property-based tests (Hypothesis / fast-check) when the input space is large and an invariant is easy to state.

## Done when
Full suite green, lint + typecheck clean, and you can list which test covers each acceptance criterion.
