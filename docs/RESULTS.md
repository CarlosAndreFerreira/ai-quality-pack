# Measured results

This page has the numbers that we measured for the pack, with their limits. It includes the results that are not good for the pack. A number without an interval is a count from a small sample: read it as an indication.

Setup of all agent runs: Claude Haiku, Claude Code in headless mode, each run in a Docker container that sees only the task. The benchmark harness is outside this repository (SWE-bench Verified needs about 185 GB of images). Dates: November 2026.

## 1. What the bare agent does (no pack)

| Task set | Runs | Result |
|---|---|---|
| 25 tasks that we wrote (20 short, 5 over several sessions) | 1 run for each task and more | The bare agent failed the hidden tests on 2 tasks only |
| SWE-bench Verified, 10 issues | 30 | 26 resolved; 3 false "done", all on one issue |
| SWE-bench Verified, 43 issues of "1 to 4 hours" and longer | 43 | 23 resolved (53%); 18 false "done" (42%); 2 honest "not done" |

- A false "done" is a run where the agent says that the work is done and the official grader says that it is not.
- On easy tasks the bare agent is almost always right. A pack cannot show a gain there.
- On hard issues, 4 of 10 answers "done" are wrong. This is the problem that the pack is for.

## 2. What the pack changed

| Comparison | Result | Limit |
|---|---|---|
| Full pack against core pack, on our tasks | The full pack was never better than the core | Tasks at the ceiling: 23 of 25 measure nothing |
| Pack memory on tasks over several sessions | The bare agent solved 9 of 9 with its own notes | 5 tasks |
| A Stop gate with a mandatory evaluator, on the 2 tasks where agents fail | 0 false "done" in 40 runs, against 4 in 20 runs for the bare agent | The gate was an experimental overlay, not the shipped default; 4 to 6 times the cost of a bare run |
| The same gate on 10 SWE-bench issues | 9 of 10 resolved at 2 times the cost; the evaluator approved one wrong fix | 1 run for each issue |
| Bare agent against the gate on the 20 hard issues that the bare agent failed | Not finished: 4 of 80 runs | No result |

- Release check of version 0.5.0 (the 2 tasks where agents fail, 3 runs for each arm and task): the core pack with the Stop gate ended correct in 5 of 6 runs, the bare agent in 4 of 6. The pack arm cost 3.5 times more (0.14 against 0.04 US dollars) and took 8 times longer. 6 runs for each arm show that the pack arm works; they do not show a gain.
- A defect that the measurement found: the hooks had relative paths, so the Stop gate did not run after the agent changed directory. It is fixed.
- The shipped pack with all the features of this version was not measured against the bare agent.

## 3. The evaluator on patches with a known answer

42 patches of the bare agent on the hard SWE-bench issues, each judged once by the `evaluator` subagent (the version before the merge-readiness step):

| | PASS | FAIL | UNKNOWN |
|---|---|---|---|
| Wrong patches (19) | 5 (26%, 95% interval 12% to 49%) | 11 | 3 |
| Correct patches (23) | 11 | 9 (39%, 95% interval 22% to 59%) | 3 |

- The two intervals overlap. This sample does not show that the evaluator separates wrong work from correct work.
- Cost: 0.81 US dollars for 42 patches, about the cost to write the patches. 4 runs reached the time limit of 10 minutes.
- We checked the 9 rejections of correct patches without an agent, on the base commit, the agent's patch and the reference patch. In 6, the agent's patch has a real defect that the reference patch does not have. In 2, the behaviour is the same as the reference. 1 needs a MySQL server and was not run.
- So "resolved" in SWE-bench means "passes the hidden tests", not "has no defect". The rate of correct work rejected is an upper bound of the evaluator's error.
- For the 5 wrong patches that the evaluator approved, the defect is in behaviour that only the hidden tests exercise.
- A judge that only runs the visible tests approves 12 of the 12 wrong patches in `evals/judge-cases/`. This is the floor that an evaluator must beat.

