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
| Bare agent against the core pack of version 0.6.0 on the same 20 hard issues, 2 runs for each issue and arm | Resolved: 4 of 40 with the pack, 2 of 40 without. False "done": 27 of 40 with the pack, 35 of 40 without | The gate had no commands, so it checked nothing. See below |
| Bare agent against a gate with commands, and against that gate with a mandatory evaluator, on 40 hard issues, 2 runs for each issue and arm | False "done": 30 of 80 for the bare agent, 32 of 80 with the gate, 14 of 80 with the evaluator. Resolved: 46, 39 and 38 of 80 | With the evaluator, the agent said "not done" for 29 of 38 correct patches. See below |

- Release check of version 0.5.0 (the 2 tasks where agents fail, 3 runs for each arm and task): the core pack with the Stop gate ended correct in 5 of 6 runs, the bare agent in 4 of 6. The pack arm cost 3.5 times more (0.14 against 0.04 US dollars) and took 8 times longer. 6 runs for each arm show that the pack arm works; they do not show a gain.
- A defect that the measurement found: the hooks had relative paths, so the Stop gate did not run after the agent changed directory. It is fixed.
- Core pack of version 0.6.0 (Stop gate, evaluator, plan before code, memory) against the bare agent, 20 hard SWE-bench issues, 80 runs, Claude Haiku:
  - Resolved issues: 4 of 40 (10%, 95% interval 4% to 23%) with the pack, 2 of 40 (5%, 95% interval 1% to 17%) without. For each issue: the pack was better on 3, worse on 1, equal on 16 (sign test, p = 0.63). No difference that this sample can show.
  - False "done": 27 of 40 (68%) with the pack, 35 of 40 (88%) without. For each issue: fewer on 8, more on 2, equal on 10 (sign test, p = 0.11). The agent with the pack said "not done" in 9 runs, the bare agent in 3, and each of these statements was correct.
  - Cost for each run: 0.030 US dollars with the pack, 0.019 without (1.6 times). Median time: 140 seconds against 69 seconds.
  - The gate checked nothing. These repositories have no `.agent-memory/gate.json`, and no agent wrote it. The gate printed "nothing to gate" in 30 runs and was not run in 10. The evaluator ran in 6 of 40 runs: this arm does not make it mandatory. Thus this comparison measures the instructions of the pack, not a gate.
  - After this result, the gate fails when it has no commands, and `memory.py stats` shows in how many sessions each control ran.
- The complete pack with all the features was not measured against the bare agent on hard issues.

### A gate that has commands, and a mandatory evaluator, against the bare agent

The question: does a Stop gate that runs the tests of the project, or a Stop gate that also needs a PASS of the evaluator (`"require_evaluator": true`), make fewer false "done" than the bare agent?

- **The cases.** The 40 hard SWE-bench Verified issues ("1 to 4 hours" and longer) that have a test command that passes on the base commit. 2 runs for each issue and arm: 240 runs. Claude Haiku is the author and the evaluator. The pack is at the commit after version 0.10.2 that has the option.
- **The test command.** The test files of the project that the official test patch changes, as they are on the base commit. The hidden tests are not in it. The 3 arms get the same command, so the arms differ in the obligation and not in the information.
- **The arms.** A0c: the bare agent, with the test command in the prompt. G: the core pack, with the command in a committed `gate.json` and the Stop gate. GE: G with `"require_evaluator": true`.
- **The controls ran.** The gate ran its command in 80 of 80 runs of G and in 80 of 80 runs of GE. In GE the hook blocked for the evaluator in 74 of 80 runs, and 74 runs have a verdict.

| | A0c | G | GE |
|---|---|---|---|
| Resolved (the hidden tests pass) | 46 of 80 (58%) | 39 of 80 (49%) | 38 of 80 (48%) |
| The agent said "done" | 74 (92%) | 63 (79%) | 23 (29%) |
| False "done", of all runs | 30 (38%) | 32 (40%) | 14 (18%) |
| Correct patch, and the agent said "not done" | 2 (2%) | 8 (10%) | 29 (36%) |
| Wrong answers among the answers "done" | 30 of 74 (41%) | 32 of 63 (51%) | 14 of 23 (61%) |
| Runs that used the 30 minutes | 0 | 0 | 8 |
| Mean cost of a run (US dollars) | 0.017 | 0.021 | 0.096 |
| Mean time of the agent (seconds) | 85 | 173 | 831 |

