# Changelog

## Unreleased
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
