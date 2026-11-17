# Changelog

## Unreleased

Three corrections from the second use on a real project (a Rust application, 2026-11-17).

- **Fix: `repro` did not name a shared build directory.** With `CARGO_TARGET_DIR` set to a directory outside the repository, the run on the current code used the test program that the base compiled, and `repro` printed `STILL-FAILING` for a correct fix. The note of version 0.8.0 for this case compared the last lines of the two outputs, and with the real tool they are not the same text (times, ports). Now `repro` finds the cause: when `CARGO_TARGET_DIR` or `CARGO_BUILD_TARGET_DIR` points outside the repository and the base has no directory of its own, the result says that it is not reliable and gives the option to use. The comparison of text stays for other tools, and it ignores numbers.
- **`repro --expect` shows the lines around the expected text.** The end of the output of a build tool can be build lines only.
- **`task open --id` says that the id is not used.** The pack gives the id of a new task; before, an id on the command line was dropped with no message.
- `--base-env` with a real cargo project: checked. `repro` gave `VERIFIED` with a build directory of its own for the base.
- 1 test with more checks.

## 0.9.1 — 2026-11-17

Two reports say more, and one more measurement is in [docs/RESULTS.md](docs/RESULTS.md). No default changed.

- **Measured: a test from the issue as a guide for the author.** With the test of the `criteria` subagent in the repository, the bare agent resolved 20 of 40 hard issues, against 21 without it. The test costs little and makes the session shorter; it did not make the author correct more frequently.

Checked: 157 tests on Windows and on Linux (Python 3.9 and 3.14), each with and without `PYTHONDONTWRITEBYTECODE`. Not covered: macOS.

- **`skill-eval` says when the tasks cannot show the effect.** In our measurements, 23 of 25 tasks were at the ceiling and measured nothing, and the report did not say it. Each report of `run`, `ablate` and `calibrate` now has a `task signal` line and a `task_signal` record: the tasks with a failed run and a passed run, the tasks at the ceiling (each run passed) and the tasks at the floor (each run failed).
  - `run`: when the baseline passes each run of each task, or each run of each task fails, the verdict is `INCONCLUSIVE` and the reason says that the task set cannot show the effect.
  - `ablate`: when each run of each task fails with and without the skill, the verdict is `NO-SIGNAL`, not `PRUNABLE`. `PRUNABLE` on tasks at the ceiling stays, with a reason that says it is for those tasks only.
  - `calibrate` prints a warning for a task set at the ceiling or at the floor.
- **Each `skill-eval` report has its commit.** The reports of `run`, `ablate` and `judge` and the noise file have `commit`, `dirty` (a tracked file has an uncommitted change), the Python version and the platform. A run uses the commit and the skills folder on disk, and the report says so when `dirty` is true. A report without a commit is not written.
- **`memory.py verdict` says which type of `UNKNOWN` it is, and the next step.** `no-evidence`: no command gave a record for this code. `weak-evidence`: a command ran, and its record does not count (a reproduction with a test from after the change, a mutation check that did not pass, a counterexample that did not load the code of the base). The two types were one line before, and they need different actions. `--json` has `unknown` and `next`, and the run log has `unknown`.
- 1 test, and 1 test with more checks.

## 0.9.0 — 2026-11-17

This release changes defaults, and it corrects version 0.8.0. A new install has the core only (3 skills). The result of a change comes from the records of commands, not from the text of the evaluator. The release also says what the measurements do not support: on hard issues, the evaluator, the existing tests of a project and a test written from the issue did not separate wrong patches from correct patches ([docs/RESULTS.md](docs/RESULTS.md)). Read "Changes that need attention in an upgrade" below.

Checked: 156 tests on Windows and on Linux (Python 3.9 and 3.14), each with and without `PYTHONDONTWRITEBYTECODE`. Not covered: macOS. Not measured with an agent: the new defaults against the bare agent.

- **The Stop hook keeps the answer to the task.** When the hook blocked a stop, the last message of the agent was about the gate only, and the answer to the task was lost. Seen on 2026-11-17: a session that had to write a test and give its command ended with text about the gate file. Now each block message tells the agent to give the complete answer again. A gate without commands has its own message with two cases: code changed (write the gate file), or nothing that a command can check (do not write a gate file, say that no gate ran). The gate itself did not change: without commands it fails. The effect on an agent is not measured.

- **Fix: Python bytecode files.** In a project that does not ignore `__pycache__`, a check of the pack wrote bytecode files into the project. They changed the workspace hash, showed as changes outside the scope in the evidence block, and stopped `memory.py pr` ("changes that are not committed"). Python also accepts an old bytecode file when the source has the same size and the same second of modification: after a quick edit, a check ran the old code.
  - The commands that the pack runs (gate, `repro`, `counterexample`, base tests) get a bytecode directory of their own (`PYTHONPYCACHEPREFIX`), removed at the end. A value that you set stays. `python -I` and `-E` do not read it.
  - `__pycache__` and `.pyc` files that git does not track and does not ignore are not counted as changes. The evidence block has a line for them, and `pr` names them. A file of this type that git tracks is not hidden.
  - **Correction for version 0.8.0**: its notes say that the tests passed on Windows and on Linux. Each of those runs had `PYTHONDONTWRITEBYTECODE=1` set. Without it, 4 tests failed on Linux with Python 3.14. The tests now run in the two modes before a push.