Differences in percentage points, with a 95% interval from a bootstrap over the issues (10,000 samples):

- Resolved: G − A0c = −8.7 (−18.8 to 0.0). GE − A0c = −10.0 (−21.2 to −1.2).
- False "done": G − A0c = +2.5 (−6.2 to +11.3). GE − A0c = −20.0 (−31.2 to −8.8).

What the numbers say:

- **The gate with the tests of the project did not change the number of false "done".** Its command failed in 4 of 80 runs and the hook blocked in 3. A wrong patch passes the existing tests in most cases, as the count above showed (9 of 86).
- **The mandatory evaluator made fewer false "done", because the agent then said "not done" in most runs.** The records had no PASS for 32 of 37 correct patches (86%) and for 29 of 37 wrong patches (78%). They had a PASS for 5 correct patches and for 8 wrong patches. Thus a PASS did not separate them. Correction of 2026-11-24: the first text of this page said "the evaluator gave FAIL" for these 32 and 29 runs. The number counts a FAIL, an UNKNOWN and a run without a verdict together.
- **Why there was no PASS** (one person read the last record of the evaluator in each of the 61 runs; no run was repeated):

  | Last record of the evaluator | Correct patches (32) | Wrong patches (29) |
  |---|---|---|
  | No defect found; no PASS because the test was recorded after the change, or because a part did not run in the container | 15 | 12 |
  | A `regression` counterexample for the behaviour of the code | 0 | 7 |
  | A case that the change does not repair and that fails on the base also, or a stricter reading of the request | 6 | 5 |
  | A project rule that is not about behaviour (changelog entry, import order) | 2 | 0 |
  | No verdict in the records, or the run used the 30 minutes | 7 | 4 |
  | A FAIL first and a PASS after it | 2 | 1 |

- **The largest cause is a rule of the pack, not a judgement of the model.** A PASS needs a test that was recorded before the change. With `require_evaluator` the agent learns about the evaluator at the Stop hook, after the change. Thus the rule refused a PASS for 12 correct patches and for 12 wrong patches where the evaluator found no defect. To accept a later test is not the repair: the same 12 wrong patches then get a PASS.
- **A `regression` counterexample was the one record that separated the patches**: 7 wrong patches and 0 correct patches. This agrees with the 3 of 3 above. The next measurement did not repeat it (12 wrong patches and 9 correct patches; see the section below). 2 correct patches had a `regression` record for a lint rule, not for behaviour.
- **An answer "done" was not more reliable with the pack.** It was wrong in 61% of the cases in GE, in 51% in G and in 41% for the bare agent.
- **The two pack arms resolved fewer issues than the bare agent.** For GE the interval does not include zero. The cause is not measured. In GE, 8 runs used the full 30 minutes; the harness counts them as "done" (5 wrong, 3 correct).
- **Cost.** GE cost 5.6 times the bare agent and took 10 times longer.
- What this means for use: do not turn on `require_evaluator` to make "done" reliable. It makes the agent say "not done" for correct work also. A gate with the tests of the project stops a "done" without a check and finds a regression; it does not find a patch that repairs the wrong thing.
- Cost: 10.79 US dollars for 240 runs.
- Limits: one model for the author and for the evaluator. The 2 runs of an issue are not independent. 68 runs ran one at a time and 172 ran 4 at a time, with the issues divided between the 4 processes. In 1 run of GE the agent changed `.agent-memory/gate.json`; the hook reads the committed file, so the check stayed on. 11 runs left an empty patch (2, 5 and 4).

### The "regression" mode of the mandatory evaluator against the bare agent

The question: with `"require_evaluator": "regression"`, where only a `regression` counterexample blocks the stop (the mode as it was at this commit; it does not block now), does the agent call a correct patch done, and is its "done" more reliable than that of the bare agent?

- **The cases.** The same 40 hard issues and the same test command as above. 2 runs for each issue and arm: 160 runs on one day (2026-11-24), 4 at a time. Claude Haiku is the author and the evaluator. The pack is at the commit `bcfed3c`, after version 0.10.2.
- **The arms.** A0c: the bare agent, with the test command in the prompt. GR: the core pack, with the command in a committed `gate.json`, the Stop gate and `"require_evaluator": "regression"`.
- **The criteria, written before the run.** (1) GR calls a minimum of 80% of its correct patches done. (2) GR resolves not more than 5 points fewer issues than A0c. (3) The precision of "done" in GR is higher than in A0c. (4) A maximum of 5% of the runs of GR use the 30 minutes.

