# AI Quality Pack

A portable quality layer for AI coding agents (Claude Code, Google Antigravity, Codex, OpenCode, and any [Agent Skills](https://agentskills.io/specification) client). It covers deterministic gates, minimal rules, long-horizon memory, an independent evaluator, learning from mistakes, and **measured**, human-approved skill evolution.

> Status: v0.10.1, experimental. The design follows published work (see [Design sources](#design-sources)). Parts of the pack are measured, and most are not: [docs/RESULTS.md](docs/RESULTS.md) has the numbers, with what they do not show. Use `skill-eval` on your tasks to find out for your project.

## Why

Coding agents fail in predictable ways. They declare victory early, grade their own work too kindly, forget earlier sessions, repeat mistakes, and drift when instructions grow. This pack addresses each failure with the smallest mechanism that can be checked:

| Failure | Mechanism |
|---|---|
| "Done" without a check | Completion **gate** (lint/typecheck/tests) + optional Claude Code Stop hook. A gate without commands fails |
| Self-grading bias | A result from **records of commands** (gate, reproduction, counterexample). A separate **evaluator** (fresh context) looks for a counterexample; its text does not decide |
| Vague scope | **Acceptance criteria** agreed before code; design review via Google's Elephant-Goldfish Model (optional) |
| Lost context across sessions | File memory: tasks, features, progress, playbook, plus a session-start digest |
| Repeated mistakes | **Playbook** of root-caused rules, de-duplicated, scored helpful/harmful |
| Skill drift / overfitting | `skill-evolve` proposes a diff; `skill-eval` measures it (noise floor, guards, holdout); **a human approves** |
| Insecure code | `aqp-security-review` mapped to OWASP Top 10:2025 and the OWASP LLM Top 10 2025 |
| No record of what happened | Local **run log** (`events.jsonl`) + `memory.py stats`; eval transcripts with tokens and cost |

## What the measurements show

The numbers, with intervals, costs and limits, are in [docs/RESULTS.md](docs/RESULTS.md). All agent runs used Claude Haiku as the author.

What the pack does:
- It stops a "done" that no command checked. In 40 agent runs on repositories without a gate file, the old gate (exit code 0) let the agent continue in each run. The gate now fails.
- It records a regression that a command shows. Each of the 3 counterexamples of type `regression` was on a wrong patch. 3 is a small number.
- It runs checks that do not use a model: secrets, risk rules of the project, changes outside the scope of the task, deleted or skipped tests.
- In one use on a real project, the independent evaluator found a defect in new code that the tests of the author and the gate did not find. It is one case.

What the pack does not do:
- It does not tell you that a patch is correct. On 42 patches for hard issues, the evaluator did not separate wrong patches from correct patches, on Haiku or on Sonnet.
- A green gate is not proof. Of 86 wrong patches, 9 broke an existing test of the project; the other 77 failed only tests that the agent did not have.
- A green reproduction test is not proof. A test that the `criteria` subagent wrote from the issue alone rejected 0 of 19 wrong patches. With that test in the repository, the author resolved 20 of 40 issues, against 21 without it.
- The full pack was never better than the core, thus a default install has the core only.

Not measured: the new defaults against the bare agent, other models as the author, other agents than Claude Code, and macOS.

## Install

Requires Python 3.9+ and git. No other dependencies. Works on Linux, macOS and Windows.

```bash
git clone https://github.com/CarlosAndreFerreira/ai-quality-pack
python3 ai-quality-pack/install.py project /path/to/your/repo          # the core; auto-detects python / typescript / go / rust
python3 ai-quality-pack/install.py project . --secure                   # + Stop gate, guard, sandbox and CI gate, with one option
python3 ai-quality-pack/install.py project . --full                     # + the other skills of the pack and the upstream skills
python3 ai-quality-pack/install.py project . --with-stop-gate           # enforce the gate before Claude Code finishes
python3 ai-quality-pack/install.py project . --with-egm                 # + Google Elephant-Goldfish design review
python3 ai-quality-pack/install.py project . --link .codex/skills       # expose skills to another agent folder
python3 ai-quality-pack/install.py project . --with-codex --with-opencode   # hooks for Codex, plugin for OpenCode 2
python3 ai-quality-pack/install.py project . --dry-run                  # show what would change
python3 ai-quality-pack/install.py global                               # Antigravity plugin + Claude Code skills
```

### Claude Code plugin

```bash
claude plugin marketplace add CarlosAndreFerreira/ai-quality-pack
claude plugin install ai-quality-pack@ai-quality-pack
```

- The plugin gives Claude Code the skills, the `evaluator` and `criteria` subagents and the three hooks. It writes nothing in your repository.
- Run `aqp-memory init` in a repository to start the memory. Add `.agent-memory/gate.json` with `{"commands": [...]}` to turn on the completion gate. Without this file, or with no commands in it, the gate fails and the Stop hook blocks one time: a gate that checks nothing is not a pass.
- `aqp-memory` is `memory.py`. Use it where the instructions name `python3 .agents/skills/long-horizon/scripts/memory.py`.
- The plugin does not add `AGENTS.md`, `CLAUDE.md`, the CI workflow or the language profiles. Use `install.py` for these. In a project that has the `install.py` hooks, the plugin's hooks do nothing.
- Checked: `claude plugin validate --strict` passes. In two agent sessions on Linux, the three hooks ran, and the agent and the `evaluator` subagent used `aqp-memory`.
- Limits: the hook launcher is a shell script, and it has not been run on Windows. Use `install.py` there.
- `claude plugin uninstall ai-quality-pack` removes it.

The installer never overwrites your files. It merges `.claude/settings.json` instead of replacing it. `--upgrade` replaces pack-owned skills and keeps a backup. Where symlinks are unavailable (Windows without developer mode), it copies.

## What gets installed

```
.agents/skills/            pack skills + pinned upstream skills (.claude/skills → symlink)
AGENTS.md                  minimal: profile commands, definition of done, memory, rules
CLAUDE.md                  @AGENTS.md
.claude/settings.json      SessionStart → memory digest · PostToolUse → formatter · (opt.) Stop → gate
.claude/agents/evaluator.md
.agent-memory/             tasks.jsonl · features.json · lessons.jsonl · progress.md · gate.json · evals/
                           events.jsonl (run log, local, not committed)
```

## Skills

A default install has the core: `long-horizon`, `evaluator` and `plan-before-code`, with the three subagents and the hooks. `--full` adds the other skills of the table and the upstream skills. Reason: in the one comparison that we have, the full pack was never better than the core ([docs/RESULTS.md](docs/RESULTS.md)), and each skill description uses context in each session. The commands of `memory.py` are the same in the two installs. `memory.py --help` lists the 10 core commands, and `--help-all` lists each command. The Claude Code plugin has the core skills also: the marketplace entry names them, and `install.py --full` adds the others to a project.

| Skill | Purpose |
|---|---|
| `long-horizon` | Session ritual; tasks `T-0001…` with status, notes, links; resume after interruption; stuck detection; isolated git worktrees |
| `plan-before-code` | Routes small changes to an inline plan and large ones to EGM; always ends with testable acceptance criteria |
| `tdd-loop` | Strict red → green → refactor |
| `evaluator` | Independent, skeptical grading of each criterion against the running code |
| `aqp-code-review` | Ranked findings, each with a concrete failure scenario |
| `aqp-security-review` | OWASP Top 10:2025 (A01–A10) + OWASP LLM Top 10 (LLM01–LLM10) |
| `ui-ux-review` | Grades the running UI (WCAG 2.2 AA, heuristics, visual quality); optional pattern research with citations |
| `learn-from-mistakes` | Turns mistakes and non-obvious wins into scored playbook rules |
| `skill-evolve` | Curates the playbook; proposes skill diffs; protected core; never self-applies |
| `skill-eval` | A/B, A/A calibration and ablation of skills on verifiable tasks |
| `ste-writing` | Docs in ~80% ASD-STE100 Simplified Technical English, with a linter |

Upstream (MIT, [mattpocock/skills](https://github.com/mattpocock/skills), pinned to a reviewed commit, dependencies resolved automatically): `grill-me`, `grilling`, `grill-with-docs`, `domain-modeling`, `improve-codebase-architecture`, `codebase-design`, `handoff`.

## The loop

```
request → task open → acceptance criteria → implement → gate → evaluator (fresh context)
                                                          │ fail ×3 → ⚑ needs-human
                                                          └ pass → feature pass --verified-by evaluator → commit → progress
mistake / win → lesson add (dedup) → digest every session → helpful/harmful votes
             recurring or harmful → skill-evolve proposal → skill-eval verdict → human approves → commit (revertible)
```

## Operating rules

These rules need no code. They keep a line of agents useful when it runs without a person at each step.

**Three points where a person decides, and no more.** A person accepts 93% of an agent's permission requests (Anthropic, on the auto mode of Claude Code): a request at each step is not a control. Put the person where the decision has value:

1. **At the start: the question.** If the issue does not say enough, the result is a question on the issue (`memory.py triage`, the `triage` subagent). No code.
2. **Before a large or irreversible change: the plan.** A data migration, a deletion, a public API change, a new dependency: the agent stops and waits (`plan-before-code`, AGENTS.md).
3. **At the end: the pull request.** The agent opens a draft with the evidence and the review risk. A person reviews it and merges it. Nothing in the pack merges.

Between these points the checks are deterministic: the gate, the secret scan, the reproduction check, the warnings for changed tests.

**One issue, one worktree, one pull request.** Do not build an orchestrator. Reports of many agents on one codebase show merge conflicts and agents that undo the work of other agents ([Cursor, scaling agents](https://cursor.com/blog/scaling-agents); [Anthropic, building a C compiler](https://www.anthropic.com/engineering/building-c-compiler)).

- Each task has its own branch and its own git worktree: `memory.py task worktree --id <T>`.
- Do not run two tasks that change the same files at the same time. Run them one after the other.
- Each task ends in one pull request. `memory.py pr` refuses a second pull request for the same branch or the same issue, and refuses work on the main branch.
- Keep a task small enough for one review: the gate warns above `max_changed_lines`.

## Reproduction check, gate guards and doctor

```bash
python3 .agents/skills/long-horizon/scripts/memory.py repro --test "pytest tests/test_bug.py" --test-file tests/test_bug.py
python3 .agents/skills/long-horizon/scripts/memory.py doctor
python3 .agents/skills/skill-eval/scripts/skill_eval.py power --delta 0.15 --rho 0.6 --tasks 20
```

- `repro` runs the test on the base commit and on the current code. The result is `verified` only if the test fails on the base and passes now. A fix without a verified reproduction is not proved: say so in the report.
- The base runs in a temporary git worktree. Files that git does not track are not there. Use `--expect` to name text that the failure must print.
- The gate uses the committed `gate.json`. It ignores an edit that is not committed, and it reports the edit.
- The gate fails when `gate.json` does not exist or has no commands. In 40 agent runs on repositories without a gate file, the old message ("nothing to gate", exit code 0) let the agent continue in each run, and no agent wrote the file ([docs/RESULTS.md](docs/RESULTS.md)). `"allow_no_commands": true` is for a project that wants only the secret scan and the test guards. A gate file that git does not have gives a warning: a person reviews and commits it.
- The gate reports deleted test files and new skip markers. It does not block them. The next session digest shows them.
- `task open` saves the base commit in `tasks.jsonl` and `events.jsonl`. `gate` and `evidence` compare with the earliest valid open task base by default, then the remote default merge-base, then `HEAD`. They verify the saved base against `events.jsonl` and git ancestry, and report if `.agent-memory/gate.json` changed after that base.
- `task open --scope <glob>` records allowed file patterns for a task. `gate` shows a warning for changed files outside that scope, and `evidence` lists them and sets review risk to at least `MEDIUM`.
- `"block_test_changes": true` in `gate.json` makes the gate fail for a deleted test file or a new skip marker. A person who agrees adds the path (or a glob) to `"allowed_test_changes"` and commits `gate.json`. The agent cannot approve its own change, because the gate reads the committed file. A changed line in an existing test stays a warning: that warning is as frequent on correct patches as on wrong patches ([docs/RESULTS.md](docs/RESULTS.md), section 4).
- `"replay_base_tests": "warn"` (or `"block"`) with `"test_command"` in `gate.json` swaps modified or deleted tracked tests back to the base version, runs `test_command` on the new code, and restores the workspace (with recovery via `.replay-backup.json` if interrupted). Unapproved deletions or skips stay visible when an agent commits them after `task open`; neither option ran with a live agent yet.
- `doctor` finds hooks that will not run and gate commands that are not installed.
- Hooks do not run in `claude -p --bare`. In CI, run `memory.py gate` as a separate step. In unattended runs, use `gated-run` (see below).
- `skill-eval power` gives the number of tasks that a comparison needs. Run it before you spend tokens.
- `diff-view` shows the change without the comments that it added. The evaluator reads this view.
- `install.py project . --with-ci` adds a GitHub Actions workflow. It runs the gate on each pull request with the `gate.json` of the base branch.
- The `criteria` subagent writes the acceptance criteria and their tests from the requirement, in new test files. It does not see the implementation. Record the tests with the feature: `memory.py feature add --id F-1 --desc "..." --criterion "..." --test-file tests/test_x.py`. A reproduction with a recorded test file that did not change counts as a test from before the change. A reproduction with a test that was not recorded before the change does not support the result: `memory.py verdict` gives UNKNOWN, and `feature pass --verified-by evaluator` refuses it. Reason: a test that is written after the change can agree with a wrong change (2 of 3 such reproductions were on wrong patches in our measurement, a small number). A person accepts later tests with `"accept_later_tests": true` in `.agent-memory/config.json`, or passes the feature with `--verified-by human`.
- `memory.py evidence` prints a Markdown block for a pull request. It lists what the checks recorded for this code and what is not verified.
- `skill-eval judge --cases cases.jsonl --judge-cmd "claude -p {prompt}"` measures the evaluator on cases with a known answer. The main number is the rate of wrong work that the evaluator approved. Add `--repeats 3` (`--rule asymmetric`) to approve a case only when all runs agree, and to report unanimous rate and pairwise kappa.
- `install.py project . --evaluator-model opus` makes the evaluator subagent of Claude Code run on that model (a `model:` line in `.claude/agents/evaluator.md`). The idea is that a judge on the model of the author tends to agree with the author. Our one measurement does not support a stronger model by default: on the 24 shipped cases, the evaluator on Claude Sonnet approved 7 of 12 wrong patches, and the evaluator on Claude Haiku approved 0 of 12, for patches that Haiku wrote ([docs/RESULTS.md](docs/RESULTS.md)). The 7 are one type of defect, so this is not a general rate. On 42 patches for hard SWE-bench issues, Sonnet approved 13 of 19 wrong patches and Haiku 2 to 4; the two models did not separate wrong from correct patches. Measure the evaluator on cases with a known answer (`skill_eval.py judge`) before you change its model. Run the command again to change the model. OpenCode and the plugin are not changed.
- Set `"evaluator_runs": 3` (or `"auto"`) in `.agent-memory/config.json` to require unanimous `feature vote` runs for `feature pass --verified-by evaluator`. Editing code makes old votes stale; disagreements appear as `UNKNOWN` in `evidence` until a fix or a human override.

### Evidence for a verdict: counterexample and mutation check

We measured the evaluator on 42 patches for hard issues with two models. One model rejected most patches and the other approved most patches, and the two did not separate wrong patches from correct patches ([docs/RESULTS.md](docs/RESULTS.md)). A verdict that only the opinion of a model supports has little information. These commands tie a verdict to a command that ran.

```bash
python3 .agents/skills/long-horizon/scripts/memory.py counterexample --test "pytest tests/test_probe.py" --test-file tests/test_probe.py
python3 .agents/skills/long-horizon/scripts/memory.py mutants
```

- **`counterexample`** is the opposite of `repro`. It shows a defect: a command that fails on the current code. Then it runs the command on the base. If the command passes on the base, the change broke it (`regression`). If it fails on the base too, the change does not fix it (`not-fixed`), or the check fails for another reason: read the two outputs. A command that passes on the current code shows no defect (exit code 1).
- **A verdict of the evaluator needs a record.** This is the default; `"verdict_evidence": false` in `.agent-memory/config.json` turns it off. The text of the evaluator does not decide: its task is to find a counterexample, and `memory.py verdict` gives the result. A PASS (`feature pass --verified-by evaluator`, `feature vote --verdict PASS`) needs a reproduction for the current code. A FAIL vote needs a counterexample for the current code. Without the command, the result is UNKNOWN, and the evaluator says what it could not show. A person can pass a feature with `--verified-by human`.
- The evidence block shows a counterexample for the current code, and the review risk is then `HIGH`.
- **A test inside the file that the fix changes.** In Rust or Go, a unit test is in the file of the code. `--test-file` copies that file to the base, and the fix goes with it. Use `--test-patch FILE`: a patch with the test only, which `repro` and `counterexample` apply on the base. Make it before you write the fix (`git diff > test.patch`), or cut the test lines from the complete diff. Add `--expect "<text of the failure>"`: without the test, the base can fail for another reason, for example a function that does not exist.
- **A build cache that two checkouts use.** With `CARGO_TARGET_DIR`, or a build directory outside the repository, the run on the current code can use the files that the base compiled, and `repro` then says `STILL-FAILING` for a correct fix. `--base-env NAME=VALUE` sets a variable for the run on the base only, for example `--base-env CARGO_TARGET_DIR=/tmp/base-target`. `repro` names this cause when the last lines of the two outputs are the same.
- **The check must load the code of the base.** A check that imports the code from an absolute path or from an installed package runs the current code in the two runs. `counterexample` finds this: it runs the check one more time on the base, with each source file that the change touched replaced by one unknown name. If that name is not in the output, the result is `base-not-seen`. `repro` gives the same reason for a test that passes in the two runs. Limit: the probe needs a source file that the change touched and that the base has.
- **Questions about the requirement.** `feature add --question "..."` records what the requirement does not decide. A person answers with `memory.py feature answer --id F --n 1 --evidence "..." --by <name>` in a terminal; an agent cannot. The evidence block has a part "Decisions about the requirement", with each question and its answer, for the features of the change: a reviewer reads there what the requirement did not say and who decided. While a question has no answer, the evidence block has a line "Requirement" and an item under "Not verified", and `feature confirm` refuses. The pack does not find these questions: the `criteria` subagent or a person writes them. Why: in our measurement the wrong patches failed on behaviour that the issue did not describe ([docs/RESULTS.md](docs/RESULTS.md)).
- **A person confirms the tests of the criteria.** `feature add --assumption "..."` records what the tests take as true and the requirement does not say. `memory.py feature review --id F` prints a sheet for a person, with these assumptions first, then the criteria and the test files. The person runs `memory.py feature confirm --id F` in a terminal; an agent cannot. The result of `verdict` does not change: the verdict and the evidence block say if a person confirmed the tests. A test file that changes after the confirmation is not confirmed. Why: 19 of 42 tests that a model wrote from the requirement alone failed on the correct fix ([docs/RESULTS.md](docs/RESULTS.md)). Not measured: how many of these a person finds.
- **`memory.py verdict`** prints what the records support for exactly this code. It reads no text of an agent. `FAIL` (exit code 1): a `regression` counterexample. `SUPPORTED` (exit code 0): the gate passed and a reproduction is verified; this is support, not proof. `UNKNOWN` (exit code 3): the rest, with one of two types and the next step. `no-evidence`: no command gave a record for this code (the work of verification is not done). `weak-evidence`: a command ran, and its record does not count (for example, a reproduction with a test from after the change). Use it in a script or in CI in place of the last line of an evaluator.
- **`--json`** on `gate`, `repro`, `counterexample` and `evidence` prints one JSON object in place of the text: `schema`, `command`, `exit`, `result`, `record` (what the command wrote in the run log) and `output`. `evidence --json` has the risk, the verdict, the records, the list of what is not verified and the Markdown. The exit code does not change. A script, CI or another agent reads this object, not the lines of a terminal. The number in `schema` changes only when a key goes away or changes its meaning. [docs/JSON.md](docs/JSON.md) has each key and each value of `result`.
- **`mutants`** runs the mutation tool of the project on the lines that the change touched. A mutation tool makes small wrong versions of the code. A test suite that accepts a wrong version does not check that code. The pack has no mutation engine: put the command in `gate.json`, with `{diff}` for the path of a diff file. For Rust: `"mutation_command": "cargo mutants --in-diff {diff}"` ([cargo-mutants](https://mutants.rs/in-diff.html); exit code 2 means that mutants were missed). StrykerJS has `--incremental`. When the command is in the gate file, the evidence block has a line "Mutation check", and a check that did not pass is in "Not verified". The gate does not run it: it is slow.
- Why these two: a study that replayed the validation commands of repair agents on the code before and after the change found that, in 24% of the runs, no command that passed could tell the bug from the fix ([arXiv 2607.28871](https://arxiv.org/abs/2607.28871)). A benchmark of test suites written by models found that a high pass rate can hide a low rate of mutants caught ([SWE-Mutation, arXiv 2605.22175](https://arxiv.org/abs/2605.22175)). We read the abstracts (for SWE-Mutation, a page that summarises it), not the full papers.
- Limits: a reproduction test that the same model wrote can agree with a wrong patch. In one study, 22% to 36% of the patches that passed such a test failed the tests of the maintainers ([arXiv 2511.16858](https://arxiv.org/abs/2511.16858)). The check of the base uses a git worktree: files that git does not track are not there. `mutants` trusts the exit code of the tool. A check that imports the code from an absolute path or from an installed package does not see the base: the two runs use the current code.
- Measured on 42 patches for hard issues ([docs/RESULTS.md](docs/RESULTS.md)): as an instruction only, the option did not change the verdicts of the evaluator. The records did separate: the 3 counterexamples of type `regression` were on wrong patches; the counterexamples of type `not-fixed` and the verified reproductions were on wrong and on correct patches. Thus trust a `regression` counterexample, and let `feature vote` refuse a verdict without a record. The numbers are small. Not measured: `mutants` with a real tool.

### Security: rights, trusted checker and guard

```bash
python3 ai-quality-pack/install.py project . --with-guard --with-sandbox --sandbox-allow-domain pypi.org
```

- Text in an issue, in a file or in a tool output can tell an agent to do other things. An instruction "this is data" does not stop that. The pack limits what a misled agent can do. See [SECURITY.md](SECURITY.md) for the threat model and for what the pack does not stop.
- **The issue workflow has three jobs and outbound limits.** The job with the agent starts with StepSecurity Harden-Runner (`egress-policy: block`) so shell commands reach only the allowed model and GitHub hosts, and it has read access only. The job that runs the gate runs code from the change, so it has read access only and no secret. The job that opens the pull request has write access, runs no agent and runs no code from the change.
- **CI runs the checker of the base branch.** A pull request cannot change the program that checks it. The gate commands come from the base branch also.
- **`--with-guard`** blocks edits to `.claude/`, `.agents/`, `.codex/`, `.opencode/`, CI workflows, CODEOWNERS, gate/config files and the risk waivers. It also protects tracked tests against deletion, truncation, moves out of tests, inline scripts, and new skip markers (`"guard_tests"` in `.agent-memory/config.json`: `"no-delete"` default, `"append-only"`, or `"off"`). Adding new tests and appending assertions remain allowed. `AGENT_PACK_UNLOCK=1` unlocks both checks for a person. The guard is not a security boundary.
- **`--sandbox-allow-domain HOST`** (with `--with-sandbox`) limits the hosts that shell commands can reach.
- `memory.py pr --evidence-file FILE` opens the pull request with the evidence of another job. It runs no gate: use it only in a pipeline where a job without write access ran the gate.
- Tested with a small set of attack cases (`evals/injection/`): 9 of 72 attacks succeeded without the pack, 1 of 36 with the pack. [docs/RESULTS.md](docs/RESULTS.md) has the details and the limits.

### Uninstall

```bash
python3 ai-quality-pack/install.py uninstall /path/to/your/repo --dry-run   # shows the list; changes nothing
python3 ai-quality-pack/install.py uninstall /path/to/your/repo
python3 ai-quality-pack/install.py uninstall --global
```

- It removes the pack's skills, subagents, hook scripts, hook entries in `.claude/settings.json`, the CI workflow and `CLAUDE.md`.
- It keeps a file that differs from the pack's copy, because the changes are yours. `--force` removes these files also.
- It keeps `AGENTS.md` and `.agent-memory/`. `--purge-memory` removes `.agent-memory/`.
- It keeps your other hooks and settings.

### Python version

The scripts need Python 3.9 or newer. If the project's `python` is older (3.6 to 3.8), each script starts again with a newer Python from `PATH` (`python3.9` to `python3.15`, `python3`, `python`). Set `AGENT_PACK_PYTHON` to select one. If none is found, the script prints the cause and exits with code 1.

### Checks before a push

CI runs these commands on Linux, macOS and Windows (Python 3.9 and 3.13) for each push to `main` and each pull request. Run them before a push also:

```bash
python -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
python skills/skill-evolve/scripts/validate_skills.py skills --strict
python skills/ste-writing/scripts/ste_lint.py README.md --lang en --threshold 60
```

Run the tests two times: without `PYTHONDONTWRITEBYTECODE` (make sure that your shell does not set it) and with it. Version 0.8.0 was released after test runs that had this variable set in each environment, and 4 tests failed without it.

## More parts, in the reference

These parts are installed and have tests. None was used on a real project, and none was measured with an agent, unless the line says so. Their text is in [docs/REFERENCE.md](docs/REFERENCE.md).

- [## Measuring skill changes (`skill-eval`)](docs/REFERENCE.md#measuring-skill-changes-skill-eval): Measure a change of a skill with tasks of your project: `run`, `ablate`, `calibrate`, `power`, `judge`. Only `judge` ran in our measurements.
- [## Observability](docs/REFERENCE.md#observability): The run log, `stats`, the control coverage and the factory numbers.
- [### From an issue to a draft pull request](docs/REFERENCE.md#from-an-issue-to-a-draft-pull-request): `memory.py pr` and the issue workflow on GitHub. Not run on GitHub.
- [### Triage: is the issue ready for work?](docs/REFERENCE.md#triage-is-the-issue-ready-for-work): `memory.py triage` and the `triage` subagent. The text check passed 53 of 53 valid issues; the subagent is not measured.
- [### Factory report](docs/REFERENCE.md#factory-report): `memory.py factory`: numbers of merged and rejected changes.
- [### Merge readiness](docs/REFERENCE.md#merge-readiness): The merge-readiness step of the evaluator.
- [### Risk rules of the project](docs/REFERENCE.md#risk-rules-of-the-project): `risk_rules` in the gate file, and waivers by a person.
- [### Secrets, provenance and audit](docs/REFERENCE.md#secrets-provenance-and-audit): `provenance`, `audit` and the secret scan. The secret scan runs in each gate.
- [### Memory: small and confirmed](docs/REFERENCE.md#memory-small-and-confirmed): Lessons, the size limit of the digest and the confirmation by a person.
- [### Complexity of the change](docs/REFERENCE.md#complexity-of-the-change): `memory.py complexity`: a warning for a change that makes the code more complex.
- [### Evals of the pack](docs/REFERENCE.md#evals-of-the-pack): The evaluation sets of the pack itself.
- [### CI audit, CODEOWNERS and sandbox](docs/REFERENCE.md#ci-audit-codeowners-and-sandbox): `install.py --with-ci`, `--with-sandbox` and the CODEOWNERS lines.
- [### Other agents: Codex and OpenCode](docs/REFERENCE.md#other-agents-codex-and-opencode): Hooks for Codex and a plugin for OpenCode. Not used on a real project.
- [### Checks of the skills themselves](docs/REFERENCE.md#checks-of-the-skills-themselves): `validate_skills.py` and the writing lint.
- [### Unattended runs: the gate without hooks](docs/REFERENCE.md#unattended-runs-the-gate-without-hooks): `memory.py gated-run` for a run with no hooks.
- [## Robustness](docs/REFERENCE.md#robustness): What the installer and the scripts do on a failure.

## Limitations
- **Measured in part.** [docs/RESULTS.md](docs/RESULTS.md) has what we measured. The complete pack was not measured against the bare agent on hard issues. The design sources report gains for *their* systems, not for this pack.
- **Antigravity**: `install.py global` installs a native Antigravity plugin (`~/.gemini/config/plugins/ai-quality-pack/`) with `plugin.json`, global `rules/AGENTS.md`, and the isolated `evaluator` subagent (`agents/evaluator.md`).
- **No sandbox by default.** Agents run with your permissions. `install.py --with-sandbox` turns on the Claude Code sandbox for shell commands (not on native Windows). For unattended runs, use a container or a VM also.
- The run log sees only what goes through `memory.py` and the pack hooks. It does not see the agent's reasoning or its other tool calls. Two sessions in one checkout at the same time share one session id file, so their events can get the wrong id.
- Recurrence counting depends on the agent reusing lesson keys. Duplicate detection is lexical, not semantic.

## Design sources
- Anthropic: [Effective harnesses for long-running agents](https://anthropic.com/engineering/effective-harnesses-for-long-running-agents) · [Harness design for long-running application development](https://anthropic.com/engineering/harness-design-long-running-apps)
- [Evaluating AGENTS.md (ICLR 2026)](https://arxiv.org/abs/2602.11988): keep context files minimal
- [ACE: Agentic Context Engineering (ICLR 2026)](https://arxiv.org/abs/2510.04618): itemised playbooks with incremental updates
- [Google Research RRSI](https://github.com/google-research/rrsi): regularised harness self-improvement (noise floor, guards, holdout)
- [GEPA / gskill](https://github.com/gepa-ai/gepa): measuring skills on verifiable repo tasks
- [Google Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model): fresh-context design review
- DeepSeek Super-agent, Prime Agent, LongHorizon-Harness: task IDs and recovery, completion gate, stuck detection
- [Test-Driven Development for Code Generation](https://arxiv.org/abs/2402.13521); [OWASP Top 10:2025](https://owasp.org/Top10/2025/)
- [Validation Evidence in LLM Repair Agents](https://arxiv.org/abs/2607.28871): replay a check on the code before and after the change; [Investigating Test Overfitting on SWE-bench](https://arxiv.org/abs/2511.16858): the limit of tests that the same model wrote; [SWE-Mutation](https://arxiv.org/abs/2605.22175) and [cargo-mutants](https://mutants.rs/): mutation checks on the changed lines

Evaluated projects and why each was or was not adopted: [docs/extensions.md](docs/extensions.md).

## Contributing
Bug reports, results from your own use, measurements and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first: it has the checks to run and the rules for a change. Report a security problem in private, as [SECURITY.md](SECURITY.md) says.

## License
MIT, copyright Carlos André Ferreira. The files that the installer copies into your repository (hooks, subagents, CI workflows, `AGENTS.md`) start with the copyright line and the MIT reference: keep it in your copies, as the license asks. Upstream skills keep their own licenses (copied into each folder with a `.upstream` provenance file).
