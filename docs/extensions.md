# Extensions (not installed by default)

These projects were evaluated against the pack (November 2026). They are useful in specific situations, but they do not belong in the base install.

## Google Elephant-Goldfish Model (EGM) — `--with-egm`
Design-before-code flow: a context-rich "Elephant" session drafts a design doc, and stateless "Goldfish" sessions review it with no memory of the conversation. Apache-2.0. Installed through each agent's plugin CLI, because the skills need the full plugin (reviewer prompts, document standards).
- Claude Code: `claude plugin marketplace add google/elephant-goldfish-model && claude plugin install egm@egm`
- Antigravity CLI: `agy plugin install https://github.com/google/elephant-goldfish-model`
- Integration: `plan-before-code` routes large or irreversible changes to `/egm-brainstorm → /egm-draft → /egm-review → /egm-resolve`, then turns the approved doc into acceptance criteria.
- Caveat: not an officially supported Google product. The adoption claim ("thousands of Googlers") is usage, not a controlled study.

## GEPA / gskill — skill optimisation (advanced)
`skill-eval` *measures* one proposed change. GEPA's gskill *searches* for better skills: it generates verifiable tasks from a repository (SWE-smith) and evolves skills with `optimize_anything`, comparing with-skills vs without-skills runs, including Claude Code modes.
- Use when: a repo has many recurring agent tasks and a budget for hundreds of rollouts.
- Cost: high (rollouts × candidates). Set a budget before you start.
- Output: candidate skills. They still go through `skill-evolve` (validation, `skill-eval`, user approval).
- Repo: https://github.com/gepa-ai/gepa

## NVIDIA Auto-Ontology — data projects only
A semantic layer generated from database metadata (business terms → columns, certified metric SQL, relationships), served over MCP/CLI/API, so agents write SQL against certified definitions. Apache-2.0. Needs PostgreSQL 17 + pgvector.
- Use when: an agent answers questions over relational data (Postgres, Databricks, Snowflake, DuckDB).
- Not for: code quality. It is unrelated to this pack's purpose.
- Repo: https://github.com/NVIDIA/auto-ontology (no external pull requests accepted).

## Evaluated and not adopted
- **MIT Recursive Language Models**: an inference strategy for multi-million-token inputs. Coding agents already handle context with search and selective reads, and the cost has a long tail.
- **Microsoft Agent Framework / Copilot harness**: an agent runtime, not portable skills. Its building blocks (file memory, progressive skills, plan/execute todos, tool approval) confirm this pack's design. `microsoft/skills` is Azure-specific.
- **DeepSeek dsh-superagent**: ideas adopted (task IDs, isolated workers, needs-human queue). The always-on chat listener was not adopted, because of its prompt-injection surface and because the prototype has no sandbox.

## diagram-design (cathrynlavery) — diagrams for docs and ADRs
An agent skill that draws 45 diagram types as one self-contained HTML + SVG file in your brand, and can redraw draw.io, Mermaid and Excalidraw files. MIT. It does **not** research UI designs; its only network use is a homepage fetch for brand colours and fonts.
- Use when: architecture sketches, flows and quadrants for design docs (pairs well with EGM design docs).
- Caveat (from its README): the HTML output does not diff well in git; use Mermaid for diagrams that change often.
- Repo: https://github.com/cathrynlavery/diagram-design

## Evaluated and not adopted (continued)
- **Prime Agent (Prime Intellect)**: ideas adopted — a completion gate with change detection (`memory.py gate`, optional Stop hook), provenance and rollback for skill changes, a protected core, reward-hacking guards. The single-IPython-tool runtime and self-editing daemon were not adopted (they are a harness, not portable skills).
- **AMAP-ML LongHorizon-Harness**: ideas adopted — only verified results become state (already), stuck detection after repeated failures (`fail_streak` → ⚑), per-role model tiers (evaluator note). The Manager/Executor/Auditor runtime is a wrapper around agents, not skills.
- **mini-swe-agent**: confirms the minimal-scaffold principle (bash only, linear trajectory). Useful as a cheap, model-agnostic headless agent for `skill-eval` experiments where your main agent has no headless mode. Note that it does not read SKILL.md natively.
- **opencode**: reads `.claude/skills/*/SKILL.md` and `AGENTS.md` natively, so the pack works there without changes. Its per-skill permission patterns (`allow`/`ask`/`deny`) are worth using for risky skills.
- **jcode**: a fast Rust harness with multi-agent file-change notifications and embedding memory. It is a harness, not skills. Git worktrees cover the isolation need here.
- **Google Research RRSI**: ideas adopted in `skill-eval` — a noise-calibrated acceptance floor, non-compensatory guards, cost-aware acceptance, a held-out split, an auditable edit history, a leakage critic, pruning by ablation. The automatic fast-forward was replaced by human approval.
- **billion-context**: a context-compression proxy. Not adopted: TLS interception of model traffic, API keys forwarded, remote forced updates. Its useful ideas (reversible summaries, stable prefix, append-only logs) are already in the memory design.
