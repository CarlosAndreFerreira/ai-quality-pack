# AI Quality Pack — what to build next, and why

Date: 2026-11-12. Base: the pack at commit `95ce9b2`, and a benchmark of the pack that is kept outside this repository.

Evidence tags: **[code]** checked in the pack or in the benchmark results; **[cited]** read in the primary source; **[abstract]** only the abstract was read; **[hypothesis]** not tested; **[not verified]** the page could not be opened.

The sources were read by automated searches on 2026-11-12, through a tool that summarises each page. Check table values against the source before you cite them elsewhere.

## 1. Conclusion

The first problem the pack must solve is the false "done": the agent delivers a wrong fix and says that it is correct. The benchmark measured this in 18 of 43 runs on the hard issues of SWE-bench Verified [code]. Research from 2025–2026 measures the same thing: agents predict 61–77% success when the real rate is 22–35% [cited: Kaddour et al., arXiv 2602.06948].

The pack's LLM evaluator, as it is, does not solve this. It grades criteria that the agent itself wrote, and it approved wrong fixes on `astropy-14369` and `pylint-4551` [code]. The literature explains why and points to three corrections that have evidence: take the author's narrative away from the evaluator, give it an independent executable signal (a reproduction test), and calibrate it with examples.

Test tampering, memory and complexity metrics have weaker evidence or a low incidence in our data. They come later.

## Status at version 0.8.0 (2026-11-16)

Each item of this plan has code or documentation in the pack. "Measured" means a run with an agent, or a check on real patches. [docs/RESULTS.md](RESULTS.md) has the numbers.

| Item | In the pack | Measured |
|---|---|---|
| E0 Evals of the pack | `evals/judge-cases/` (24 cases), `evals/injection/` (18 attack cases), `docs/RESULTS.md` | Yes: 0 of 12 wrong patches approved, 3 of 12 correct patches rejected. A short release check exists (2 tasks, 12 runs); the full regression suite does not |
| E1 Evaluator without the author's narrative | Evaluator rewritten, `criteria` subagent, `diff-view` | Yes: no measurable gain against the older evaluator on 42 patches |
| E2 Reproduction before the fix | `memory.py repro` | No |
| E3 Calibrate the evaluator | `skill-eval judge`, with more than one run for each case and a rule for the result | One run for each patch: 5 of 19 wrong SWE-bench patches approved. 3 runs with the rule of the pack: 1 of 19 wrong patches approved, 17 of 23 correct patches rejected. The evaluator does not separate wrong from correct patches on these issues. `install.py --evaluator-model` puts it on another model: on the 24 shipped cases, Sonnet approved 7 of 12 wrong patches against 0 of 12 for Haiku (one type of defect); on the 42 patches, 13 of 19 against 2 to 4, with an agreement near zero for the two models |
| E4 Statistics | Paired interval, `pass^k` with its interval and the cost for each passed run, a cost limit, `power` | Not applicable |
| E5 Protect tests and gate | Committed gate file and fixed base; the gate fails when it has no commands; warnings for deleted and changed tests and skip markers; `block_test_changes`; guard for tracked tests; CI runs the checker of the base branch | In part: the warning for changed tests does not separate wrong from correct patches. In the injection set, the deletion of a test succeeded in 1 of 12 runs with the pack, before `block_test_changes`. No run on ImpossibleBench |
| E6 CI and isolation | Gate and audit workflow, pinned actions, `--codeowners`, `--with-sandbox` with a host list, `--with-guard`, three jobs with separate rights and an egress policy in the issue workflow | No: not run in CI. The read rule for `.env` and the rule for CI workflows held in the injection set |
| E7 Smaller memory | Digest size limit, lessons confirmed by a person | No |
| E8 Complexity | `memory.py complexity`, gate warning | No. Property tests and mutation tests are not built |
| F1 Install | Plugin, marketplace, `doctor`, `uninstall`, adapters for Codex and OpenCode 2 | Plugin: 2 agent sessions on Linux. OpenCode: checked with local models. Codex: not run |
| F2 Gate without hooks | `memory.py gated-run` | No: tested with a simulated agent |
| F3 From an issue to a run | Issue workflow template | No: not run on GitHub |
| F4 Triage | `memory.py triage`, `triage` subagent and skill | Text check: 53 of 53 valid issues pass, after tuning on them. Subagent: no |
| F5 Pull request with evidence | `memory.py pr`, `evidence` with review risk and cost, risk rules of the project with waivers that a person records; the evidence says when the branch is behind the default branch, which changed files the graded features cover, and which criteria name code | No: tested with a simulated GitHub CLI |
| F6 Merge readiness | Evaluator step, `max_changed_lines`, `doctor` note | No |
| F7 Few human decision points | README, "Operating rules" | Not applicable |
| F8 Factory report | `memory.py factory` | No |
| F9 Parallel work | README, "Operating rules" | Not applicable |
| F10 Governance | Secret scan in the gate, `provenance`, `audit` with a hash chain and the identity of each run, `stats` with the control coverage of the sessions, threat model, checks of skill files | Secret scan: 0 false alarms in 3,673 added lines. Prompt injection: 9 of 72 attacks succeeded without the pack, 1 of 36 with the pack |

