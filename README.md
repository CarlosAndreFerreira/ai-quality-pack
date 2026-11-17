# AI Quality Pack

A portable quality layer for AI coding agents (Claude Code, Google Antigravity, Codex, OpenCode, and any [Agent Skills](https://agentskills.io/specification) client). It covers deterministic gates, minimal rules, long-horizon memory, an independent evaluator, learning from mistakes, and **measured**, human-approved skill evolution.

> Status: v0.9.0, experimental. The design follows published work (see [Design sources](#design-sources)). Parts of the pack are measured, and most are not: [docs/RESULTS.md](docs/RESULTS.md) has the numbers, with what they do not show. Use `skill-eval` on your tasks to find out for your project.

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
| Insecure code | `security-review` mapped to OWASP Top 10:2025 and the OWASP LLM Top 10 2025 |
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
- This repository is private: `git` must have a stored credential for it (`gh auth login`, then `gh auth setup-git`).
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
| `code-review` | Ranked findings, each with a concrete failure scenario |
| `security-review` | OWASP Top 10:2025 (A01–A10) + OWASP LLM Top 10 (LLM01–LLM10) |
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

## Measuring skill changes (`skill-eval`)

```bash
export SKILL_EVAL_AGENT_CMD='claude -p {prompt}'          # any headless agent; run inside a sandbox
python3 .agents/skills/skill-eval/scripts/skill_eval.py init        # write 3–10 verifiable tasks (~1/3 holdout)
python3 .agents/skills/skill-eval/scripts/skill_eval.py calibrate   # A/A run → noise band
python3 .agents/skills/skill-eval/scripts/skill_eval.py run --proposal .agent-memory/proposals/<p>.md --annotate
python3 .agents/skills/skill-eval/scripts/skill_eval.py ablate --skill <name>   # is this skill still worth it?
```
Verdicts: `IMPROVES`, `IMPROVES (weak evidence)`, `INCONCLUSIVE`, `REGRESSES`, `PRUNABLE`/`KEEP`, `NO-SIGNAL`, `NOT-USED`. Four guards block a change regardless of its headline gain:
- a task the baseline always passed now fails;
- protected test files were tampered with;
- the holdout dropped beyond the noise band;
- the proposal leaks task-specific content.

## Observability

The memory files hold the state of the work. The run log holds what happened in each run. `memory.py` and the hooks write one line to `.agent-memory/events.jsonl` for each session start, gate run, feature grading, lesson vote, and Stop-hook block or release. Each line has the agent session id.

The log has ids, outcomes and durations. It has no prompt text and no code. It stays on your machine (git-ignored), and `AGENT_MEMORY_EVENTS=0` turns it off.

```bash
python3 .agents/skills/long-horizon/scripts/memory.py stats            # last 30 days; --days N, --json
python3 .agents/skills/long-horizon/scripts/memory.py stats --min-gate-coverage 0.8   # exit code 1 below this rate
```
```
# Run statistics: last 30 days (41 events, 6 sessions)
gate: 12 runs · 4 failed (33%) · 9 skipped (unchanged) · median 41.0s
  3× failed: uv run pytest -q
stop hook: 3 blocked · 1 released without a passing gate
features: 5 passed · 4 failed gradings · 1.8 evaluator rounds per pass · verified by: evaluator 4, human 1
  ⚠ marked as passing while the gate was not green for that workspace: F-3
lessons: 3 added · 2 recurred · votes +4/-1
```

Two cases that were silent before are now visible:
- The Stop hook blocks one time only, so that it cannot loop. If the agent then stops without a gate pass for its final code, the log records `released-red` and the next session digest shows it under "Needs you".
- `stats` shows the control coverage: in how many sessions the gate ran a command, the last gate result was a pass, criteria were recorded, the evaluator graded, and a reproduction was verified. A session without a record of a control is a gap, not a pass. In 40 benchmark runs with the pack installed, the gate had no commands in each run and the evaluator ran in 6 runs; only the artifacts showed it ([docs/RESULTS.md](docs/RESULTS.md)). The idea is from an eval runner that scores an agent harness from its event log and reports a missing event as a coverage gap.
- `feature pass --verified-by evaluator` is a statement by the agent. The log records if the gate was green for that workspace at that moment, and `stats` lists the features where it was not.

`skill-eval` keeps the output of each agent run in `.agent-memory/evals/results/<run>-transcripts/`. If the agent prints a JSON result (`claude -p {prompt} --output-format json`), each run also records tokens, cost and turns, and the cost ratio of a verdict uses money or tokens instead of wall-clock time.

Each measurement prints one line for each variant that you can quote: `reliability at cost, candidate: each of 3 runs passed on 75% of the tasks (95% CI 30% to 95%); $0.0412 for each passed run`. The first number is pass^k: a task counts only when each of its runs passed. The cost is the total spend divided by the runs that passed, in money, else tokens, else seconds. `skill_eval.py run --max-cost-per-pass 0.05` gives no `IMPROVES` verdict when the candidate costs more than that, or when the agent command reports no cost.

For tokens, cost and tool calls of your normal sessions, use the telemetry that Claude Code already has. The pack does not copy it. The `session.id` attribute there is the `session` field of the run log, so you can join the two.

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317    # your collector
```
See [Claude Code: monitoring usage](https://code.claude.com/docs/en/monitoring-usage). Other agents (Antigravity, Codex) get the run log but no session id, unless you set `AGENT_SESSION_ID`.

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
- **`memory.py verdict`** prints what the records support for exactly this code. It reads no text of an agent. `FAIL` (exit code 1): a `regression` counterexample. `SUPPORTED` (exit code 0): the gate passed and a reproduction is verified; this is support, not proof. `UNKNOWN` (exit code 3): the rest, with one of two types and the next step. `no-evidence`: no command gave a record for this code (the work of verification is not done). `weak-evidence`: a command ran, and its record does not count (for example, a reproduction with a test from after the change). Use it in a script or in CI in place of the last line of an evaluator.
- **`mutants`** runs the mutation tool of the project on the lines that the change touched. A mutation tool makes small wrong versions of the code. A test suite that accepts a wrong version does not check that code. The pack has no mutation engine: put the command in `gate.json`, with `{diff}` for the path of a diff file. For Rust: `"mutation_command": "cargo mutants --in-diff {diff}"` ([cargo-mutants](https://mutants.rs/in-diff.html); exit code 2 means that mutants were missed). StrykerJS has `--incremental`. When the command is in the gate file, the evidence block has a line "Mutation check", and a check that did not pass is in "Not verified". The gate does not run it: it is slow.
- Why these two: a study that replayed the validation commands of repair agents on the code before and after the change found that, in 24% of the runs, no command that passed could tell the bug from the fix ([arXiv 2607.28871](https://arxiv.org/abs/2607.28871)). A benchmark of test suites written by models found that a high pass rate can hide a low rate of mutants caught ([SWE-Mutation, arXiv 2605.22175](https://arxiv.org/abs/2605.22175)). We read the abstracts (for SWE-Mutation, a page that summarises it), not the full papers.
- Limits: a reproduction test that the same model wrote can agree with a wrong patch. In one study, 22% to 36% of the patches that passed such a test failed the tests of the maintainers ([arXiv 2511.16858](https://arxiv.org/abs/2511.16858)). The check of the base uses a git worktree: files that git does not track are not there. `mutants` trusts the exit code of the tool. A check that imports the code from an absolute path or from an installed package does not see the base: the two runs use the current code.
- Measured on 42 patches for hard issues ([docs/RESULTS.md](docs/RESULTS.md)): as an instruction only, the option did not change the verdicts of the evaluator. The records did separate: the 3 counterexamples of type `regression` were on wrong patches; the counterexamples of type `not-fixed` and the verified reproductions were on wrong and on correct patches. Thus trust a `regression` counterexample, and let `feature vote` refuse a verdict without a record. The numbers are small. Not measured: `mutants` with a real tool.

### From an issue to a draft pull request

```bash
python3 ai-quality-pack/install.py project . --with-issue-workflow      # adds .github/workflows/agent-issue.yml
python3 .agents/skills/long-horizon/scripts/memory.py pr --title "Fix add" --issue 12 --dry-run
```

- The workflow starts when a person adds the label `agent` to an issue. The agent works on the branch `agent/issue-<number>`, with a limit of turns and of US dollars.
- The workflow runs the gate and opens the pull request. The agent does not push, does not open the pull request and does not merge.
- `memory.py pr` opens a draft pull request with the evidence block. It needs the GitHub CLI (`gh`).
- It stops without a pull request if the gate is red (exit code 1), if an open pull request has the same branch or closes the same issue (exit code 3), or if work is not committed (exit code 2). The workflow then writes a comment on the issue.
- The evidence block has a review risk: `HIGH` for changes to CI, hooks, the gate, dependencies, migrations, infrastructure or security code, for changed tests and for more than 400 lines. `MEDIUM` for more than 100 lines or 5 files, or for a check without a record. `LOW` for the rest. The label is a guide for the reviewer, not a proof.
- `--cost-usd` puts the cost of the run in the block.
- The block says what the PASS of a feature does not cover. These three lines come from the review of a real pull request, where a PASS for one feature was read as an approval of 16,000 changed lines:
  - **Base branch.** The gate gives a warning, and the block has a line, when the branch is behind the default branch of `origin` (as of the last `git fetch`). The block says if a merge has conflicts, and the review risk is then `HIGH`. A green gate on an old branch says nothing about the code that a merge gives.
  - A changed file in the scope of a feature that waits for its grade shows as "not graded yet", with the id of the feature.
  - **Feature coverage.** The block counts the changed files that are in the scope of a task of a graded feature (`task open --title T --feature F-1 --scope "src/billing/**"`). The files outside each scope are in "Not verified": they had no criteria and no evaluator. When no task has a scope, the block says that the changed files are not linked to a feature.
  - **Criteria that name code.** `feature add` gives a warning for a criterion that names a source file or a function, and the block repeats it for a graded feature. Such a criterion describes the implementation: its PASS shows that the code is as written. Write what a user or a test can observe, or let the `criteria` subagent write the criteria from the requirement.
  - Limits: the scope is what the agent or a person wrote in the task. The check for names of code finds text (file extensions, `snake_case`, `a::b`); it does not know if a criterion is correct. Not measured.
- Limit: the workflow template was not run on GitHub. Run it on a test issue first, and read the comments at the top of the file.

### Triage: is the issue ready for work?

```bash
python3 .agents/skills/long-horizon/scripts/memory.py triage --file issue.md
```

- Exit code 0: the text is ready for work. Exit code 4: the text is too thin, and the output is the questions for the issue.
- The issue workflow runs this check first. A thin issue gets the questions as a comment, and no agent run starts.
- The check is a set of text rules. It finds an empty or one-line issue. It does not find a subtle ambiguity.
- The `triage` subagent does the real check: it reads the repository and gives `TRIAGE: READY` with its assumptions, or `TRIAGE: ASK` with at most 3 questions. It has read-only tools.
- Measured: the text check passed 53 of 53 valid SWE-bench Verified issues, after three rules were adjusted on the same issues. It stopped 9 of 9 thin requests that we wrote. The subagent is not measured.

### Factory report

```bash
python3 .agents/skills/long-horizon/scripts/memory.py factory --days 30
```

- From GitHub (branches `agent/*`): pull requests opened, merged and closed, the merge rate with a 95% interval, the median time to merge, the cost, the review risk, and the merged pull requests that were reverted.
- From the local run log: pull requests refused for a red gate (work that ended as "done" with a red gate), unattended runs, triage results.
- The cost for each merged pull request shows only when each pull request has a cost in its text.
- Limit: the local run log is on one machine. A CI runner does not keep it.

### Merge readiness

- The evaluator checks what a maintainer checks: the written rules of the project, the style of the code next to the change, one purpose, size, documentation. It writes `MERGE-READY: YES` or `MERGE-READY: NO` after the overall result. Only a broken written rule changes the overall result.
- `"max_changed_lines": 400` in `gate.json` makes the gate warn about a larger change. It does not block.
- `doctor` says when the gate has no lint or type check command.
- Not measured: the effect of these checks on the share of pull requests that maintainers merge.

### Risk rules of the project

The pack has a fixed list of risky paths. A project adds its own rules in `gate.json`:

```json
"risk_rules": [
  {"name": "payments", "path": "(^|/)billing/", "diff": "charge\\(|refund\\(", "why": "it changes how money moves", "block": true},
  {"name": "schema", "path": "\\.sql$", "why": "it changes the database"}
]
```

- `path` is a regular expression for the changed paths. `diff` is a regular expression for the lines that the change added. With the two, a line must match `diff` in a file that matches `path`.
- A rule that matches gives a gate warning, sets the review risk to `HIGH`, shows in the evidence block, and makes `"evaluator_runs": "auto"` ask for 3 runs.
- With `"block": true`, the gate fails until a person waives the rule.
- A person who reviewed the lines records why no more review is necessary: `memory.py risk waive --rule payments --reason "..."`. This needs a terminal, or `AGENT_MEMORY_HUMAN=1`. The agent cannot do it.
- The waiver is a line in `.agent-memory/risk-waivers.jsonl` with the rule, the reason, the person and the lines. Commit it: the reviewer of the pull request sees it, and the evidence block shows the reason.
- A waiver is for the lines that the person saw. A new line that matches the rule needs a new waiver.
- `memory.py risk` shows the rules that match the current change. `memory.py risk --strict` ends with exit code 1 when a rule has no waiver.
- The rules come from the committed gate file, as the commands do. `doctor` reports a rule that is not valid.
- Limits: a rule finds text, not meaning. The check for a person stops a habit, not an attack. Not measured: the effect on the defects that reach a merge.

### Secrets, provenance and audit

```bash
python3 .agents/skills/long-horizon/scripts/memory.py secrets --base origin/main
python3 .agents/skills/long-horizon/scripts/memory.py provenance --set "Assisted-by: AI coding agent"
python3 .agents/skills/long-horizon/scripts/memory.py provenance --check origin/main
python3 .agents/skills/long-horizon/scripts/memory.py audit --out audit.jsonl
```

- The gate scans the lines that the change added, before it runs the project's commands. A line that looks like a secret stops the gate. The output names the file, the line and the rule, never the value.
- Rules: private keys, AWS, GitHub, Slack, Google and `sk-` keys, JSON web tokens, and a password, token or key in an assignment. Placeholders do not count. For a false alarm, put `pack:allow-secret` on the line. `"secret_scan": false` in `gate.json` turns the scan off.
- The scan is a set of patterns. It does not replace a dedicated scanner such as gitleaks: add one to the gate commands if you have it.
- `provenance` is off until a person sets a trailer. Then the agent adds the trailer to its commits, `--check` finds commits without it, and `memory.py pr` puts it in the pull request text.
- `audit` writes the run log (sessions, gate runs, gradings, pull requests, triage) with a checksum. The issue workflow keeps it as an artifact for 90 days.
- Each line of the run log says who ran it: `actor` (`AGENT_ACTOR`, else `GITHUB_ACTOR`, else the git user e-mail), `model` (`AGENT_MODEL`, else the model that the Claude Code session start reported) and `pack` (the pack version). A gate line has `policy` also: a hash of the gate rules that gave the result.
- Each line has the hash of the line before it. `memory.py audit --verify` exits 1 when a line was changed, removed or inserted. `audit` prints the head of the chain; `audit --verify --head HASH` finds a log that was cut at the end.
- Limit: the chain has no secret. An agent that writes the complete log again, with new hashes, gives a chain that verifies. The chain is proof only against a head that the agent cannot change: keep the head (the output of `audit`) in a CI log or an artifact. Lines from before this version have no hash, and `--verify` counts them apart.

### Memory: small and confirmed

- The session digest has a size limit of 6000 characters (`memory.py start --max-chars`). The most urgent items come first, so the cut removes the end.
- A lesson that an agent records is not in the digest until a person confirms it: `memory.py lesson confirm --key <key>`, in a terminal. Text that a model wrote does not become a standing instruction without a person.
- Each new lesson records who wrote it (agent or human), the commit and the session. `memory.py lesson list` shows the lessons that wait.
- Lessons from before this version stay in the digest.
- Limit: the terminal check stops an agent that confirms by habit. It is not a security boundary: `AGENT_MEMORY_HUMAN=1` passes it.

### Complexity of the change

```bash
python3 .agents/skills/long-horizon/scripts/memory.py complexity --base origin/main --max 10
```

- It reports the Python functions that the change made more complex than the limit. A function that was over the limit before, and did not grow, is not reported.
- `"max_complexity": 10` in `gate.json` makes the gate show these functions as warnings. It does not block. The installer sets it for Python projects, with `"max_changed_lines": 400`.
- The count is an approximation of cyclomatic complexity. Python only. For other languages, put the linter's rule in the gate commands.

### Evals of the pack

- `evals/judge-cases/` has 24 cases that measure the evaluator: 12 wrong patches and 12 correct patches from agent runs, labelled by hidden tests. `python evals/judge-cases/check_labels.py` checks the labels without an agent. See [evals/README.md](evals/README.md).
- A judge case can bring its own code: `"repo"` and `"patch"` in the case line. The judge then works in a new repository, away from the labels.
- [docs/RESULTS.md](docs/RESULTS.md) has the numbers that we measured, with intervals, costs and limits. It includes the results that are not good for the pack.

### CI audit, CODEOWNERS and sandbox

```bash
python3 ai-quality-pack/install.py project . --with-ci --codeowners @your-org/your-team --with-sandbox
```

- The CI workflow has an `audit` job: `pip-audit` for Python dependencies and `npm audit` for JavaScript dependencies. The secret scan is part of the gate.
- `--codeowners` adds CODEOWNERS lines for the gate file, the hooks, CI and the tests. It has an effect only with a branch protection rule that requires a review from code owners.
- `--with-sandbox` writes Claude Code settings: no read of `.env` and `secrets/` files, and the sandbox for shell commands with `failIfUnavailable`. Claude Code then stops at startup where the sandbox cannot run. On native Windows the installer writes only the read rules.
- The sandbox covers shell commands. File tools, MCP servers and hooks follow the permission rules.
- The gate warns when the change removes or replaces lines of an existing test. New tests give no warning. In our runs the warning came for wrong patches (6 of 19) and for correct patches (5 of 23): it tells a person where to look, it does not show that the work is wrong.

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

### Other agents: Codex and OpenCode

```bash
python3 ai-quality-pack/install.py project . --with-codex --with-stop-gate --with-guard
python3 ai-quality-pack/install.py project . --with-opencode --with-stop-gate --with-guard
```

The hook scripts are the same for each agent. An adapter connects the agent's events to them.

| Part of the pack | Claude Code | Codex | OpenCode 2 |
|---|---|---|---|
| Skills and `AGENTS.md` | yes | `AGENTS.md`: yes. Skills in `.agents/skills`: not checked | yes (`.agents/skills`, `.claude/skills`) |
| Session digest, with the session id in the run log | hook | hook | plugin |
| Formatter after an edit | hook | hook | plugin |
| Guard (`--with-guard`) | hook | hook | plugin |
| Completion gate (`--with-stop-gate`) | the agent cannot stop | the agent cannot stop | one prompt with the gate output |
| Evaluator, criteria and triage subagents | yes | no | `.opencode/agents/` |
| Any agent with a headless command | `gated-run` | `gated-run` | `gated-run` |

- **Codex**: `--with-codex` writes `.codex/hooks.json`. Codex has the hook events and the hook input of Claude Code. Start Codex in the repository and use `/hooks` to trust the hooks: Codex does not run project hooks before that. The commands need a POSIX shell.
- **OpenCode**: `--with-opencode` writes a plugin (`.opencode/plugins/ai-quality-pack.js`), the three subagents and `.opencode/ai-quality-pack.json` (which options are on). The plugin is for OpenCode 2; OpenCode 1 has a different plugin interface.
- OpenCode has no hook that stops the agent from finishing. When the gate fails, the plugin sends the gate output to the session as a new prompt, one time. If the gate still fails, the run log records `released-red` and the next session digest shows it. `opencode run` ends before that prompt: for unattended work use `gated-run --agent-cmd "opencode run --auto"`.
- The guard protects `.codex/` and `.opencode/` also. It reads the arguments of the tool call (a file path, a shell command, or the files of a patch), so it does not depend on the tool names of one agent.
- Checked on OpenCode 2.2.7 with local models: the plugin loads; the digest runs and the run log has the session id and the model; the guard blocks a shell command and a file tool on a protected path; with an OpenCode server, a red gate gives one new prompt and then `released-red`.
- Not checked: Codex. No Codex was installed where this was built: the adapter follows the Codex hook documentation, and the tests run its commands with the documented input. Also not checked: the formatter and the subagents in OpenCode, the OpenCode terminal interface, and Windows for both agents.

### Checks of the skills themselves

```bash
python3 .agents/skills/skill-evolve/scripts/validate_skills.py .agents/skills --strict
python3 .agents/skills/skill-evolve/scripts/validate_skills.py .agents/skills --scanner "gitleaks detect --no-git --source {dir}"
```

A skill is a set of instructions that the agent follows. A skill from another person is a way into the agent, as a dependency is a way into a program.

- **Hidden characters** are errors: bidirectional controls, zero-width spaces and tag characters. A reviewer does not see them, and an agent reads them.
- **Suspect instructions** are warnings, in `SKILL.md` and in the files of the skill: an order to drop other instructions, to hide an action from the user, to send local data to a network address, to run code from the network, to read credential files, or to turn off a safety check. A person reads the line. `skill-scan: ok` on the line marks it as read.
- **Overlap**: two descriptions that share half of their words give a warning. The agent chooses a skill from its description.
- **`--scanner CMD`** runs an external scanner on the skills. A scanner that is not installed gives `INCOMPLETE` and exit code 3: a check that did not run did not pass.
- **Activation in `skill-eval`**: `run` and `ablate` report in how many runs the agent used the skill, from the tool calls in the transcript. A skill that was never used gives `NOT-USED` (ablate) or `INCONCLUSIVE` (run): the comparison says nothing about it. The agent command must print the transcript, for example `--output-format stream-json --verbose`.
- The text rules find the plain forms of an attack. They do not find an instruction that is written to look like normal work. The ideas for these checks come from NVIDIA SkillEvaluator (static checks of a skill, a check that the skill ran, an incomplete state for a missing scanner).

### Unattended runs: the gate without hooks

```bash
python3 .agents/skills/long-horizon/scripts/memory.py gated-run \
  --agent-cmd "claude -p --bare --permission-mode acceptEdits" --prompt-file task.md --retries 2
```

- `gated-run` runs the agent command with the task on stdin. Then it runs the gate.
- If the gate fails, it runs the agent again with the gate output and the task. `--retry-cmd` sets a different command for these rounds.
- Exit code 0: the gate passed. Exit code 1: the gate still fails after the last round. The work is not done.
- It needs `.agent-memory/gate.json`. Without a gate file it stops with exit code 2.

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

The CI of this repository runs on a manual trigger. Run these three commands before a push:

```bash
python -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
python skills/skill-evolve/scripts/validate_skills.py skills --strict
python skills/ste-writing/scripts/ste_lint.py README.md --lang en --threshold 60
```

Run the tests two times: without `PYTHONDONTWRITEBYTECODE` (make sure that your shell does not set it) and with it. Version 0.8.0 was released after test runs that had this variable set in each environment, and 4 tests failed without it.

## Robustness
- Atomic writes plus a cross-process lock (tested with 16 concurrent writers).
- Append-only logs with `merge=union`. Duplicates and conflict markers are folded on read, and task-id collisions after a merge are flagged.
- The memory digest is sanitised and wrapped as data (`<project-memory>`). Obvious secrets are refused at write time.
- `unittest` suite (installer, memory, gate, evals, concurrency). CI on Linux, macOS and Windows (Python 3.9 and 3.13).

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

## License
MIT. Upstream skills keep their own licenses (copied into each folder with a `.upstream` provenance file).