| | A0c | GR |
|---|---|---|
| Resolved (the hidden tests pass) | 41 of 80 (51%) | 39 of 80 (49%) |
| The agent said "done" | 75 (94%) | 55 (69%) |
| False "done", of all runs | 35 (44%) | 27 (34%) |
| Correct patches that the agent called done | 40 of 41 (98%) | 28 of 39 (72%) |
| Wrong patches that the agent called done | 35 of 39 (90%) | 27 of 41 (66%) |
| Correct answers among the answers "done" (precision) | 40 of 75 (53%) | 28 of 55 (51%) |
| Runs that used the 30 minutes | 0 | 0 |
| Mean cost of a run (US dollars) | 0.019 | 0.073 |
| Mean time of the agent (seconds) | 92 | 508 |

Differences in percentage points, GR − A0c, with a 95% interval from a bootstrap over the issues: resolved −2.5 (−11.3 to +7.5); false "done" −10.0 (−22.5 to +2.5); the agent said "done" −25.0 (−36.3 to −13.8).

The result against the criteria: criterion 1 failed (72%), criterion 2 passed (−2.5 points, and the interval goes to −11.3), criterion 3 failed (51% against 53%), criterion 4 passed (0 runs).

What the pack recorded in the 80 runs of GR:

| Record | Correct patches (39) | Wrong patches (41) |
|---|---|---|
| The evaluator recorded a result | 36 | 37 |
| Last result of the evaluator: PASS | 11 | 12 |
| Last result of the evaluator: FAIL | 12 | 14 |
| Last result of the evaluator: UNKNOWN | 13 | 11 |
| A test recorded before the change | 24 | 21 |
| `memory.py verdict` gave `SUPPORTED` at the end | 16 | 13 |
| A `regression` counterexample | 9 | 12 |
| The limit of evaluations came into effect (`LIMIT`) | 9 | 14 |

What the numbers say:

- **GR said "done" less frequently, and did not separate the patches.** It did not call done 28% of its correct patches and 34% of its wrong patches. Thus the false "done" decreased because "done" decreased, and the precision of "done" did not change.
- **The `regression` counterexample did not separate the patches in this run.** 12 wrong patches and 9 correct patches have one. In the measurement above it was 7 and 0, and before that 3 and 0. The difference in this run: the instructions tell the evaluator to look for a regression first.
- **Most of these counterexamples reject the reference fix also.** With no agent, we ran each recorded command again in the image of the issue: on the base, on the last patch of the agent and on the reference fix of the maintainers. The files of the evaluator came from the transcript of the run. 18 of the 21 runs gave a command that passes on the base.

  | | Correct patches | Wrong patches |
  |---|---|---|
  | Runs with a `regression` counterexample | 9 | 12 |
  | Runs where a command passes on the base again | 8 | 10 |
  | The last patch of the agent fails a command | 0 of 8 | 2 of 10 |
  | The reference fix fails a command | 7 of 8 | 7 of 10 |

  - In 14 of 18 runs, the reference fix fails a command that the evaluator recorded as a regression. The record is correct as a fact: the behaviour changed. It is not a defect: the correct fix changes the same behaviour.
  - The agent repaired the difference in 16 of 18 runs, thus its last patch has the behaviour of the base. The limit of evaluations then let the agent stop without a new verdict, so the records do not show the repair.
  - A counterexample that stays on the last patch is rare: 0 of 8 correct patches and 2 of 10 wrong patches. The 2 are one issue.
  - On the 10 issues where the reference fix fails a command, the bare agent resolved 12 of 20 runs and GR resolved 12 of 20. Thus no loss is measured from these repairs.
  - Limits: the file is the last version in the session, which can be different from the version at the record. 3 runs did not give a command that passes on the base. The 7 and 0 of the measurement above were not checked in this way.