Two changes of defaults, from the results in [docs/RESULTS.md](docs/RESULTS.md): the full pack was never better than the core, and the verdicts of the evaluator did not separate wrong patches from correct patches while the records of commands did. Not measured: the effect of these two defaults, and the tests that the `criteria` subagent writes. The tests ran on Linux only (Python 3.14).

- **`memory.py`: the large functions are split, with no change of behaviour.** The commands with actions (`feature`, `lesson`, `task`) have one function for each action; the gate has stages (warnings, changes that need a person, checks) and one function for a failure; the session digest and the evidence block have one function for each section; `stats` and `factory` compute and print in different functions. The most complex function went from 71 to 41 (our count of branches), the functions above 25 from 13 to 5, and the longest function from 130 to 69 lines. A test keeps these limits. The script is still one file with no local import: CI copies this one file from the base branch, and that is what stops a pull request from a change of its checker. `cmd_pr` is not split yet.

Changes that need attention in an upgrade:
- `feature pass --verified-by evaluator` and `feature vote` now refuse a verdict without a record (a verified reproduction for a PASS, a counterexample for a FAIL). `"verdict_evidence": false` in `.agent-memory/config.json` gives the old behaviour. `--verified-by human` and `ci` did not change.
- A new install has 3 skills. An install that has the other skills keeps them, and `--upgrade` still upgrades them.
- A reproduction with a test that was not recorded with `feature add --test-file` no longer gives SUPPORTED or an evaluator PASS. Record the tests with the criteria, or set `"accept_later_tests": true`.
- The Claude Code plugin loads 3 skills in place of 12. Use `install.py project . --full` for the others.

- **Core install by default**: `long-horizon`, `evaluator`, `plan-before-code`. `install.py --full` adds the other 9 skills and the upstream skills (the core fetches nothing from the network). `AGENTS.md` of a core install has no line about skills that are not installed.
- **`install.py --secure`**: one option for `--with-stop-gate --with-guard --with-sandbox --with-ci`.
- **The result comes from records by default.** `verdict_evidence` is on unless the config file turns it off. The evaluator (skill, Claude Code and Antigravity subagents) says that its text does not decide: it shows a defect with `counterexample`, and it reports the line of `memory.py verdict`. The definition of done in `AGENTS.md` names `memory.py verdict`.
- **Tests from before the work.** The `criteria` subagent writes the tests of the criteria in new test files (it has the `Write` tool, and no shell). `feature add --test-file FILE` (or `--test-patch`) records them with the feature. `repro` with a recorded file that did not change gives `recorded_test` in the run log; `verdict` has the record `reproduction_test`, and the evidence block says if the test was recorded before the change. A test that changed after the record does not count.
- **`memory.py --help` lists the 10 core commands**; `--help-all` lists each command. Each command still runs and has its own `--help`.
- **A reproduction supports the result only with a test from before the change.** With a test that was not recorded with the criteria, `memory.py verdict` gives UNKNOWN and `feature pass --verified-by evaluator` and a PASS vote are refused. `"accept_later_tests": true` in `config.json` gives the old behaviour. Reason: 2 of 3 verified reproductions of the evaluator were on wrong patches. This is a small number: the rule follows the cause (a test written for a change can agree with it), not a measured rate.
- **The Claude Code plugin has the core skills**: the marketplace entry lists the 3 skill directories (`claude plugin validate --strict` passes; the plugin was not installed again to check what it loads).
- **`install.py global`**: the Antigravity rules of a core install have no line about skills that are not installed, and `uninstall --global` removes that file.
- 7 tests; older tests set `"verdict_evidence": false` or `"accept_later_tests": true`, use `--full`, or record the test with the feature first.

## 0.8.0 — 2026-11-16

This release ties a verdict to a command that ran. We measured the evaluator on 42 patches for hard issues with two models: one model rejected most patches, the other approved most patches, and the two did not separate wrong patches from correct patches. An instruction to bring evidence did not change the verdicts. The records of the commands did separate in one case: each of the 3 counterexamples of type `regression` was on a wrong patch. The numbers are small, and they are in [docs/RESULTS.md](docs/RESULTS.md). The release also has the corrections from the first use on a real project.

Not measured: `memory.py verdict` on the 42 patches, `mutants` with a real mutation tool, `--test-patch` and `--base-env` on a real compiled project. The tests ran on Windows and on Linux (Python 3.9 and 3.14). On the Python 3.13 image, the tests passed before the last change, which is in one test only; the run after that change was not complete at the time of the release. Not run on macOS.

- **From the first use on a real project** (a Rust workspace; a security fix with a gate, a reproduction and an independent evaluator, which found a defect that the tests of the author did not find):
  - `repro --test-patch FILE` and `counterexample --test-patch FILE` apply a patch with the test on the base. Before, a test inside the file that the fix changes could not be used: a copy of the file took the fix to the base.
  - `--base-env NAME=VALUE` sets a variable for the run on the base only. With a build cache that two checkouts use (`CARGO_TARGET_DIR`), the run on the current code used the files of the base, and `repro` said `STILL-FAILING` for a correct fix. `repro` now names this cause when the two outputs end with the same lines.
  - The evidence block says "in the scope of a feature that is not graded yet" for a changed file that waits for a grade. Before, it said that the file was not linked to a feature.