The core pack of version 0.6.0 against the bare agent on 20 hard issues showed no difference that the sample can show, and the gate had no commands in those runs. What comes next is measurement, not features: a gate that has commands and a mandatory evaluator against the bare agent on hard issues, and what the evaluator can check on a hard issue (a stronger model for the evaluator was not better on the 24 cases and on the 42 patches). Version 0.8.0 adds verdicts from records that a command wrote (`counterexample`, `verdict`, `verdict_evidence`, `mutants`): on the 42 patches the 3 counterexamples of type `regression` were on wrong patches, and `memory.py verdict` itself is not measured. On one real project, a gate, a reproduction and an independent evaluator found a defect that the tests of the author did not find: one case, not a rate.

## 2. Proposals, by priority

### E0. Evals of the pack itself, included and published
This comes first because every other proposal needs it to be measured.

- **State in the pack:** the tool exists (`skill-eval`), but the pack ships no evaluation of itself. There is no way to know if one version is better than the one before [code].
- **Evidence:**
  - We know that the full pack does not beat its core, and that the evaluator approves wrong fixes, only because we measured [code].
  - Anthropic recommends starting with 20 to 50 tasks taken from real failures, preferring deterministic graders, keeping a reference solution per task, isolating trials and reading transcripts [cited: demystifying-evals-for-ai-agents].
  - Claude Code already has plugin evals as a concept [cited: code.claude.com/docs/en/plugins].
- **How, in three levels:**
  1. **Evaluator calibration set, inside the pack.** Pairs of a correct patch and a wrong patch with a known verdict. It runs in minutes and measures how often the evaluator approves wrong code. Starting point: the 41 benchmark patches with an official verdict (18 false "done", 23 resolved). It is the base of E3.
  2. **Regression suite of the pack, in the repository but outside the installer.** 20 to 30 tasks that the agent fails without the pack, plus some that it solves, to detect harm. It runs before each release with the arms "no pack" and "with pack", and reports false "done", `pass^k` and cost.
  3. **External benchmark, outside the repository.** SWE-bench Verified and ImpossibleBench stay in the harness (185 GB of images, hours of run time). The pack publishes the protocol and the results.
- **What not to do:**
  - Do not run agent evals on each push: they spend tokens and need credentials in CI. CI runs the deterministic tests; evals run per release.
  - Do not include tasks that the agent always solves without the pack: 23 of our 25 self-written tasks were like that and measured nothing [code].
  - Do not leave tasks and answers within reach of the agent under test: in one reported case an agent read the git history of earlier trials [cited: demystifying-evals-for-ai-agents].
- **Obligation:** results are published also when they get worse, with intervals and cost.

### E1. The evaluator sees the issue and the diff, never the author's narrative or criteria
- **State in the pack:** `evaluator.md` tells the evaluator to load the criteria with `memory.py feature show`, and the implementing agent wrote those criteria [code].
- **Evidence:**
  - Author text misleads automated reviewers: refined PR descriptions got 32 of 33 re-introduced vulnerabilities accepted (Claude Code 17/17); hiding the description recovered 50%, and hiding all metadata recovered the rest [cited: Alexopoulos et al., arXiv 2603.18740].
  - A "confirm it is correct" review has an AUROC of 0.51–0.58, close to chance; asking to "find bugs" cuts overconfidence by 13–15 points [cited: arXiv 2602.06948].
  - Separating who writes the tests from who writes the code: pass@1 from 71.3 to 79.9 on HumanEval, and test accuracy from 61.0 to 87.8 [cited: AgentCoder, arXiv 2312.13010].
  - Anthropic reports the same defect ("found real issues, then talked itself into approving") and fixed it with a hard threshold per criterion [cited: harness-design-long-running-apps].