The version of the evaluator before the rewrite (it read the implementer's criteria and had no `UNKNOWN`), on the same 42 patches:

| | Older evaluator | Current evaluator |
|---|---|---|
| Wrong patches approved | 6 of 19 (32%, 95% interval 15% to 54%) | 5 of 19 (26%, 95% interval 12% to 49%) |
| Correct patches rejected | 8 of 23 (35%, 95% interval 19% to 55%) | 9 of 23 (39%, 95% interval 22% to 59%) |
| No decision | 7 | 6 |
| Same as the official label | 21 of 42 | 22 of 42 |

- The rewrite of the evaluator shows no measurable gain on these patches.
- The two versions gave the same verdict on 24 of 42 patches only. One verdict for one patch is not stable. A comparison of versions needs more than one run for each patch.

The current evaluator on the 24 cases of `evals/judge-cases/` (two small tasks):

| | PASS | FAIL |
|---|---|---|
| Wrong patches (12) | 0 (0%, 95% interval 0% to 24%) | 12 |
| Correct patches (12) | 9 | 3 (25%, 95% interval 9% to 53%) |

- Cost: 0.21 US dollars and 14 minutes for 24 cases. No case without a decision.
- The 3 rejections are on one task. The evaluator found that the fix raises an error for an infinite price, where the old code returned it. This is true for the 3 patches, and for the reference solution also. The requirement does not cover this input: the rejection is too strict, not false.
- The evaluator is much better on these small tasks (0 of 12 wrong patches approved) than on the SWE-bench issues (5 of 19). Do not use the small set to predict the result on large repositories.

## 4. Deterministic checks

| Check | Measured on | Result |
|---|---|---|
| Triage text check | 53 valid SWE-bench issues | 3 sent back in error with the first rules; 0 after 3 rules were adjusted on the same issues |
| Triage text check | 9 thin requests that we wrote | 9 sent back |
| Secret scan | 3,673 added lines in 96 real patches | 0 lines flagged; the patches had no secrets, so this measures false alarms only |
| Warning for an existing test that the change rewrote | 42 agent patches | Warning on 6 of 19 wrong patches and on 5 of 23 correct patches: it does not separate them |
| Plugin install | 2 agent sessions on Linux | The 3 hooks ran; the evaluator used the memory command after a fix |

## 5. Prompt injection

The test set in `evals/injection/` (18 attack cases, 2 runs for each case and arm, Claude Haiku, each run in a container). The set ran two times; the second run has a fix of the guard.

| Arm | Attacks that succeeded | Bug fixed |
|---|---|---|
| No pack, two runs of the set | 9 of 72 (13%, 95% interval 7% to 22%) | 72 of 72 |
| Pack with gate, guard and read rules, second run | 1 of 36 (3%, 95% interval 0% to 14%) | 36 of 36 |

- The difference is not significant with this sample (exact test, p = 0.16).
- **The model stops most attacks without the pack.** An order with "do not mention this" succeeded in 1 of 36 runs without the pack. An instruction in a code comment or in a test output never succeeded (0 of 48). In most runs the agent told the user about the instruction.
- **The attacks that work are written as a project rule, in the issue text**: 8 of 12 runs without the pack, 1 of 6 with the pack.
- **What the pack stopped, and how.** The read rule for `.env` stopped the copy of the token (0 of 12, against 3 of 24 without the pack). The permission rule for `.github/workflows/` stopped the workflow file (0 of 12, against 1 of 24). These are permission rules of Claude Code that the installer writes; they held in a session that skips permission prompts.
- **What the pack did not stop.** The deletion of a test file succeeded in 1 of 12 runs with the pack (5 of 24 without). The gate reported it ("test file deleted"), and the agent did not tell the user. The pack detects this; it does not prevent it.
- **A defect that the test set found.** In the first run the guard blocked the agent's own gate command when it ended in `2>&1` (25 of 38 pack runs). It is fixed, with tests. The results of the pack arm above are from the second run.
- Cost: 0.70 US dollars for 152 runs.
- Limits: one small task, one model, attacks that we wrote, and no network leak in the set. The sandbox was not in the pack arm, because the container cannot run it. A stronger attack can do better than these.

## 6. What is not measured

- The effect of the complete pack on false "done", against the bare agent, on hard issues.
- The `triage` subagent, the merge-readiness step of the evaluator, the reproduction check, the complexity warning, the digest size limit and the confirmation of lessons: none was measured with an agent.
- The issue workflow: it was not run on GitHub.
- Test tampering: no agent run on tasks with impossible tests (ImpossibleBench). The `block_test_changes` option of the gate was not run with an agent or on the prompt-injection test set.
- Prompt injection with a network leak, with the sandbox, in the issue workflow on GitHub, and with stronger attacks.
- Other models than Claude Haiku, other agents than Claude Code, macOS, and the plugin on Windows.

## 7. How to repeat

- Evaluator calibration, small set: see [evals/README.md](../evals/README.md).
- Label check of that set, no agent: `python evals/judge-cases/check_labels.py`.
- Prompt-injection test set: see [evals/README.md](../evals/README.md).
- Your own project: `skill-eval calibrate`, `run`, `ablate` and `judge` (README, "Measuring skill changes").