- **No record of the pack separated the patches.** A PASS, a FAIL, an UNKNOWN, a test recorded before the change and a `SUPPORTED` verdict have almost the same count for correct and for wrong patches.
- **The mode is better than the first mode for correct patches**, as designed: the agent called done 72% of them, against 6 of 38 (16%) with `"require_evaluator": true`. No run used the 30 minutes, against 8.
- **The two defects of the pilot runs did not occur.** The evaluator recorded a result in 73 of 80 runs, and the limit of evaluations came into effect in 23.
- **The agent did not obey the records.** It said "done" in 13 of the 21 runs with a `regression` counterexample (the limit of evaluations then lets the stop pass), in 13 of 26 runs where the last result was a FAIL, and in 20 of 24 where it was an UNKNOWN.
- **Cost.** GR cost 3.8 times the bare agent and took 5.5 times longer. 7.36 US dollars for 160 runs.
- What this means for use: do not turn on `require_evaluator`, in the one mode or in the other, to make "done" reliable on hard issues when one model is the author and the evaluator. Read a `regression` counterexample as "the behaviour changed": a person decides if the request wants that change. With these two measurements, a check by the same model added no information about the correctness of the patch.
- Limits: one model for the author and for the evaluator, hard issues only, Python only. The 2 runs of an issue are not independent. 80 runs for each arm cannot show a difference of 7 points in false "done". Not measured: a stronger model as the author and as the evaluator, and tasks that are less hard. 6 runs left an empty patch.

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

### The evaluator on another model (version 0.7.1)

The same 24 cases, one run for each case, the evaluator of version 0.7.1. The session that calls the evaluator is on Claude Haiku in the two rows. Only the model of the evaluator subagent changes (`install.py --evaluator-model`).

| Model of the evaluator | Wrong patches approved (12) | Correct patches rejected (12) | Cost | Time |
|---|---|---|---|---|
| Claude Haiku (the model of the author of the patches) | 0 (0%, 95% interval 0% to 24%) | 3 (25%, 95% interval 9% to 53%) | 0.22 US dollars | 14 minutes |
| Claude Sonnet | 7 (58%, 95% interval 32% to 81%) | 0 (0%, 95% interval 0% to 24%) | 0.80 US dollars | 8 minutes |

- The stronger model approved more wrong patches: 7 of 12 against 0 of 12 (Fisher exact test, p = 0.005). It rejected no correct patch (3 for Haiku, p = 0.22).
- The 7 approvals are one defect. In 9 of the 12 wrong patches, `available()` returns an integer when the bucket is full, and the requirement says that it returns a float. Haiku found this defect in 9 of 9 patches, and Sonnet in 2 of 9. The two models rejected the 3 wrong patches of the other task. Thus the 12 wrong patches are not 12 independent cases: this result shows one type of defect that Sonnet missed, not a general rate.
- The evaluator on Sonnet ran its own checks in each case (the transcripts show it, and the model in the usage record). It reported that `available()` returns a float; it did not test a full bucket.
- What this means for use: a stronger model for the evaluator is not better by default. On this set it was less strict in the two directions, at 3.6 times the cost. Measure the evaluator on your cases before you change its model.
- Limits: one run for each case, two small tasks, and the patches are from Haiku.

The same comparison on the 42 SWE-bench patches (19 wrong, 23 correct). The evaluator is that of version 0.6.0 in the two rows, and its text did not change after that version. One line is different: the model of the evaluator subagent.

| Model of the evaluator | Wrong patches approved (19) | Correct patches rejected (23) | No decision | MCC | Cost for one pass |
|---|---|---|---|---|---|
| Claude Haiku, 3 passes | 3, 4, 2 (9 of 57, 16%) | 15, 16, 15 (46 of 69, 67%) | 4, 5, 6 | 0.10, -0.01, 0.16 | 0.70 to 0.74 US dollars |
| Claude Sonnet, 1 pass | 13 (68%, 95% interval 46% to 85%) | 4 (17%, 95% interval 7% to 37%) | 1 | 0.12 | 2.38 US dollars |

- The model changes the direction of the error, not the quality of the judgement. Haiku rejects most patches (FAIL for 67% of the correct patches and for 72% of the wrong patches). Sonnet approves most patches (PASS for 83% of the correct patches and for 68% of the wrong patches). The agreement with the official label is near zero for the two models (MCC 0.12 against -0.01 to 0.16).
- The two differences are large (Fisher exact test against the 3 passes of Haiku together: p < 0.001 for the wrong patches approved, p < 0.001 for the correct patches rejected). Sonnet gave the same verdict as a pass of Haiku for 16 or 17 of the 42 patches.
- Of the 13 wrong patches that Sonnet approved, Haiku rejected 6 in each of its 3 passes.
- Sonnet was faster: 60 minutes of agent time for the pass, against 141 to 168 minutes, and no run at the time limit. It cost 3.2 times more.
- What this means for use: do not change the model of the evaluator to get a better evaluator. On hard issues, a PASS of the evaluator on Sonnet has as little information as a FAIL of the evaluator on Haiku. The weak part is what the evaluator can check, not the model: on these issues the hidden tests of the maintainers decide, and the evaluator does not have them.
- Limits: one pass for Sonnet, and one verdict is not stable on this set. The official label is a weak reference for a rejection (see above). Not measured: a model of another supplier, and Sonnet as the author of the patches.