- **How:** a "criteria" subagent with `Read, Grep, Glob` only gets the issue and writes criteria and acceptance tests before the implementation. The evaluator gets the issue, the criteria and the diff; new comments in the diff are removed from the view that it reads.
- **Risk:** the cost of one more subagent. In our pilot the evaluator already doubles the cost [code].

### E2. Reproduction before the fix, checked by the gate
- **State in the pack:** not present. `tdd-loop` is a rule in text [code].
- **Evidence:**
  - Filtering patches by a generated test that goes from fail to pass more than doubles precision (47.8%, at 20% coverage) [cited: SWT-Bench, arXiv 2406.12952].
  - On 22 SWE-bench Verified systems, precision rises to 65–92% at 30–41% coverage; one system went from 60.8% to 91.9% [cited: Otter, arXiv 2502.05368].
  - Reproduction coverage rose to 63% in 2025 [abstract: e-Otter++, arXiv 2508.06365].
  - SWE-agent already asks for a reproduction script and says to run it again before submitting [cited: config/default.yaml].
- **How:** `memory.py repro --test <command>` runs the test on the base commit (it must fail) and on the current code (it must pass), and records the result. The final report has three states: "done, with reproduction", "done, without reproduction" and "not done".
- **Limit:** the signal exists only when the agent can reproduce the problem; in the other cases the pack must say that it did not verify. A test written by the same context can share the wrong reading of the issue, so E2 works better with E1 [hypothesis].

### E3. Measure and calibrate the evaluator
- **State in the pack:** nobody knows how often it approves wrong code. The evaluator does not set `model:` [code].
- **Evidence:**
  - Text-only judges reject 3–46% of wrong patches (Claude 3.7 Sonnet 7.9%); a judge with execution reaches 61%, but rejects 16.9% of correct ones [cited: BouncerBench, arXiv 2506.17812].
  - With human-refined rubrics: recall 0.94 and precision 0.80 on unanimous cases [abstract: Shi et al., arXiv 2511.10865].
  - A reviewer of a different model did not clearly improve calibration (N=25) [cited: arXiv 2602.06948].
- **How:** a calibration set from the benchmark patches. Report sensitivity, specificity and MCC. Add an "unknown" verdict [cited: demystifying-evals-for-ai-agents].

### E4. Statistics of `skill-eval`
- **State in the pack:** Wilson interval and sign test; no `pass^k`, no paired difference with an interval, no power calculation [code].
- **Evidence:**
  - Paired differences cut variance by about one third at correlation 0.5; detecting 3 points at 80% power needs about 969 items [cited: Miller, arXiv 2411.00640].
  - `pass^k`: 75% per trial is about 42% for three in a row [cited: Anthropic, demystifying-evals]; in τ-bench, `pass^8` is under 25% [cited: arXiv 2406.12045].
  - Consistency between runs improved little over 24 months of models [cited: Rabanser et al., arXiv 2602.16666].
  - Comparing without a cost control confuses quality with brute force [cited: Kapoor et al., arXiv 2407.01502].
- **How:** `skill-eval power --delta --rho`, `pass^k` in the report, the interval of the paired difference, and cost next to the rate.

### E5. Protect tests, gate and hooks with deterministic checks
- **State in the pack:** a rule in text; the agent can edit `gate.json`, hooks and tests [code].
- **Evidence:**
  - Claude models cheat mostly by editing tests; LLM monitors detect 42–65% on SWE-bench; read-only tests stop the edit but not special-casing; an explicit "cannot do it" exit cut GPT-5 cheating from 54% to 9% [cited: ImpossibleBench, arXiv 2510.20270].
  - "Do not cheat" instructions have a negligible effect [cited: METR, 2025-06-05].
  - On unambiguous problems cheating is rare (0–3.4%) [cited: EvilGenie, arXiv 2511.21654], which agrees with our zero tampering in about 350 runs [code].