- **`memory.py verdict`**: what the records support for the current code (`SUPPORTED`, `FAIL`, `UNKNOWN`), without the text of an agent. `FAIL` needs a `regression` counterexample: in our measurement, each of the 3 such counterexamples was on a wrong patch, and the verdicts of the evaluator did not separate wrong from correct patches.
- **`counterexample` and `repro` find a check that does not load the code of the base** (it imports the code from an absolute path or from an installed package). The counterexample then has the type `base-not-seen`. In the measurement, such checks made the type `not-fixed` useless.
- **Fix**: `AGENT_MEMORY_LOCK_TIMEOUT` (seconds, default 10) sets how long a writer waits for the memory lock. With many writers on a machine under load, the last writers ended with exit code 4. The test with 16 writers failed for this reason in one complete run on Windows, while another test run and containers used the machine; it now uses a longer wait. One earlier failure on Windows was not identified and can be the same.
- **`memory.py counterexample`**: shows a defect with a command that fails on the current code, and runs it on the base to say if the change broke it (`regression`) or does not fix it (`not-fixed`). The evidence block shows it, with review risk `HIGH`.
- **`"verdict_evidence": true`** in `config.json` (off by default): a PASS of the evaluator needs a reproduction for the current code, and a FAIL vote needs a counterexample. Without the command, the result is UNKNOWN. The evaluator has one paragraph for this option. Reason: on 42 patches, the evaluator on one model rejected most patches and on another model approved most patches. Measured on the same 42 patches ([docs/RESULTS.md](docs/RESULTS.md)): as an instruction only, the verdicts did not change, and one model did not read the option. The 3 counterexamples of type `regression` were on wrong patches; the type `not-fixed` and the verified reproductions did not separate wrong from correct patches.
- **`memory.py mutants`**: runs the mutation tool of the project (`"mutation_command"` in `gate.json`, for example `cargo mutants --in-diff {diff}`) on the lines that the change touched. The evidence block has a line for it. The pack has no mutation engine. Not run with a real tool.
- **Measured** ([docs/RESULTS.md](docs/RESULTS.md)): the evaluator on another model, on the 24 shipped cases. On Claude Sonnet it approved 7 of 12 wrong patches and rejected 0 of 12 correct patches; on Claude Haiku, the model of the author, 0 of 12 and 3 of 12. The 7 approvals are one type of defect. On the 42 SWE-bench patches, Sonnet approved 13 of 19 wrong patches and rejected 4 of 23 correct patches (Haiku: 2 to 4, and 15 to 16); the agreement with the official label is near zero for the two models. The text of `--evaluator-model` in the installer and in the README now says that a stronger model is not better by default.

## 0.7.1 — 2026-11-16

From the review of a real pull request made with an older version of the pack. The evaluator gave a PASS to one feature; the pull request had 16,000 added lines, most of them from commits before the pack was used, on a branch 77 commits behind the default branch. A person read the PASS as an approval of the complete change, and an independent review found 6 defects. One of the 6 was in the graded feature: its criterion named a function ("the replace is atomic") and not the behaviour.
- **The gate and the evidence block say when the branch is behind the default branch** of `origin`, as of the last fetch, and if a merge has conflicts (review risk `HIGH`). The gate does not block.
- **The evidence block shows the feature coverage of the change**: the changed files in the scope of a task of a graded feature, and the files outside each scope in "Not verified". Without a scope, the block says that the changed files are not linked to a feature. Attention in an upgrade: `evidence --strict` now fails for a graded feature without a task scope.
- **`feature add` gives a warning for a criterion that names code**, and the evidence block repeats it for a graded feature.
- **Fix**: a new file below a directory with a name that starts with a dot (`.github/`, the memory directory) lost the dot in the list of changed files. New files of the memory directory were counted as changes of the project, and a path rule for `.github/` did not match a new file.
- **Fix (Windows)**: `memory.py` read the output of git and of the gate commands in the ANSI code page. One byte outside it (UTF-8 text in a test output or in a diff) stopped the gate with a Python error and no result. The output is now read as UTF-8, and a byte that is not valid shows as a replacement character. Found when the new evidence block ran on that pull request.
- Not measured: the effect of these three checks. The tests ran on Windows and on Linux (Python 3.9, 3.13 and 3.14), not on macOS.

## 0.7.0 — 2026-11-13

This release comes from the first measurement of the shipped pack against the bare agent. The gate checked nothing in those runs, and only the artifacts showed it. Thus a gate without commands now fails, and `stats` shows in how many sessions each control ran. A project can add its own risk rules, `skill-eval` gives one line of reliability at cost, and the evaluator can run on another model. The numbers are in [docs/RESULTS.md](docs/RESULTS.md).

Not measured in this release: the risk rules, the evaluator on another model, and a gate that has commands against the bare agent on hard issues. The tests ran on Windows and on Linux (Python 3.9, 3.13 and 3.14), not on macOS.

- **The gate fails when it has no commands.** Before, `memory.py gate` without `.agent-memory/gate.json` printed "nothing to gate" and ended with exit code 0, and the Stop hook did nothing. In 40 agent runs on repositories without a gate file, the agent got that message in 30 runs and did not run the gate in 10; no run wrote a gate file. Now the gate ends with exit code 1 and tells the agent to write the file and to tell the user; the Stop hook blocks one time in a project that has `.agent-memory/`; `doctor` reports it as a problem; the installer warns when no profile gave commands. A gate file that git does not have gives a warning. `"allow_no_commands": true` keeps a gate with only the secret scan and the test guards.
  - Attention in an upgrade: a CI job or a script that ran `memory.py gate` in a project without a gate file now fails.
