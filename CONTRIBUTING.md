# Contributing

Thank you for your interest. Bug reports, results from your own use, suggestions and pull requests are all welcome.

This pack is a research preview. Its central claim is that it reduces false "done" on hard issues, and that claim is **not measured yet** ([docs/RESULTS.md](docs/RESULTS.md)). Some of the most useful contributions are not code.

## Ways to help

| Contribution | Where |
|---|---|
| A bug in the pack | Open an issue. Give the command, the output, your OS and your Python version |
| A use on a real project | Open an issue with what the pack found, what it missed, and what got in the way. Each real use so far found defects that the tests did not find |
| A measurement | Open an issue or a pull request with the protocol, the raw numbers and the limits. Negative results are welcome too |
| A suggestion or a question | Open an issue (or a discussion, if enabled) before a large pull request |
| An adapter for another agent | See "Adapters for other agents" below |
| A security problem | **Do not open a public issue.** See [SECURITY.md](SECURITY.md) |

## Before you open a pull request

1. For a change of more than a few lines, open an issue first. Say what problem it solves and how you will check it.
2. Keep one purpose for each pull request. A fix with an unrelated cleanup is hard to review.
3. Fork the repository, make a branch, and run the checks below.

### Checks

The scripts use the Python standard library only (Python 3.9 or newer). There is nothing to install.

```bash
python -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
python skills/skill-evolve/scripts/validate_skills.py skills --strict
python skills/ste-writing/scripts/ste_lint.py README.md --lang en --threshold 60
```

If you have Claude Code, also run `claude plugin validate . --strict`.

All four commands must pass. Say in the pull request which OS and Python version you used. CI runs Linux, macOS and Windows with Python 3.9 and 3.13.

## Rules for changes

These rules keep the pack honest. A pull request that breaks one will be asked to change.

- **No new dependency.** The scripts run with the Python standard library, so that anyone can read what runs in their repository. CI copies `memory.py` from the base branch as one file: do not split it into modules, and do not import a local module from it.
- **A bug fix comes with a test that fails without the fix.** A new behaviour comes with a test of that behaviour.
- **No claim without data.** Do not change a number or a conclusion in [docs/RESULTS.md](docs/RESULTS.md), the README or the CHANGELOG without the measurement behind it: protocol, raw results and limits. "Not measured" is a correct statement; a claim that sounds measured and is not is a defect.
- **Do not weaken a check.** A change that makes the gate, the guard, the verdict or the secret scan accept more needs its reason in the pull request, and a test for the case that it still refuses.
- **Keep functions small.** A test limits the complexity of the functions of `memory.py`. If your change hits the limit, split the function; do not raise the limit.
- **Write simple English** in the README, the skills and the docs: short sentences, one instruction for each sentence, active voice. The linter in the checks enforces part of this.
- **Add a line to the `Unreleased` part of [CHANGELOG.md](CHANGELOG.md)**, and say what is not measured or not tested.
- **Security-relevant files.** A change to the guard, the hook scripts, the CI templates or the skills is read with extra care: skills and hooks are instructions and code that run in the repositories of other people.

## Adapters for other agents

The pack has adapters for Claude Code, Codex and OpenCode 2. The Codex adapter has not run with a real Codex yet, and a report from a real run is welcome.

A new adapter must:

1. call the same scripts as the other adapters (`memory.py start`, the formatter, the guard, the Stop gate), and not copy their logic;
2. add the configuration folder of that agent to the protected paths of `templates/.claude/hooks/guard_pack_files.py` in the same pull request. Otherwise the agent can change its own gate;
3. say in the README what was run with a real version of the agent, and what was not.

## Reviews and decisions

The maintainer reviews pull requests when time permits. A pull request can be closed when it does not fit the scope of the pack: a quality layer with deterministic checks and published measurements, not a new agent runtime. That is not a judgement of the work.

## License

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE) of this repository.