### Verdicts with evidence that a command produced (`verdict_evidence`)

The 42 SWE-bench patches again, with `"verdict_evidence": true` in each workspace, one pass for each model of the evaluator. In this test the option is an instruction to the evaluator only: the harness has no feature record, so `feature vote` does not refuse a verdict.

| Evaluator | Wrong patches approved (19) | Correct patches rejected (23) | No decision | MCC |
|---|---|---|---|---|
| Haiku, option off, 3 passes | 3, 4, 2 | 15, 16, 15 | 4, 5, 6 | 0.10, -0.01, 0.16 |
| Haiku, option on | 3 | 14 | 6 | 0.10 |
| Sonnet, option off | 13 | 4 | 1 | 0.12 |
| Sonnet, option on | 12 | 3 | 1 | 0.24 |

- The verdicts did not change (Fisher exact test, p from 0.62 to 1.00). An instruction is not a control: the evaluator gave a verdict without the command.
  - Sonnet read `config.json` in 1 of 42 runs and ran `repro` or `counterexample` in none.
  - Haiku read it in 41 of 42 runs and ran one of the two commands in 22 runs, with 10 usage errors. It gave 28 FAIL verdicts, and 19 of them had no counterexample that the command accepted.
- The records of the commands separate better than the verdicts. In the pass of Haiku:
  - A counterexample of type `regression` (the check passes on the base and fails on the change): 3 runs, and the 3 patches are wrong.
  - A counterexample of type `not-fixed` only (the check fails on the base also): 6 runs, 2 wrong patches and 4 correct patches. In the transcripts, a part of these checks imports the code from an absolute path, thus the run on the base used the code of the change. This type has little information.
  - A verified reproduction (fails on the base, passes on the change): 3 runs; 2 are wrong patches that the evaluator approved. A test that the model wrote for the patch can agree with a wrong patch.
- What this means for use: a `regression` counterexample shows a real difference from the base, and a person must read it. It is not a decision: a later measurement found it for 12 wrong patches and for 9 correct patches, and in 14 of 18 runs the reference fix failed the same command (see section 2). Do not read a `not-fixed` counterexample or a verified reproduction from the evaluator as a decision. Use `feature vote` or `feature pass`, which refuse a verdict without the record; a text of the evaluator does not.
- Limits: 3, 6 and 3 runs are small numbers. One pass for each model. The baseline rows use the pack of version 0.6.0 and the rows with the option use the current pack with a gate file without commands; the text of the evaluator is the same, plus the paragraph of the option. Cost: 3.36 US dollars for the two passes.

### What a gate with the existing tests of a project can find

No agent ran for this number. It comes from the reports of the SWE-bench grader for the runs above. A wrong patch that breaks an existing test of the project (`PASS_TO_PASS`) makes a gate with those tests fail. A wrong patch that fails only the hidden tests (`FAIL_TO_PASS`) passes that gate.

- Of 86 wrong patches on hard issues, 9 break an existing test (10%, 95% interval 6 to 19%). The other 77 fail hidden tests only. The 86 are 19 patches of the bare agent in the selection run, and 36 of the bare agent and 31 of the core pack in the comparison of version 0.6.0.
- What this means for use: a gate with the tests of the project stops a "done" without a check, and it finds a regression. It does not find a patch that repairs the wrong thing. A green gate is not proof that a patch is correct.
- Limits: hard issues only, and one model as the author. The gate also runs lint and type checks, which this number does not include.

### One use on a real project

A security fix in a Rust application of the author of the pack (2026-11-16), with the feature record, `repro`, the gate of the project and the independent evaluator in a separate context.

- The reproduction test failed on the base and passed with the fix. The gate passed.
- The evaluator gave FAIL in its first round, with a check of its own: a redirect with status 307 sent the credentials to a different host. The tests of the author and the gate did not find this. After the fix, the evaluator gave PASS.
- A person then ran the application with a real session, with no failure.
- Limits: this is one case, not a rate. The evaluator ran on a stronger model than Haiku. The use also showed three defects of the pack, corrected in version 0.8.0.