- **How, by cost:**
  1. The gate reads `gate.json` from the base branch, as Cursor Bugbot does with its configuration [cited: cursor.com/docs/bugbot].
  2. The gate reports deleted tests and new skip markers under "Needs you".
  3. `deny` rules and a PreToolUse hook on `.claude/hooks/**` and `gate.json`. The mechanism exists, but it does not catch a script that writes the file, and the documentation says it is not a security boundary [cited: code.claude.com/docs/en/permissions].
- **Medium priority:** cheap, but the measured incidence is low.

### E6. CI as the final authority, and isolation
- **State in the pack:** no CI template; `actions/checkout@v4` by tag; no sandbox or permissions [code].
- **Evidence and practice:**
  - GitHub recommends pinning actions by SHA, a read-only `GITHUB_TOKEN`, and CODEOWNERS on the workflow folder [cited: docs.github.com, secure-use].
  - The Copilot agent cannot approve or merge its own PRs, and workflows run only after a human approves [cited: docs.github.com, risks-and-mitigations].
  - The Claude Code sandbox covers shell commands only, does not exist on native Windows and, without `failIfUnavailable`, runs with no isolation and no warning [cited: code.claude.com/docs/en/sandboxing].
- **How:** a workflow template with the gate, `pip-audit` and `gitleaks`; CODEOWNERS for tests, gate and workflows; the installer offers the sandbox with `failIfUnavailable` and a read `deny` on `.env`, and says where it is not supported.

### E7. Memory: reduce it, do not extend it
- **Evidence:**
  - The bare agent solved 9 of 9 multi-session tasks without the pack's memory [code].
  - In 11 of 12 pairings a memory system did not beat no memory; only verified experience injected by an oracle helped (+1.1 to +4.5 points) [abstract: VibeMemBench, arXiv 2609.23570].
  - LLM-generated context files do not raise success and raise cost by 20–23% [cited: arXiv 2602.11988].
- **How:** a size limit on the digest; lessons with author and commit; agent lessons enter the digest only after they are confirmed [cited: OWASP ASI06]. Path scoping and time decay have no evidence that justifies them now.

### E8. Later, only with a measurement
- **Complexity gate:** repositories that adopted Cursor had +41.6% complexity [cited: He et al., arXiv 2511.04427], and feeding static analysis back to the agent reduces the problems [abstract: arXiv 2508.14419]. A `C901` rule in the Python profile is cheap.
- **Property-based tests and mutation on the diff:** feasible (56% of agentic PBT reports were valid [abstract: arXiv 2510.09907]), but expensive and with no measured link to the false "done".
- **Claude Code plugin format** and managed settings for companies [cited: code.claude.com/docs/en/plugins].

## 3. From pack to product: what is missing to work like a factory

Question: what is missing for the pack to be a daily product where an issue goes in and verified code comes out.

### Thesis
The market already has the assembly line: Copilot cloud agent, Codex cloud, Devin, Factory, Symphony and the Claude Code GitHub Action take an issue and open a PR [cited: the documentation of each]. One more orchestrator is not new, and the ground is hard: Vibe Kanban closed for lack of a business model, and Jules is being wound down [cited: vibekanban.com/blog/shutdown; jules.google/docs/changelog].

What the market lacks is **quality control for the line**. The bottleneck moved from writing to reviewing: +98% merged PRs, +91% review time, +154% PR size, with no gain at company level [cited: Faros 2025, vendor telemetry]. And passing the tests is not enough: maintainers accepted 24 percentage points fewer PRs than the automated grader approved [cited: METR, 2026-03-10].

**Proposed position:** the pack is the quality-control station that connects to any line. Its product is a small, verified PR with the evidence attached, plus a calibrated and measured "done".

### What is missing, in order

**F1. One-command install, diagnosis and uninstall**
- **Today:** `git clone` and a Python script with options; no diagnosis and no uninstall [code].
- **Practice:** the most adopted add-ons install through a plugin marketplace or `npx`, and several have a `doctor` command; only one documents uninstall [cited: READMEs of superpowers, everything-claude-code, claude-mem].
- **How:** package as a Claude Code plugin with a marketplace, keep the installer for other agents, and add `doctor` and `uninstall`.
- **Limits of the format:** a plugin cannot ship the main status line, and an `enabledPlugins` entry in the repository does not download the plugin for each collaborator [cited: code.claude.com/docs/en/plugins].

