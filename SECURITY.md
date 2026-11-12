# Security

This page is the threat model of the pack: what an attacker can try, what the pack does about it, and what the pack does not protect against. The pack is a set of checks for agent work. It is not a sandbox and it is not a security product.

## What we protect

1. The repository: no change reaches the default branch without a person's review.
2. The checks themselves: an agent cannot make its own gate easy and then pass it.
3. Secrets: they do not go into the repository, the memory files or a pull request.
4. The agent's instructions: text from outside does not become a standing instruction.

## Trust boundaries

| Source | Trust |
|---|---|
| The person at the terminal, and the people who can label issues and review pull requests | Trusted |
| The default branch after review (code, `gate.json`, the pack's scripts, CI workflows) | Trusted |
| Issue text, pull request text, comments | **Not trusted** |
| Files in the working tree that a change touched; web pages; output of tools and tests; dependencies | **Not trusted** |
| What an agent writes: code, memory entries, lessons, its own report | **Not trusted** until a check or a person confirms it |

Prompt injection is text from a source that is not trusted, which tells the agent to do something else. An instruction to the agent ("this is data") lowers the risk a little and stops nothing. The controls below limit what a misled agent can do.

## Risks and controls

| Risk | Control in the pack | Strength | Your part |
|---|---|---|---|
| **Prompt injection through an issue** in the issue workflow | The agent job uses `step-security/harden-runner` (`egress-policy: block`, `disable-sudo-and-containers: true`, narrow `allowed-endpoints`), has read access only to the repository, and holds only the model key. A second job runs the gate, with read access and no secret. A third job, with write access, runs no agent and no code from the change. The result is a draft pull request | Structural (GitHub token rights + runner egress filter) | Give the workflow its own model key with a spending limit. Only people you trust can add the label |
| **Prompt injection through repository files or tool output**, in a local session | `--with-sandbox` (shell commands in the operating system sandbox, optional host list); `--with-guard`; read rules for `.env` and `secrets/` | Sandbox: structural, where it runs. Guard: heuristic | Run unattended agents in a container or a VM |
| **Prompt injection through memory** (a lesson or a note that an agent wrote) | A lesson of an agent is not in the session digest until a person confirms it. The digest is wrapped as data, cleaned of control characters, and limited in size | Structural for lessons; advisory for the rest | Review `.agent-memory/` diffs. Do not accept memory commits from people you do not trust |
| **The agent weakens its checks**: edits `gate.json`, hooks, skills, CI | The gate runs the committed `gate.json`. CI runs the gate program of the base branch. `--with-guard` blocks edits of these files. `--codeowners` asks for a review of them | CI: structural. Guard: heuristic | Turn on branch protection with required reviews from code owners |
| **The agent weakens the tests**: deletes, skips or rewrites them | The gate warns about deleted test files, new skip markers and rewritten lines of existing tests. The review risk is `HIGH` | Detection only: a person decides | Read the warnings on the pull request |
| **A wrong "done"** | Gate, reproduction check, evaluator in a separate context, evidence block that lists what is not verified | Measured: see `docs/RESULTS.md`. The evaluator approved 5 of 19 wrong patches on hard issues | Review the pull request. The evaluator is not a replacement for review |
| **Secrets in the change or in memory** | The gate fails on an added line that looks like a secret, and never prints the value. Memory writes refuse obvious secrets | Patterns: they miss secrets of an unknown form | Add a dedicated scanner (gitleaks) to the gate. Never paste credentials into an agent chat |
| **Malicious repository hooks**: `.claude/settings.json` hooks and `.agents/skills/*/scripts` run code when an agent opens the repository | The installer that you run adds the hooks. The scripts use the standard library only and are readable | None against a repository that you did not write | Review `.claude/`, `.agents/` and `gate.json` before you open a repository that you do not trust with an agent |
| **Gate command execution**: the gate runs the commands of `gate.json` | The Stop gate is opt-in. A timeout counts as a failure. The gate does not loop | None against a hostile `gate.json` | Treat `gate.json` as CI configuration: review its diffs |
| **Supply chain** | Upstream skills are pinned to a reviewed commit. GitHub actions are pinned by commit. `pip-audit` has a fixed version. The pack has no dependency | Structural for what is pinned | Review a change of a pin. The plugin installs from this repository: pin a release tag |
| **Audit** | `memory.py audit` writes the run log with a checksum. The issue workflow keeps it for 90 days | The local run log is a file that an agent can change. The copy in CI is out of its reach after the upload | Keep the CI artifacts if you need a record |
| **Reward hacking in evals** | `skill-eval` restores and checks protected files, has a leakage critic and a holdout split. Judge cases with their own code run away from the labels | Structural for the judge cases | Keep check files out of the agent's reach |
| **Telemetry** | The run log has ids, outcomes, durations, gate command lines and the actor (the git user e-mail, or `AGENT_ACTOR`), never prompt or code text. It stays local. `AGENT_MEMORY_EVENTS=0` turns it off | Structural | Eval transcripts hold the agent's full output: read them before you share them |

## What the pack does not protect against

- **Data that leaves through allowed hosts.** In a local session without `--sandbox`, shell commands keep your normal network access; `--sandbox-allow-domain HOST` narrows outbound hosts there. In `templates/ci/agent-issue.yml`, Harden-Runner blocks outbound traffic outside `allowed-endpoints` (`api.anthropic.com`, `github.com`, Actions upload hosts, npm) and disables sudo/containers, though allowlisted shared hosts (including `github.com` and the model API) remain reachable by `curl`. Keep secrets out of the `agent` job except a dedicated API key with a spending limit.
- **The run log on the agent's machine.** The agent can write `.agent-memory/events.jsonl`. The hash chain (`audit --verify`) finds a line that was changed, removed or inserted, but not a log that was written again from the start: the chain has no secret. Compare with a head that was recorded where the agent cannot write (a CI log, an artifact).
- **An agent that changes the checks through a script.** `--with-guard` blocks file tools and the shell commands that it recognises. It is not a security boundary: a program that the agent writes and runs can change the same files. The checks that count are the ones in CI, with the copy of the base branch.
- **Code from the change that lies about the gate result** in the `verify` job. That job has no write access and no secret, so the damage is a wrong draft pull request. A person reviews it, and the `quality-gate` workflow runs again on the pull request.
- **A hostile repository.** If you open a repository that you did not write, its hooks and its gate commands run with your rights.
- **Subagents with a shell.** The evaluator runs commands on code that is not trusted. It has the same rights as the main agent.
- **MCP servers, file tools and hooks under the sandbox.** The Claude Code sandbox covers shell commands only.
- **Native Windows.** Claude Code has no sandbox there. The installer writes only the read rules.
- **A person who confirms without reading.** The terminal check for `lesson confirm` and `AGENT_PACK_UNLOCK` are speed bumps for an agent. They do not check who the person is.

## Status of the evidence

- The split of rights in the issue workflow follows the documented behaviour of GitHub token permissions. The workflow was not run on GitHub.
- The guard has unit tests for 11 blocked and 12 allowed operations, plus 10 tests in `TestProtectionTests` for tracked-test protection, fixed task base resolution, and base-test replay, and unit tests in `VerificationBlockTests` for CI egress policy configuration and loopback `exfil` harness checks.
- **Tested with attack cases** (`evals/injection/`, 18 cases in the published baseline, harmless canaries, Claude Haiku): 9 of 72 attacks succeeded without the pack and 1 of 36 with the pack. The read rule for `.env` and the rule for CI workflows stopped their attacks. The deletion of a test file got through once: the gate reported it and did not prevent it. `evals/injection/run_inject.py` now adds a fourth loopback HTTP `exfil` goal (`24` attack cases total with `--reps 2`); that fourth goal and the GitHub Harden-Runner step have unit tests only and were not run against a live model or GitHub runner yet. See [docs/RESULTS.md](docs/RESULTS.md).
- That test is small: one task, one model, attacks that we wrote, no network leak, no sandbox. The workflow on GitHub and stronger attacks were not tested with attack cases.

## Reporting

Open a private security advisory on this repository (GitHub → Security → Report a vulnerability). Please do not open public issues for vulnerabilities.