### A second use on a real project

A second security fix in the same Rust application (2026-11-17), with the defaults of version 0.9: the test recorded with the criteria before the change, and the result from the records.

- The test failed on the base: a host that is not trusted received the request with the token of the session. `repro` with a build directory of its own for the base gave `VERIFIED`. The gate passed. `cargo-mutants` on the changed lines made 2 mutants, and the tests caught the 2. `memory.py verdict` gave `SUPPORTED`.
- The independent evaluator ran 7 checks of its own (33 forms of the address, redirects, 2 controls) and found no counterexample. It listed 4 risks outside the criteria and 3 weak points of the tests of the author.
- The use showed 5 defects of the pack, which the tests of the pack did not show. The most important: `repro` gave `STILL-FAILING` for a correct fix, because the two runs used one build directory, and the note for this case did not print with the output of the real tool. See the changelog.
- Limits: one more case, not a rate. The evaluator ran on a stronger model than Haiku. `memory.py mutants` did not run: the project has no mutation command in its committed gate file, thus the tool ran directly.

### A third use on a real project

A third change in the same Rust application (2026-11-18): no request of the session client goes to a host that is not trusted. It was the first use of the questions about the requirement, of the review sheet and of the JSON output.

- A subagent that had only the requirement wrote 7 criteria, 9 tests, 3 questions and 10 assumptions. The tests compiled at the first try: 6 failed on the base and 3 passed, as the subagent said. The first question was a contradiction in the requirement, which the author of the requirement did not see: an existing test needed the behaviour that the requirement stops.
- An agent could not answer the questions and could not confirm the tests. `repro --json` and `gate --json` gave the results without a read of terminal text. The independent evaluator ran 11 checks of its own and found no counterexample; it found a design defect (the refusal was read from the type of the error), which the author then corrected. `memory.py verdict` gave `SUPPORTED`, with the note that no person confirmed the tests.
- What this use does not show: that a person finds wrong tests with the review sheet. The owner of the project told the agent to record its own recommendations as the answers, and did not confirm the tests.
- The use showed 3 points to change in the pack: the evidence block did not show the answers, the sheet had 10 assumptions in no order, and an answer that permits a change of a test is not related to the warning for that change. The first two are changed. See the changelog.
- Limits: one more case, in the same project. Nothing ran with the real service.

### A fourth use, on a Python project

The first use that is not on Rust (2026-11-18): a Python repository of tests, with `unittest`, that is not ours and is not named here. A code review of an open pull request had a finding with no need of hardware: a generator script stopped in a correct case. The flow of the pack ran on a copy with no remote. No commit and no pull request was made.

- The pack ran with no change for Python. A subagent with only the requirement wrote 7 tests, 5 questions and 8 assumptions; it could run nothing, and it said correctly which test fails on the code of the pull request. `repro --json` gave `verified` in 1 second, with no build directory. `gate --json` passed with the 3 commands of the project that need no device.
- The independent evaluator ran 13 checks of its own and compared the change with the code before it. It found that the fix accepted a case that gave an error before. `counterexample` recorded it as a `regression`, and `memory.py verdict` gave `FAIL`: the first `regression` counterexample in a real use, and it was correct.
- The second version of the fix failed the gate: a check of the evaluator showed that it changed other behaviour. The third version passed, and the verdict was `SUPPORTED`.
- The 5 questions had no answer, because the person who can answer them was not there. The evidence block shows them under "Not verified".
- The use showed 3 points to change in the pack. (1) In a first use, the risk is HIGH each time, because the gate file is new and not committed, and the reason does not say "new gate file". (2) The pack runs the commands of a project with the PATH that it finds. This project sends commands to real devices, and the pack has no option to stop such a program; in this use, a script of ours replaced those programs with a command that fails. (3) The files of the evaluator count as changes outside the scope of the task.
- Limits: one case, with no device, on Linux only. The fix was not sent to the project.

### A test written from the issue, before the fix

The question: can a test that the `criteria` subagent writes from the text of the issue only replace the evaluator as the judge of a patch? The subagent wrote one test for each of the 42 hard issues, at the base commit, and saw no fix (Haiku, one pass, pack at commit `638c60f`). Then, with no model, each test ran on the base, on the base with the reference fix, and on the base with the patch of the bare agent (19 wrong patches, 23 correct patches). A test is valid when it fails on the base and passes on the reference fix.

