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
- Not measured: an older version of the evaluator on the same patches (the run is in progress), and the evaluator on the 24 cases of `evals/judge-cases/`.

## 4. Deterministic checks

| Check | Measured on | Result |
|---|---|---|
| Triage text check | 53 valid SWE-bench issues | 3 sent back in error with the first rules; 0 after 3 rules were adjusted on the same issues |
| Triage text check | 9 thin requests that we wrote | 9 sent back |
| Secret scan | 3,673 added lines in 96 real patches | 0 lines flagged; the patches had no secrets, so this measures false alarms only |
| Warning for an existing test that the change rewrote | 42 agent patches | Warning on 6 of 19 wrong patches and on 5 of 23 correct patches: it does not separate them |
| Plugin install | 2 agent sessions on Linux | The 3 hooks ran; the evaluator used the memory command after a fix |

## 5. What is not measured

- The effect of the complete pack on false "done", against the bare agent, on hard issues.
- The `triage` subagent, the merge-readiness step of the evaluator, the reproduction check, the complexity warning, the digest size limit and the confirmation of lessons: none was measured with an agent.
- The issue workflow: it was not run on GitHub.
- Test tampering: no agent run on tasks with impossible tests (ImpossibleBench).
- Other models than Claude Haiku, other agents than Claude Code, macOS, and the plugin on Windows.

## 6. How to repeat

- Evaluator calibration, small set: see [evals/README.md](../evals/README.md).
- Label check of that set, no agent: `python evals/judge-cases/check_labels.py`.
- Your own project: `skill-eval calibrate`, `run`, `ablate` and `judge` (README, "Measuring skill changes").