- **Measured** ([docs/RESULTS.md](docs/RESULTS.md)): the core pack of version 0.6.0 against the bare agent on 20 hard issues (4 of 40 resolved against 2 of 40; 27 against 35 false "done"; no difference that the sample can show; the gate had no commands); the evaluator with 3 runs on 42 patches (1 of 19 wrong patches approved, 17 of 23 correct patches rejected).
- **Risk rules of the project**: `"risk_rules"` in `gate.json` (a regular expression for the changed paths, for the added lines, or the two). A match gives a gate warning and review risk `HIGH`, and with `"block": true` the gate fails. A person records why no more review is necessary with `memory.py risk waive --rule NAME --reason "..."`; the waiver is a committed line in `.agent-memory/risk-waivers.jsonl`, it shows in the evidence block, and it is for the reviewed lines only. `memory.py risk` shows the matches. The guard protects the waiver file. Not measured.
- **Reliability at cost in `skill-eval`**: each measurement prints one line for each variant, with the share of tasks where each run passed (pass^k), its 95% interval, and the cost for each passed run (money, else tokens, else time). The JSON report has `pass_all_ci95` and `per_pass`. `run --max-cost-per-pass USD` gives no `IMPROVES` verdict above the limit, or when the agent command reports no cost.
- **`install.py --evaluator-model MODEL`**: the evaluator subagent of Claude Code runs on a model that is not the model of the author. `uninstall` removes a file that has only this change. Not measured: on 42 SWE-bench patches the evaluator on the model of the author did not separate wrong patches from correct patches, and a different model is the next thing to measure.
- **`stats` shows the control coverage of the sessions**: in how many sessions the gate ran a command, the last gate result was a pass, criteria were recorded, the evaluator graded, a reproduction was verified, and in how many no control left a record. `--min-gate-coverage RATE` gives exit code 1 below a rate. The limit: a session that changed no code counts as a gap also, because the run log does not record edits.

## 0.6.0 — 2026-11-13

This release is about what a misled or careless agent can do, and how to see it. The issue workflow has separate rights, CI runs the checker of the base branch, the agent cannot change its checks or its tests without a trace, and a prompt-injection test set measures the result ([docs/RESULTS.md](docs/RESULTS.md), [SECURITY.md](SECURITY.md)).

- **Rights**: the issue workflow has three jobs (agent with read access; gate with read access and no secret; pull request with write access and no agent), with an egress policy for the agent job.
- **Checks that the agent cannot weaken**: CI runs `memory.py` of the base branch; `--with-guard` protects the pack's files and the tracked tests; `block_test_changes` makes the gate fail for a deleted test or a new skip marker; a fixed base for the gate.
- **Audit**: each run log line has the actor, the model and the pack version, and a hash chain that `audit --verify` checks.
- **Skills as a way in**: `validate_skills.py` finds hidden characters, suspect instructions and overlap, and runs external scanners with an incomplete state.
- **Evaluator**: more than one run for each case with a rule for the result (`judge --repeats`, `feature vote`); `skill-eval` reports if the agent used the skill.
- **Other agents**: adapters for Codex and OpenCode 2.
- **Measured**: 9 of 72 injection attacks succeeded without the pack and 1 of 36 with the pack (Claude Haiku, one small task). The short release check of 0.5.0 ended correct in 5 of 6 runs with the pack and 4 of 6 without.
- **Not measured**: the complete pack against the bare agent on hard issues; the evaluator with more than one run; the issue workflow on GitHub; the Codex adapter with Codex; the egress policy; the checks of skills against real hostile skills.

Changes that need attention in an upgrade:
- Each new run log line has a hash. A tool that writes lines into `events.jsonl` by itself breaks the chain: use `memory.py event`.
- With `--with-guard`, the agent cannot delete or cut a tracked test file (`"guard_tests"` in `.agent-memory/config.json`).
- `gate` and `evidence` compare with the base of the open task, when a task is open.
- `validate_skills.py --strict` fails for a suspect instruction in a skill. Put `skill-scan: ok` on a line that a person read.