| Measure | Result |
|---|---|
| Issues with a new test file and a command | 40 of 42 |
| Tests that fail on the base | 38 of 40 |
| Valid tests | 19 of 42 (45%, 95% interval 31 to 60%) |
| Tests that fail on the reference fix also | 19 |
| Wrong patches with a valid test: accepted | 6 of 6 (95% interval 61 to 100%) |
| Correct patches with a valid test: rejected | 0 of 13 (95% interval 0 to 23%) |
| Wrong patches rejected, of all 19 | 0 |
| Cost | 0.72 US dollars, 63 minutes to write, 12 minutes to check |

- The result is negative. No test rejected a wrong patch. The limit that we set before the run was a maximum of 6 of 19 wrong patches accepted. The run is at the limit only because 13 wrong patches have no valid test, thus no decision.
- The result is the same for each test case. 13 of the 19 wrong patches have a minimum of one test case that fails on the base and passes on the reference fix. Not one of these cases fails on the wrong patch.
- In 37 of 40 issues the patch and the reference fix have the same result. In the other 3, the wrong patch passes and the reference fix fails: the test has the same incorrect reading of the issue as the patch.
- A possible cause: these wrong patches repair the symptom that the issue shows. They fail on behaviour that the issue does not describe and that only the hidden tests of the maintainers check. A test from the same text, by the same model, confirms the symptom only.
- Half of the tests are not good criteria. 19 tests fail on the reference fix: they ask for more than the issue, or for an interface that the fix does not have. In a project, such a test stops a correct fix.
- What this means for use: a test before the change is a necessary check at a low cost. It is not a verdict. Do not show a green reproduction test as proof that a patch is correct.
- Limits: one pass. The authors of the patches did not see the test. Thus the run measures the test as a judge, not as a guide for the author. The same model wrote the tests and the patches; a different model is not measured. Hard issues only.

### The same test as a guide for the author

The run above measured the test as a judge. This run gives the test to the author: the bare agent (Haiku) has the test file in the repository and its command in the prompt, with the instruction that the change must make the test pass and that the test files must not change. 40 issues with a test, one pass, official grading. The comparison is with the patches of the selection run for the same issues (bare agent, no test), issue by issue.

| Group | Issues | Without the test | With the test | Wrong to resolved | Resolved to wrong |
|---|---|---|---|---|---|
| All | 40 | 21 (52%, 95% interval 37 to 67%) | 20 (50%, 95% interval 35 to 65%) | 1 | 2 |
| Valid test | 19 | 13 | 14 | 1 | 0 |
| Test that is not valid | 21 | 8 | 6 | 0 | 2 |

- The result is neutral: 21 resolved issues without the test, 20 with it (McNemar test, p 1.00). The limit that we set before the run was a minimum of 28. 37 of 40 issues have the same result.
- The 3 changes have the direction that we expected: the gain is on an issue with a valid test, and the 2 losses are on issues with a test that fails on the reference fix. 3 changes are in the noise between runs.
- No agent changed the test. The runs with the test cost less: 0.57 US dollars and 46 minutes of agent time, against 0.81 US dollars and 72 minutes.
- With the test, 9 sessions said that the work was not done, against 1 without it; 5 of the 9 had a correct patch. A part of this effect comes from the text of the prompt: some sessions read "do not change these test files" as "do not change a test".
- What this means for use: a test from the issue did not make the author correct more frequently on hard issues. It costs little, and it makes the session shorter. A test that is not valid can do harm, thus a person reads the tests of the criteria before the work.
- Limits: one pass. The comparison runs are from a different day, with the same model and the same harness. The same model wrote the tests and the patches. Hard issues only.

### More than one run of the evaluator (version 0.6.0)

The same 42 SWE-bench patches, the evaluator of version 0.6.0, 3 independent runs for each patch (126 runs, Claude Haiku).

| | Wrong patches approved (19) | Correct patches rejected (23) | No decision |
|---|---|---|---|
| Run 1 | 3 | 15 | 4 |
| Run 2 | 4 | 16 | 5 |
| Run 3 | 2 | 15 | 6 |
| 3 runs, the rule of the pack (PASS only if each run is PASS; FAIL if 2 runs are FAIL) | 1 (5%, 95% interval 1% to 25%) | 17 (74%, 95% interval 54% to 87%) | 8 |
| 3 runs, majority | 2 | 17 | 6 |