**F2. A technical risk to resolve now: hooks do not run in `--bare` mode**
- The non-interactive mode `claude -p --bare` skips hooks, skills, plugins and `CLAUDE.md`, and the documentation says it will become the default for `-p` [cited: code.claude.com/docs/en/headless].
- **Consequence:** in an unattended factory the Stop-hook gate may not exist. The gate must also be an explicit step of the pipeline and of CI, not only a hook.

**F3. Intake: from the issue to the run, with a budget**
- **Today:** interactive session only [code].
- **How:** a workflow template with `anthropics/claude-code-action`, where the `prompt` is a pack skill, started by a label on the issue, with `--max-turns` and `--max-budget-usd` [cited: code.claude.com/docs/en/github-actions and cli-reference].
- **Why a budget:** the same task varies up to 30 times in tokens between runs [abstract: arXiv 2604.22750].

**F4. Triage at intake: ask or refuse before writing code**
- Without being forced, Sonnet 3.5 missed 81% of the cases that needed clarification; with interaction it recovers about 80% of full-specification performance [cited: Ambig-SWE, arXiv 2502.13069].
- **How:** a readiness check of the issue. If information is missing, the output is a question on the issue, not a PR.
- **Where to start:** the task types with the highest merge rate: documentation 84%, CI 79%, build 74%, fix 64% [cited: arXiv 2601.15195].

**F5. Output: a small PR with evidence attached, never merged by the agent**
- **Why:** in 562 rejections of agent PRs, 38% were abandoned without review, 23% were duplicates, 17% failed CI and only 3% were incorrect; each failed CI check lowers the merge odds by about 15% [cited: arXiv 2601.15195].
- **Market norm:** Copilot, Kiro, Jira and Devin never merge; the human decides [cited: the documentation of each].
- **How:** a draft PR only after a green gate, with a duplicate check and a fixed block: the reproduction result (E2), the gate commands and result, the evaluator verdict, what was not verified, cost and a risk label.
- **Limit:** we found no controlled study that measures if attached evidence reduces review time. It is a hypothesis to measure.

**F6. "Ready to merge" criteria beyond the tests**
- The 24-point gap between the automated grader and maintainers comes from quality and repository conventions [cited: METR, 2026-03-10].
- **How:** the evaluator checks project conventions and diff size; the gate includes lint.

**F7. Few human decision points, by risk**
- Users accept 93% of permission prompts [cited: Anthropic, claude-code-auto-mode].
- **How:** three points only: the question at intake, plan approval for large tasks, PR review.