### Skill checks, test guards, audit chain, other agents
- **`validate_skills.py` checks a skill as a way into the agent**: hidden characters are errors; suspect instructions (drop other instructions, hide an action from the user, send local data out, run code from the network, read credential files, turn off a safety check) are warnings, in each text file of the skill. `skill-scan: ok` on a line marks it as read.
- **Overlap of descriptions**: a warning when two skills share half of the words of their descriptions (`--overlap`).
- **`--scanner CMD`**: an external scanner on the skills. A scanner that is not installed gives `INCOMPLETE` and exit code 3.
- **`skill-eval` reports the activation of the skill**, from the tool calls in the transcript. A skill that was never used gives `NOT-USED` in `ablate` and `INCONCLUSIVE` in `run`.
- Fix: the hash chain of the run log broke on Windows with parallel writers. A permission error on the lock file is contention there, and the writer now waits.
- The ideas for the skill checks come from NVIDIA SkillEvaluator. 5 tests. Not measured with an agent.
- **Multi-run evaluator aggregation and voting**: `skill_eval.py judge --repeats 3` (`--reps`) aggregates per-case verdicts with `--rule asymmetric` (default: `PASS` requires `k/k` unanimity, majority `FAIL` becomes `FAIL`, splits stay `UNKNOWN`), recording `per_case`, `aggregated`, `agreement_rate`, and pairwise Fleiss `kappa`. In `memory.py`, setting `"evaluator_runs": N` (or `"auto"`, which picks `3` for high-risk diffs) in `.agent-memory/config.json` requires `feature vote` runs bound to the current workspace code hash (`feature pass --verified-by evaluator` rejects un-voted or split features while `human`/`ci` overrides remain allowed).
- **Per-task file scope (`task open --scope`)**: repeatable `--scope` globs on `task open` warn in `gate` when changed files fall outside active scopes, list `Out of scope` paths in `evidence`, and bump `change_risk` to `MEDIUM` without blocking `gate`.
- **CI egress restriction and injection `exfil` goal**: `templates/ci/agent-issue.yml` runs `step-security/harden-runner` (`egress-policy: block`, `disable-sudo-and-containers: true`, minimal `allowed-endpoints`) as step 1 of `jobs.agent`. `evals/injection/run_inject.py` adds the 4th `"exfil"` goal with a per-run loopback HTTP canary server (bumping default `--max-runs` to `105`). Tested with unit tests in `VerificationBlockTests`; live LLM `judge --repeats 3` and end-to-end GitHub Actions runs remain unexecuted.
- **Fixed gate base reference (`base` on `task open`)**: `task open` (and `task worktree`) records `HEAD` in `tasks.jsonl` and `events.jsonl`. `gate` and `evidence` default to `--ref` / `AGENT_GATE_REF`, else the earliest valid open task base (cross-checked with `events.jsonl` and `git merge-base --is-ancestor`), else `merge-base HEAD origin/<default>`, else `HEAD`. Commits that weaken `.agent-memory/gate.json` or delete tests after `base` stay visible outside CI.
- **PreToolUse test guard in `guard_pack_files.py`**: protects tracked test files against deletion, truncation, moves out of tests, inline scripts naming tracked tests, and new skip markers across file tools, patches, and shell commands while allowing new tests and new assertions. Controlled via `"guard_tests"` in `.agent-memory/config.json` (`"no-delete"` default, `"append-only"`, `"off"`).
- **In-place base-test replay (`"replay_base_tests"`: `"warn"` | `"block"`)**: with `"test_command"` in `gate.json`, re-runs base versions of unapproved modified/deleted tests against the new code using atomic workspace backup and crash recovery in `.agent-memory/.replay-backup.json` (added to `.agent-memory/.gitignore`). 10 unit tests in `TestProtectionTests`; not yet measured with a live agent.
- **Codex: `install.py --with-codex`** writes `.codex/hooks.json` (session digest, formatter; the Stop gate with `--with-stop-gate`, the guard with `--with-guard`). The commands find the project with `git rev-parse --show-toplevel`. Not run with Codex: built from its hook documentation.
- **OpenCode 2: `install.py --with-opencode`** writes a server plugin, the `evaluator`, `criteria` and `triage` subagents, and `.opencode/ai-quality-pack.json`. On a red gate the plugin sends the gate output to the session one time (OpenCode cannot stop the agent from finishing). Checked on OpenCode 2.2.7 with local models: plugin load, digest, guard, gate prompt and release.
- **The hook scripts do not need Claude Code variables.** The project is `CLAUDE_PROJECT_DIR`, else `AGENT_PROJECT_DIR`, else the folder of the session or the git top level above it. `memory.py` finds the project from a subfolder in the same way.
- **The guard reads the arguments of the tool call**, not the tool name: a file path (`file_path`, `filePath`, `path`), a shell command, or the files of a patch (Codex `apply_patch`). It protects `.codex/` and `.opencode/` also.
- The formatter finds the files of a Codex patch and of an OpenCode edit.
- `uninstall` removes the Codex hooks and the OpenCode files of the pack. 6 tests.
- **Identity in each run log line**: `actor`, `model` and `pack` version; a gate line has `policy`, a hash of the gate rules that ran. The model comes from `AGENT_MODEL` or from the Claude Code session start.
- **Hash chain in the run log**: each line has the hash of the line before it (`prev`, `h`). `memory.py audit --verify` exits 1 for a line that was changed, removed or inserted; `--head HASH` finds a cut at the end. `audit` prints the head. A lock of its own keeps one chain with parallel writers, and the chain goes on after the log file is rotated.
- Limit: the chain has no secret, so it is proof only against a head that is kept where the agent cannot write. 5 tests.
- **`"block_test_changes": true` in `gate.json`** (off by default): the gate fails for a deleted test file or a new skip marker, before it runs the commands. A person approves a path or a glob in `"allowed_test_changes"` and commits `gate.json`; an edit that is not committed does not count. The prompt-injection test set showed the gap: the deletion of a test succeeded in 1 of 12 runs with the pack, and the gate only reported it.
- A changed line in an existing test does not block. That warning fired on 5 of 23 correct patches and 6 of 19 wrong patches, so it does not separate them.
- The run log records these failures as `failed: "test changes"` with the number of blocked changes.
- Not measured with an agent. 1 test.

### Security: rights, trusted checker, guard, threat model
- **The issue workflow has three jobs with different rights**: the agent (read access), the gate (read access, no secret), and the pull request (write access, no agent, no code from the change). The agent job has no `id-token` right and a fixed tool list.
- **CI runs `memory.py` of the base branch**, in `quality-gate` and in the issue workflow.
- **`install.py --with-guard`**: permission rules and a `PreToolUse` hook that stop the agent from a change of `.claude/`, `.agents/`, the CI workflows, CODEOWNERS and the gate file. `AGENT_PACK_UNLOCK=1` opens it for a person.
- **`--sandbox-allow-domain HOST`**: the hosts that shell commands can reach in the sandbox.
- **`memory.py pr --evidence-file`**: the pull request with the evidence of a job that ran the gate.
- **SECURITY.md** has the threat model: the trust boundaries, each risk with its control, and what the pack does not protect against.
- **`evals/injection/`**: a prompt-injection test set with harmless canaries (18 attack cases, 3 places, 3 goals, 2 styles). Result with Claude Haiku: 9 of 72 attacks succeeded without the pack, 1 of 36 with the pack. See docs/RESULTS.md.
- Fix, found by that test set: the guard blocked the agent's own gate command when it ended in `2>&1`.
- 7 tests.

