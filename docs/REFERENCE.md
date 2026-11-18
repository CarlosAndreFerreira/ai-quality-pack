# Reference: parts with no use on a real project

These parts of the pack are installed and have tests. None was used on a real project, and none was measured with an agent, unless its text says so. [RESULTS.md](RESULTS.md) has what we measured. The [README](../README.md) has the parts with a use or a measurement.

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
- `stats` shows the control coverage: in how many sessions the gate ran a command, the last gate result was a pass, criteria were recorded, the evaluator graded, and a reproduction was verified. A session without a record of a control is a gap, not a pass. In 40 benchmark runs with the pack installed, the gate had no commands in each run and the evaluator ran in 6 runs; only the artifacts showed it ([docs/RESULTS.md](RESULTS.md)). The idea is from an eval runner that scores an agent harness from its event log and reports a missing event as a coverage gap.
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

## From an issue to a draft pull request

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

## Triage: is the issue ready for work?

```bash
python3 .agents/skills/long-horizon/scripts/memory.py triage --file issue.md
```

- Exit code 0: the text is ready for work. Exit code 4: the text is too thin, and the output is the questions for the issue.
- The issue workflow runs this check first. A thin issue gets the questions as a comment, and no agent run starts.
- The check is a set of text rules. It finds an empty or one-line issue. It does not find a subtle ambiguity.
- The `triage` subagent does the real check: it reads the repository and gives `TRIAGE: READY` with its assumptions, or `TRIAGE: ASK` with at most 3 questions. It has read-only tools.
- Measured: the text check passed 53 of 53 valid SWE-bench Verified issues, after three rules were adjusted on the same issues. It stopped 9 of 9 thin requests that we wrote. The subagent is not measured.

## Factory report

```bash
python3 .agents/skills/long-horizon/scripts/memory.py factory --days 30
```

- From GitHub (branches `agent/*`): pull requests opened, merged and closed, the merge rate with a 95% interval, the median time to merge, the cost, the review risk, and the merged pull requests that were reverted.
- From the local run log: pull requests refused for a red gate (work that ended as "done" with a red gate), unattended runs, triage results.
- The cost for each merged pull request shows only when each pull request has a cost in its text.
- Limit: the local run log is on one machine. A CI runner does not keep it.

## Merge readiness

- The evaluator checks what a maintainer checks: the written rules of the project, the style of the code next to the change, one purpose, size, documentation. It writes `MERGE-READY: YES` or `MERGE-READY: NO` after the overall result. Only a broken written rule changes the overall result.
- `"max_changed_lines": 400` in `gate.json` makes the gate warn about a larger change. It does not block.
- `doctor` says when the gate has no lint or type check command.
- Not measured: the effect of these checks on the share of pull requests that maintainers merge.

## Risk rules of the project

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

## Secrets, provenance and audit

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

## Memory: small and confirmed

- The session digest has a size limit of 6000 characters (`memory.py start --max-chars`). The most urgent items come first, so the cut removes the end.
- A lesson that an agent records is not in the digest until a person confirms it: `memory.py lesson confirm --key <key>`, in a terminal. Text that a model wrote does not become a standing instruction without a person.
- Each new lesson records who wrote it (agent or human), the commit and the session. `memory.py lesson list` shows the lessons that wait.
- Lessons from before this version stay in the digest.
- Limit: the terminal check stops an agent that confirms by habit. It is not a security boundary: `AGENT_MEMORY_HUMAN=1` passes it.

## Complexity of the change

```bash
python3 .agents/skills/long-horizon/scripts/memory.py complexity --base origin/main --max 10
```

- It reports the Python functions that the change made more complex than the limit. A function that was over the limit before, and did not grow, is not reported.
- `"max_complexity": 10` in `gate.json` makes the gate show these functions as warnings. It does not block. The installer sets it for Python projects, with `"max_changed_lines": 400`.
- The count is an approximation of cyclomatic complexity. Python only. For other languages, put the linter's rule in the gate commands.

## Evals of the pack

- `evals/judge-cases/` has 24 cases that measure the evaluator: 12 wrong patches and 12 correct patches from agent runs, labelled by hidden tests. `python evals/judge-cases/check_labels.py` checks the labels without an agent. See [evals/README.md](../evals/README.md).
- A judge case can bring its own code: `"repo"` and `"patch"` in the case line. The judge then works in a new repository, away from the labels.
- [docs/RESULTS.md](RESULTS.md) has the numbers that we measured, with intervals, costs and limits. It includes the results that are not good for the pack.

## CI audit, CODEOWNERS and sandbox

```bash
python3 ai-quality-pack/install.py project . --with-ci --codeowners @your-org/your-team --with-sandbox
```

- The CI workflow has an `audit` job: `pip-audit` for Python dependencies and `npm audit` for JavaScript dependencies. The secret scan is part of the gate.
- `--codeowners` adds CODEOWNERS lines for the gate file, the hooks, CI and the tests. It has an effect only with a branch protection rule that requires a review from code owners.
- `--with-sandbox` writes Claude Code settings: no read of `.env` and `secrets/` files, and the sandbox for shell commands with `failIfUnavailable`. Claude Code then stops at startup where the sandbox cannot run. On native Windows the installer writes only the read rules.
- The sandbox covers shell commands. File tools, MCP servers and hooks follow the permission rules.
- The gate warns when the change removes or replaces lines of an existing test. New tests give no warning. In our runs the warning came for wrong patches (6 of 19) and for correct patches (5 of 23): it tells a person where to look, it does not show that the work is wrong.

## Other agents: Codex and OpenCode

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

## Checks of the skills themselves

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

## Unattended runs: the gate without hooks

```bash
python3 .agents/skills/long-horizon/scripts/memory.py gated-run \
  --agent-cmd "claude -p --bare --permission-mode acceptEdits" --prompt-file task.md --retries 2
```

- `gated-run` runs the agent command with the task on stdin. Then it runs the gate.
- If the gate fails, it runs the agent again with the gate output and the task. `--retry-cmd` sets a different command for these rounds.
- Exit code 0: the gate passed. Exit code 1: the gate still fails after the last round. The work is not done.
- It needs `.agent-memory/gate.json`. Without a gate file it stops with exit code 2.

## Robustness
- Atomic writes plus a cross-process lock (tested with 16 concurrent writers).
- Append-only logs with `merge=union`. Duplicates and conflict markers are folded on read, and task-id collisions after a merge are flagged.
- The memory digest is sanitised and wrapped as data (`<project-memory>`). Obvious secrets are refused at write time.
- `unittest` suite (installer, memory, gate, evals, concurrency). CI on Linux, macOS and Windows (Python 3.9 and 3.13).