**F8. Factory dashboard**
- **Today:** local `memory.py stats` [code].
- **How:** aggregate per repository the false "done" rate, the merge rate, time to merge, cost per merged PR and stability.
- **Why:** DORA 2025 links AI to more throughput and less stability [cited: the report's blog post]. We found no primary source with a measured cost per merged PR.

**F9. Parallel work: use what exists, with one rule**
- Coordination between agents fails in documented ways: 20 agents with the throughput of 2 to 3; frequent merge conflicts and agents that undo each other's fixes [cited: cursor.com/blog/scaling-agents; anthropic.com/engineering/building-c-compiler].
- **How:** do not build an orchestrator. One rule: one issue, one worktree, one PR, and no tasks that share files.

**F10. Governance**
- OpenSSF guide: no secrets in code, check that packages exist, pin versions, SAST and dependency checks in CI, and identify AI-generated code [cited: best.openssf.org].
- **How:** an audit log (the run log exists), secret scanning in the gate, and a configurable provenance mark.

### What not to build
- **Heavy specifications.** An observational study of 88,052 PRs supported none of five hypotheses in favour of spec-driven development [cited: ESEM 2026]. Acceptance tests are worth more than documents: with human-written tests, one flow reached 94.3% on SWE-bench Verified [abstract: arXiv 2510.23761].
- **TDD instructions in text.** Alone they raised regressions to 9.94%; giving the agent the list of affected tests lowered them from 6.08% to 1.82% [abstract: arXiv 2603.17973].
- **Simulated services and no human review at all**, as in the StrongDM factory, which spends $1,000 per engineer per day in tokens [cited: factory.strongdm.ai]. The idea to keep is another one: scenarios stored out of the agent's reach, which is proposal E1.

### Minimum product
1. F1 and F2: an installable plugin, and a gate that runs without hooks.
2. F3 and F5 together: a label on an issue produces a draft PR with the evidence attached.
3. F4: triage at intake.
4. F8: the dashboard numbers.

## 4. Ontologies and semantic layers: are they a good upgrade?

### Verdict
As a general upgrade of the pack, no. The evidence in favour is concentrated in weak models, in questions about company data and in multi-hop reasoning over documents. No study that we found shows that a glossary, a domain model or an ontology changes the correctness of an agent's code. Three narrow uses justify a test.

### The two projects that were proposed
- **NVIDIA Auto-Ontology** (announced 2026-10-21, Apache-2.0): an LLM reads database schemas, samples values, extracts business terms mapped to columns and infers joins; a human certifies. Read-only MCP server. No OWL or RDF, no published evaluation numbers [cited: github.com/NVIDIA/auto-ontology, README]. It is a semantic layer for text-to-SQL, not a code ontology.
- **Open Ontologies** (MIT, Rust): an MCP server with OWL reasoning, SHACL, SPARQL and a plan, apply, drift and rollback cycle. Evaluated only by its author [cited: github.com/fabio-rovai/open-ontologies]. It validates ontologies that someone must write first.

### Evidence against
- **Repository graphs help strong agents little.** RepoGraph: +2 to +2.7 points on SWE-bench Lite with 2024 models, at 6–30% more cost [cited: arXiv 2410.14684]. The large gains are with weaker open models [abstract: arXiv 2503.09089, 2505.16901]. Grep retrieval is "comparable to sophisticated graph-based baselines" [abstract: arXiv 2601.23254].
- **The published GraphRAG gains were largely an evaluation artefact.** LightRAG win rate over plain RAG: 66.7% as published, 39.06% after debiasing [cited: arXiv 2506.06331]. Graphs help only complex reasoning, at 40 to 350 times the tokens per query [cited: arXiv 2506.05690].
- **Ontologies built by LLMs are not reliable.** OLLM: literal F1 of 0.093 and 97 cycles in the generated taxonomy [cited: arXiv 2410.23584].
- **Graph memory does not beat plain text.** Mem0 graph variant: +1.6 points for twice the tokens, and all systems lose to full context [cited: arXiv 2504.19413].
- **A stale semantic artefact is worse than none.** In 320 runs, 90.1% of agent choices followed the stale instruction file and not the code. One precedence sentence raised code-following from 4.2% to 91.4% [abstract: arXiv 2610.30571].

### Evidence in favour
- **Questions about company data.** GPT-4 accuracy on enterprise SQL: 16% to 54% with an ontology layer [abstract: arXiv 2311.07509; one domain, vendor authors, a 2023 model].
- **Requirement ambiguity is a real problem,** but the solution with evidence is to ask, not to model [cited: arXiv 2502.13069].
- **Computed semantics of the code works.** Feeding static analysis back to the agent: insecure code from over 40% to 13% [cited: arXiv 2508.14419].

### What is worth a test
1. **LSP diagnostics after each edit.** Claude Code has official plugins for 13 languages [cited: code.claude.com/docs/en/plugins/code-intelligence]. The installer can suggest them.
2. **A minimal glossary, written by humans, with a precedence rule:** "in a conflict, the code and the tests win". No direct evidence [hypothesis].
3. **A data semantic layer, only for repositories that write SQL over company data.**

## 5. What not to do

- **Do not add rules in text to `AGENTS.md`.** The cost is certain and the gain is not shown [cited: arXiv 2602.11988]; the full pack never beat its core [code].
- **Do not sign receipts with a key that the agent can read.** `workspace_hash` exists; the real separation is in CI.
- **Do not add retry cycles against the gate.** Allowing several submissions raised cheating from 33% to 38% [cited: ImpossibleBench].

## 6. Order of work

1. Finish the comparison of the bare agent against the evaluator-gate arm on the 20 failed issues.
2. E0 level 1 and E3 together: build the calibration set from the 41 graded patches and measure the evaluator's error rate.
3. E1 and E2 as new arms on the same 43 issues, with this criterion: 15 points less false "done", no harm to resolved issues, cost at most 2 times.
4. E4 in parallel, because it needs no agent runs.
5. E5 with a subset of ImpossibleBench.

### After the measurement of the gate (2026-11-23): improvements to do

The measurement is in [RESULTS.md](RESULTS.md), "A gate that has commands, and a mandatory evaluator, against the bare agent". The records had no PASS for 32 of 37 correct patches and for 29 of 37 wrong patches [code]. The agent then said "not done" for 29 of 38 correct patches, and the two pack arms resolved fewer issues than the bare agent [code]. None of the items below is implemented or measured.

What the literature says about this result:

- LLM reviewers frequently mark correct code as wrong, and a more elaborate prompt can make this worse ([arXiv 2603.00539](https://arxiv.org/abs/2603.00539), [arXiv 2508.12358](https://arxiv.org/abs/2508.12358)) [abstract].
- An LLM judge of patches is useful for triage and is not sufficient as the only oracle (ESEM 2026, 326 patches) [abstract].
- The best systems write a test that fails before the fix and passes after it for 63% to 66% of the issues, and such a test is not a complete oracle ([arXiv 2508.06365](https://arxiv.org/abs/2508.06365), [arXiv 2607.28871](https://arxiv.org/abs/2607.28871)) [abstract].
- The selection of one patch from many candidates, with tests, gave 5 to 10 points more resolved issues in one study, and 26.2% to 32.8% in a second study ([arXiv 2602.05242](https://arxiv.org/abs/2602.05242), [arXiv 2510.22775](https://arxiv.org/abs/2510.22775)) [abstract].
- An agent can give a probability of success before, during and after the work, and the calibration of that number can be measured ([arXiv 2602.06948](https://arxiv.org/abs/2602.06948)) [abstract].

Improvements, in the order of the work:

1. **Done on 2026-11-24: the 32 runs without a PASS on correct patches, and the 29 on wrong patches, are classified** (the table is in RESULTS.md). The result changes this list:
   - The largest class is a rule of the pack: no PASS because the test was recorded after the change (12 correct and 12 wrong patches). The model found no defect in these runs. Thus item 3 repairs a smaller part than we thought.
   - To accept a later test is not the repair, because the 12 wrong patches then get a PASS. A test that the author writes after the fix agrees with the fix.
   - Item 2 has more support: a `regression` counterexample for behaviour was the last record for 7 wrong patches and for 0 correct patches [code].
   - A new item comes from this: with `require_evaluator`, the agent must know at the start of the session that criteria and a test are recorded before the change. Now it learns this at the Stop hook.
2. **The text of the evaluator does not block a stop.** With `require_evaluator`, only a `regression` counterexample that a command verified blocks: it was correct in 3 of 3 cases, and in 7 of 7 in the classification above [code]. Implemented on 2026-11-24 as `"require_evaluator": "regression"`; not measured with an agent. Not implemented: a `regression` record for a lint command blocks also, and the gate is the correct place for lint. A FAIL in text becomes a warning in the report for the person who reviews.
3. **Shorter instructions for the evaluator, with the same weight for PASS and FAIL.** Remove "assume the change is wrong". Each defect must quote the sentence of the requirement that it breaks. An edge case that the request does not name goes under "Not verified", not under FAIL.
4. **Measure items 2 and 3 on the patches that we have.** Run only the evaluator on the 74 patches of the mandatory-evaluator arm, which have a known answer. This costs much less than a new comparison of 240 runs.
5. **Report the precision of "done" and the share of correct patches that the agent calls done.** The rate of false "done" alone gives the best score to an agent that always says "not done".
6. **A confidence in place of "done" or "not done".** The agent gives a probability and the list of what it did not verify. Measure the calibration before any use of the number.
7. **Selection in place of a veto.** Use the cost of the mandatory evaluator (5.6 times the bare agent [code]) to make 3 to 5 candidate patches and to select one with tests. This changes what the pack is, and it needs a new measurement.

## 7. Limits

- Almost all external evidence is with other models and other harnesses. Only the points tagged [code] were measured with this pack.
- Items tagged [abstract] did not have their full text read.
- A proposal in this document is not a tested result. The CHANGELOG says what is implemented.