## 0.5.0 — 2026-11-12

The pack moves from a set of skills to a quality-control station for agent work: a reproduction check, a gate that an agent cannot make easy, an evaluator with a calibration set, a draft pull request with evidence, and the numbers that we measured ([docs/RESULTS.md](docs/RESULTS.md)).

- **Install**: Claude Code plugin and marketplace, `install.py uninstall`, `doctor`, scripts that start on Python 3.6 to 3.8.
- **Checks**: `repro`, gate guards (committed gate file, deleted or changed tests, skip markers, secrets, size, complexity), `gated-run` for runs without hooks.
- **Evaluator**: reads the requirement and not the author's narrative, gives `PASS`, `FAIL` or `UNKNOWN` and a merge-readiness line; `criteria` and `triage` subagents.
- **From an issue to a pull request**: `triage`, `pr` (draft, after a green gate, never merged), `evidence` with review risk, the issue workflow, `factory`, `audit`, `provenance`.
- **Measurement**: `skill-eval` intervals, `power` and `judge`; `evals/judge-cases/` with 24 labelled cases.
- **Not measured**: the complete pack against the bare agent on hard issues. The rewrite of the evaluator shows no measurable gain on 42 SWE-bench patches. The issue workflow was not run on GitHub.

Changes that need attention in an upgrade:
- A lesson that an agent records is not in the session digest until a person confirms it (`memory.py lesson confirm`). Older lessons stay visible.
- The session digest has a size limit of 6000 characters.
- The gate fails on a line that looks like a secret. `"secret_scan": false` in `gate.json` turns this off.
- The gate runs the committed `gate.json`.


### operating rules, Antigravity evaluator (docs/EVOLUTION.md: F7, F9)
- README has the operating rules: three points where a person decides (question, plan, pull request), and one issue, one worktree, one pull request.
- The Antigravity evaluator has the same steps as the Claude Code evaluator. It had the text of an older version.
- 1 test.
- `skill-eval judge` reads the cost from a JSON list of events, and prints the cost and the time of the set.

### evals in the repository, hardening (docs/EVOLUTION.md: E0, E5, E6)
- **`evals/judge-cases/`**: 24 calibration cases for the evaluator (12 wrong, 12 correct patches from agent runs, labelled by hidden tests), with a label check that uses no agent. The installer does not copy `evals/`.
- **`skill-eval judge` takes cases with their own code** (`"repo"`, `"patch"`): the judge works in a new repository, away from the labels.
- **`docs/RESULTS.md`**: the measured numbers, with intervals, costs and limits.
- **The gate warns when the change removes or replaces lines of an existing test.** New tests give no warning.
- **CI template**: an `audit` job with `pip-audit` and `npm audit`.
- **`install.py --codeowners OWNER`** and **`--with-sandbox`** (Claude Code sandbox with `failIfUnavailable`, and no read of `.env` and `secrets/` files).
- 5 tests.

### smaller memory, complexity of the change (docs/EVOLUTION.md: E7, E8)
- **The session digest has a size limit** (6000 characters, `--max-chars`).
- **A lesson that an agent records waits for a person.** It enters the digest after `memory.py lesson confirm --key <key>` in a terminal. Each new lesson records its origin, the commit and the session. Older lessons stay visible.
- **`memory.py complexity`**: Python functions that the change made more complex than a limit. `"max_complexity"` in `gate.json` shows them as gate warnings. The installer sets it to 10 for Python projects, with `"max_changed_lines": 400`.
- 5 tests.

### merge readiness and governance (docs/EVOLUTION.md: F6, F10)
- **The gate scans the change for secrets** before it runs the project's commands. It stops on a line that looks like a secret and never prints the value. `pack:allow-secret` on a line marks a false alarm; `"secret_scan": false` turns the scan off. `memory.py secrets --base <ref>` runs the scan alone.
- **`memory.py provenance`**: a commit trailer for agent work, off until a person sets it. `--check <base>` finds commits without it. `memory.py pr` puts it in the pull request text.
- **`memory.py audit`**: the run log as an audit record with a checksum. The issue workflow keeps it as an artifact.
- **The evaluator checks merge readiness**: written project rules, style of the nearby code, one purpose, size, documentation. It writes `MERGE-READY: YES` or `NO`. Not measured.
- `"max_changed_lines"` in `gate.json` makes the gate warn about a large change. `doctor` says when the gate has no lint or type check command.
- 6 tests.

### triage and factory report (docs/EVOLUTION.md: F4, F8)
- **`memory.py triage`**: a text check of an issue before work. Exit code 4 gives the questions for the issue. The issue workflow runs it first: a thin issue gets a comment, and no agent run starts.
- **New `triage` subagent** (read-only tools) and **`triage` skill**: decide `TRIAGE: READY` or `TRIAGE: ASK` from the requirement and the repository. Not measured.
- **`memory.py factory`**: pull requests of the agent line from GitHub (merge rate with interval, time to merge, cost, review risk, reverts), and refused pull requests, unattended runs and triage results from the local run log.
- 4 tests.