- The rule with 3 runs approved fewer wrong patches (1 of 19, against 2 to 4 with one run), and approved only 2 of the 23 correct patches.
- This evaluator does not separate wrong patches from correct patches on these issues. It gave FAIL in 41 of 57 runs on wrong patches (72%) and in 46 of 69 runs on correct patches (67%). The agreement with the official label is near zero (MCC from -0.01 to 0.16 for one run, 0.07 for 3 runs).
- It rejects more correct patches than the evaluator of the day before on the same patches: 15 or 16 of 23, against 9 of 23. The difference between the two versions is the merge-readiness step and the gate command in step 4.
- One pass without the merge-readiness step (same version, same 42 patches) did not isolate the cause. It rejected 12 of 23 correct patches (52%, 95% interval 33% to 71%) and approved 5 of 19 wrong patches. The difference from the 3 runs with the step (46 of 69 rejected) is not significant (Fisher exact test, p = 0.22). Without the step, the evaluator approved more patches of the two types (10 correct against 5, 5 wrong against 2 to 4), and the agreement with the official label did not change (MCC 0.14). Thus the step makes the evaluator more strict, not more accurate. Cost: 0.74 US dollars.
- The official label is a weak reference for a rejection: in the first calibration, 6 of 9 rejected "correct" patches had a real defect that the reference patch does not have. We did not repeat that check for these runs.
- One verdict is not stable: the 3 runs gave the same verdict for 25 of 42 patches. Two runs agreed on 29 to 32 of 42.
- No decision: 15 of 126 runs; 10 of them ended at the time limit of 600 seconds without a verdict line.
- Cost: 2.18 US dollars for 126 runs; one pass over the 42 patches took 141 to 168 minutes of agent time.
- What this means for use: with 3 runs and this rule, a PASS is rare and is wrong less frequently, and a FAIL has no information. Do not block a merge on a FAIL of this evaluator on a large repository.

### The review skills against the bare agent

The question: do the `code-review`, `security-review` and `triage` skills make the agent find more defects than the bare agent?

- **The cases.** A subagent that did not see the skills wrote small Python projects with seeded defects and an answer key. Each case also has code that looks wrong and is correct. Round 1 has 12 cases of about 80 lines. Round 2 has 4 cases of 540 to 740 lines in 7 files, and 3 of each 5 defects need two files.
- **The arms.** The bare agent, the bare agent with one skill in `.claude/skills`, and (round 2) the same with a prompt that tells the agent to read the skill and obey it. The model is Claude Haiku.
- **Round 1.** Code review: 12 of 12 defects found without the skill and 12 of 12 with it. Security review: 11 of 12 and 11 of 12. Triage: 4 of 4 correct decisions in each arm.
- **Round 2.** Bare agent: 37 of 40 defects (92%, interval 80% to 97%). With the skill: 35 of 40. With the skill and the prompt that points to it: 37 of 40. Wrong findings: 1 of 41, 1 of 38 and 0 of 38.
- **The review skills did not start.** The agent used `code-review` or `security-review` in 0 of 16 runs where the skill was only available. It used `triage` in 4 of 4 runs. With the prompt that points to the skill, it read the skill in 8 of 8 runs.
- **Claude Code has its own skills with the names `code-review` and `security-review`.** They are in the skill list of the bare agent. We do not know which one a call by name gets.
- **Conclusion.** On these cases the review skills do not change the number of defects found, because the bare agent is at the ceiling. The measurement says nothing about the form of the findings, about a large diff on a real project, or about a weaker model.
- Cost: 0.47 US dollars for 48 runs.
- Limits: seeded defects that a model wrote, one model, one or two repetitions, projects of 740 lines at most.

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

- Why the two pack arms resolved fewer hard issues than the bare agent, and the same comparison with a stronger model as the author or as the evaluator.
- The full cause of the higher rejection rate of the evaluator of version 0.6.0 (one pass without the merge-readiness step gave a result between the two versions).
- The defaults after version 0.8.0: the core install against the full install with an agent, a verdict that needs a record (`verdict_evidence` on) against the bare agent, As a judge of a finished patch, a test of the `criteria` subagent rejected no wrong patch, and as a guide for the author it did not change the number of resolved issues (see above).
- An evaluator on a model of another supplier. Sonnet in place of Haiku did not make the evaluator better (see above).
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
