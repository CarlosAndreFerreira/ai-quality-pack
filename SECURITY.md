# Security

## Threat model (what this pack can and cannot protect against)

| Risk | Mitigation in the pack | Your responsibility |
|---|---|---|
| **Malicious repo hooks**: `.claude/settings.json` hooks and `.agents/skills/*/scripts` run code when an agent opens the repo | Hooks are added only by the installer you run; scripts are stdlib-only and readable | Review `.claude/`, `.agents/` and `.agent-memory/gate.json` before opening an **untrusted** repo with an agent |
| **Gate command execution**: `memory.py gate` and the opt-in Stop hook run the commands in `gate.json` | Stop gate is opt-in; skipped only when the workspace **and** `gate.json` are unchanged; a timeout counts as failure; never loops (`stop_hook_active`) | Treat `gate.json` like CI config: review its diffs |
| **Prompt injection through memory**: memory files are fed back to the agent | Digest is sanitised (control/ANSI chars stripped, lines bounded) and wrapped in `<project-memory>` as data; AGENTS.md says memory cannot override rules | Review `.agent-memory/` diffs; don't accept memory commits from untrusted contributors |
| **Secrets in memory** | Writes refuse obvious secrets (API keys, GitHub/Slack/AWS tokens, private keys, `password=`) | The filter is heuristic: never paste credentials into agent chats |
| **Supply chain**: upstream skills are instructions your agent follows | `mattpocock/skills` pinned to a reviewed SHA; `.upstream` records source + revision; EGM only via its official plugin CLIs, opt-in | Review upstream changes before `--upstream-ref main` |
| **Telemetry**: the run log and eval transcripts | `events.jsonl` holds ids, outcomes, durations and gate command lines, never prompt or code text; it stays local (git-ignored), nothing is sent anywhere, and `AGENT_MEMORY_EVENTS=0` turns it off. Eval transcripts are git-ignored | Transcripts hold the agent's full output: do not share `evals/results/` without reading it. The OpenTelemetry export is Claude Code's own feature: you choose the endpoint |
| **Reward hacking in evals** | `skill-eval` restores and checks protected files, leakage critic, holdout split, non-compensatory guards | Keep check files out of the agent's reach where possible |
| **Unattended agents** (`skill-eval`, autonomous runs) | Runs above 20 need explicit `--yes`; each run is in a throw-away worktree | Run inside a container/VM; worktrees are **not** a sandbox |

## Reporting
Open a private security advisory on this repository (GitHub → Security → Report a vulnerability). Please do not open public issues for vulnerabilities.