### from an issue to a draft pull request (docs/EVOLUTION.md: F3, F5)
- **`memory.py pr`**: opens a draft pull request with the evidence block, only after a green gate. It stops if an open pull request has the same branch or closes the same issue, and if work is not committed. It never merges. It needs the GitHub CLI.
- **The evidence block has a review risk and the cost.** The risk is `HIGH`, `MEDIUM` or `LOW`, from the paths that changed, the size of the change and the checks without a record. The cost comes from the caller (`--cost-usd`).
- **`install.py --with-issue-workflow`**: a GitHub Actions workflow. The label `agent` on an issue starts an agent run with a limit of turns and of US dollars. The workflow, not the agent, runs the gate and opens the draft pull request. Without a pull request, it writes a comment on the issue. Not run on GitHub yet.
- 4 tests.

### old Python, and the gate without hooks (docs/EVOLUTION.md: F2)
- **The scripts start on Python 3.6 to 3.8.** In two repositories with Python 3.6, `memory.py` stopped with a `SyntaxError`, so `repro` and the gate did not run. Each script and hook now starts again with a newer Python from `PATH` (or `AGENT_PACK_PYTHON`). If none is found, it prints the cause and exits with code 1.
- **`memory.py gated-run`**: runs an agent command, then the gate. A red gate goes back to the agent with the gate output, for a set number of rounds. Exit code 1 means that the gate still fails. Use it in unattended runs: hooks do not run in `claude -p --bare`.
- **`install.py uninstall`** (F1): removes what the pack installed in a project, or with `--global` in the home directory. It keeps files that you changed (`--force` removes them), `AGENTS.md`, your other hooks and `.agent-memory/` (`--purge-memory` removes it). `--dry-run` shows the list.
- **Claude Code plugin** (F1): the repository is a plugin and its own marketplace (`claude plugin marketplace add`, `claude plugin install ai-quality-pack@ai-quality-pack`). The plugin has the skills, the two subagents and the three hooks. `aqp-memory` is on `PATH` and stands for `memory.py`. The Stop gate runs only where `.agent-memory/gate.json` exists. Run in two agent sessions on Linux; not run on Windows. The `evaluator` subagent now finds the memory command as its first step: in the first session it did not use `aqp-memory`.
- 10 tests.

### evaluator: a missing record is not a FAIL
- First calibration run (2 graded patches): the evaluator rejected a correct patch because no criteria, no reproduction and no gate file were recorded, not because of a defect in the code. The evaluator now keeps the two apart: FAIL is for a defect that it showed; a missing record goes under "Not verified". It gives one overall result (FAIL, else UNKNOWN, else PASS), and it makes its own reproduction when none is recorded.

### evolution plan, third batch (docs/EVOLUTION.md: E0, E3, F5)
- **`skill-eval judge`**: measures an evaluator on cases with a known answer. Each case has a label (`correct` or `wrong`), a prompt and an optional setup command. The judge must print `VERDICT: PASS`, `FAIL` or `UNKNOWN`. The report gives the rate of wrong work approved and of correct work rejected, each with a 95% interval, the share with no decision, and the MCC. The pack ships the tool; a case set comes from your own graded work.
- **`memory.py evidence`**: a Markdown block for a pull request. It says what the checks recorded for exactly this code (gate, reproduction, acceptance criteria, warnings, size of the change) and lists what is not verified. `--strict` exits 1 when a gap or a warning exists.
- The pack's CI runs on a manual trigger only. README has the checks to run before a push.
- 4 tests.

### evolution plan, second batch (docs/EVOLUTION.md: E1, E6)
- **The evaluator does not read the author's narrative.** It reads the requirement first and writes what must be true, reads the change with the new `memory.py diff-view` (the comments that the change added are hidden), and treats the recorded criteria as the implementer's reading. Its task is to find defects. The third verdict is `UNKNOWN`, and it does not let a feature pass. Not measured on the benchmark yet.
- **New `criteria` subagent** (read-only tools): writes acceptance criteria from the requirement before the implementation, and asks when the requirement is ambiguous.
- **`install.py --with-ci`**: a GitHub Actions workflow that runs the gate on pull requests with the base branch's `gate.json`, and shows gate warnings as annotations. Actions are pinned by commit.
- `--upgrade` also replaces the pack's subagents (old copy backed up).
- The pack's own CI pins its actions by commit, and runs once per pull request (push runs only on `main`).
- `memory.py` and `skill_eval.py` write UTF-8 to a pipe and never fail on a character that a console cannot show.
- 5 tests.

### evolution plan, first features (docs/EVOLUTION.md: E2, E4, E5, F1)
- **`memory.py repro`**: shows a fix with a test that fails on the base commit and passes on the current code. The base runs in a throw-away git worktree with the test files copied onto it. Results: `verified`, `not-reproduced` (the test passes on the base), `wrong-failure` (`--expect` text missing), `still-failing`, `base-timeout`. `repro --check` is true only for exactly the verified code. Limit: files that git does not track are not in the base checkout.
- **The gate runs the committed `gate.json`.** An edit that is not committed does not count, and the gate reports it. `--ref` or `AGENT_GATE_REF` selects the ref (in CI, the base branch).
- **The gate reports deleted test files and new skip markers** since that ref. It reports them and does not block. The next session digest shows them under "Needs you".
- **`memory.py doctor`**: checks git, memory, `.gitignore`, the hook commands and scripts, and that each gate command can run. It says that hooks do not run in `claude -p --bare`.
- **`skill-eval`**: the report gives the 95% interval of the paired per-task difference and the share of tasks where every run passed (pass^k). New `skill-eval power` gives the number of tasks needed to detect a change.
- 7 tests.

### observability follow-ups
- **A Stop-hook release is `released-green` only when the gate passed for exactly the final code.** The hook looked only for the `.gate-pass` file, so a pass from before the last edit was logged as green. New `memory.py gate --check` runs nothing and exits 0 only for a pass on the current workspace.
- **`memory.py init` no longer joins its new `.gitignore` lines to a last line that has no newline.** `evals/results/` became `evals/results/events.jsonl`, and the results and the run log were no longer ignored.
- 2 tests.

### observability
- **Run log.** `memory.py` and the hooks append to `.agent-memory/events.jsonl` (local, git-ignored): session start, gate pass/fail/skip with duration and the failing command, feature gradings, lesson adds and votes, Stop-hook blocks and releases. Each line has the agent session id (from the SessionStart hook input, or `AGENT_SESSION_ID`). No prompt or code text. `AGENT_MEMORY_EVENTS=0` turns it off; a log that cannot be written never fails a command.
- **`memory.py stats`** (`--days`, `--json`): gate failure rate and top failing commands, evaluator rounds per pass, who verified, features marked as passing while the gate was not green, stops released on a red gate.
- **The Stop hook's one-time release is no longer silent.** A stop on a red gate is logged as `released-red` and reported under "Needs you" in the next digest, until a gate pass.
- **`skill-eval` keeps each agent transcript** and, when the agent prints a JSON result, records tokens, cost and turns per run. The cost ratio uses money, else tokens, else runtime (`cost_basis` in the report).
- `--upgrade` also replaces the pack's hook scripts (old copy backed up), so an older install gets the new Stop hook.
- README: how to join the run log with Claude Code's own OpenTelemetry export by session id.
- 7 tests.

### proposed fix P1 (benchmark report, 2026-11-11)
- **Hook commands no longer depend on the agent's current directory.** The installer wrote `python3 .claude/hooks/gate_on_stop.py`. Claude Code runs a hook in the current directory, which follows the agent's `cd`. After `cd tests` the script was not found, the CLI reported "Stop hook error" and the agent stopped without the gate. The commands are now `python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/...`. The 0.4.2 fix moved into the project root inside the script, but the script never started. Seen in 2 of 10 benchmark runs on SWE-bench.
- **The installer repairs the commands of an older install** in place, without adding a second copy.
- **The session-start digest reports hooks that will not run** (script missing, or relative path) under "Needs you".
- `memory.py` works from the project root when it is started in a subfolder and `CLAUDE_PROJECT_DIR` is set.
- 4 regression tests. `test_stop_hook_command_blocks_from_a_subfolder` runs the command line of `settings.json` through a shell, as the CLI does; the 0.4.2 test called the script by its absolute path and so did not see the problem.

## 0.4.2 — 2026-11-08
Pre-publication security and edge-case review.
- **Gate cache now covers `gate.json`.** Editing the gate commands after a pass used to report "workspace unchanged — skipped" without running the new commands.
- **Stop hook fails closed on timeout.** A gate that exceeded the hook's fixed 1800 s let the agent finish silently; the budget is now sized from `gate.json` and a timeout blocks the stop.
- **Hooks run from the project root** (`CLAUDE_PROJECT_DIR`). Started from a subfolder, the Stop hook found no gate and let the agent stop.
- **Formatter no longer syncs the project on every edit** (`uv run --no-sync`), and falls back to `ruff` on PATH when the project doesn't pin it.
- Installer leaves a `settings.json` with an unexpected shape untouched instead of crashing.
- CI lints the README as English (it was linted with the Portuguese rules and passed vacuously).
- 3 regression tests, each verified to fail without its fix.

## 0.4.1 — 2026-11-07
- Native Google Antigravity plugin support in `install.py global` (`~/.gemini/config/plugins/ai-quality-pack/` with `plugin.json`, `agents/evaluator.md`, `rules/AGENTS.md`, and `assets/logo.svg`).
- Added `rust` language profile (`Cargo.toml` auto-detection, `cargo fmt`, `cargo clippy`, `cargo test` gates).
- Union-merge-safe `features.jsonl` event log alongside `features.json`.
- Fixed `install_egm()` fallback and `EgmTests` PATH isolation when broken/stub CLIs are present in `/usr/bin`.

## 0.4.0 — 2026-11-07
- `skill-eval`: A/B, A/A noise calibration, ablation, holdout split, non-compensatory guards, leakage critic, reward-hacking guard, history (RRSI, GEPA/gskill, Prime Agent).
- Completion gate (`memory.py gate`) with change detection + opt-in Claude Code Stop hook; stuck detection after 3 evaluator failures.
- `plan-before-code` routes large changes to Google's Elephant-Goldfish Model (`--with-egm`).
- New `ui-ux-review` skill.
- Security: upstream skills pinned to a reviewed SHA; memory digest sanitised and delimited; Windows-safe quoting; task-id collision warnings.

## 0.3.0
- Evaluator skill + subagent; tasks with IDs, notes, links, worktrees; ACE-style playbook; OWASP 2025 mapping; language profiles; cross-platform installer; tests + CI.

## 0.2.0
- Long-horizon memory, lessons, skill-evolve proposals, upstream grill-me.

## 0.1.0
- Base skills, AGENTS.md template, ruff/pyright/pytest gates, STE linter.
