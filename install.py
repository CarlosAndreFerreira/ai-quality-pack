#!/usr/bin/env python3
"""AI Quality Pack v3 installer — cross-platform (Linux, macOS, Windows), stdlib only, Python 3.9+.

  python3 install.py project [DIR] [--profile auto|python|typescript|go|rust|none]
  python3 install.py global
Options:
  --no-upstream        skip mattpocock/skills (grill-me & co.)
  --update-upstream    re-fetch upstream skills (only folders marked .upstream are replaced)
  --upstream-ref REF   upstream revision (default: a pinned, reviewed SHA)
  --upgrade            replace pack-owned skills, hook scripts and subagents with this version (old copies backed up)
  --link DIR           also expose skills to another agent folder (repeatable, e.g. .codex/skills)
  --with-egm           install Google's Elephant-Goldfish Model plugin via the agents' own plugin CLIs
  --with-stop-gate     Claude Code Stop hook: the completion gate must pass before the agent finishes
  --with-codex         Codex hooks in .codex/hooks.json: digest and formatter; the Stop gate and the guard with their options
  --with-opencode      OpenCode 2 plugin and subagents in .opencode/: digest and formatter; the gate and the guard with their options
  --with-ci            GitHub Actions workflow: the gate runs on each pull request, with the base branch's gate.json
  --dry-run            print actions only
Never overwrites your files: templates are added only if absent; settings.json is merged.
"""
import sys

if sys.version_info < (3, 9):  # this block must parse and run on Python 3.6: rerun with a newer Python, or say why not
    import os
    import shutil
    import subprocess

    def _rerun_with_newer_python():
        if os.environ.get("AGENT_PACK_RERUN"):
            return
        names = [os.environ.get("AGENT_PACK_PYTHON")] + ["python3.%d" % n for n in range(15, 8, -1)] + ["python3", "python"]
        for name in names:
            exe = shutil.which(name) if name else None
            if not exe or os.path.realpath(exe) == os.path.realpath(sys.executable):
                continue
            try:
                newer = subprocess.call([exe, "-c", "import sys; sys.exit(sys.version_info < (3, 9))"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30) == 0
            except Exception:
                newer = False
            if newer:
                sys.exit(subprocess.call([exe] + sys.argv, env=dict(os.environ, AGENT_PACK_RERUN="1")))

    _rerun_with_newer_python()
    sys.exit("%s needs Python 3.9 or newer. This is Python %d.%d, and no newer Python is on PATH. "
             "Install one, or set AGENT_PACK_PYTHON to the path of one."
             % (os.path.basename(sys.argv[0]), sys.version_info[0], sys.version_info[1]))

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACK = Path(__file__).resolve().parent
UPSTREAM_REPO = "https://github.com/mattpocock/skills.git"
# Pinned for supply-chain safety: upstream skills are instructions your agent will follow, so a reviewed
# revision is installed by default. Use --upstream-ref main (or a newer SHA) after reviewing the changes.
UPSTREAM_REF = "4ae2317ddb22b046e26455e4f9c9b3aaaf62212d"
UPSTREAM_SKILLS = ["grill-me", "grill-with-docs", "handoff", "improve-codebase-architecture"]
GATES = {  # deterministic completion gate per profile (memory.py gate)
    "python": ["uv run ruff check .", "uv run pyright", "uv run pytest -q"],
    "typescript": ["npx eslint . --max-warnings=0", "npx tsc --noEmit", "npm test --silent"],
    "go": ["go vet ./...", "go test ./..."],
    "rust": ["cargo fmt --all -- --check", "cargo clippy --workspace --all-targets -- -D warnings", "cargo test --workspace"],
}
EGM_REPO = "google/elephant-goldfish-model"
EGM_CMDS = {
    "claude": [["claude", "plugin", "marketplace", "add", EGM_REPO], ["claude", "plugin", "install", "egm@egm"]],
    "agy": [["agy", "plugin", "install", f"https://github.com/{EGM_REPO}"]],
    "codex": [["codex", "plugin", "marketplace", "add", EGM_REPO]],
}
PY = "python" if os.name == "nt" else "python3"
DRY = False
# Claude Code runs a hook command in the agent's current directory, and that directory follows the agent's
# `cd`. A script path relative to the project root is then not found: the hook does not start, and for a
# Stop hook that is a non-blocking error, so the completion gate is skipped without a word.
# "$CLAUDE_PROJECT_DIR" is the project root, whatever the current directory is.
HOOK_SCRIPTS = {
    "SessionStart": (".agents/skills/long-horizon/scripts/memory.py", "start"),
    "PostToolUse": (".claude/hooks/format_on_edit.py",),
    "Stop": (".claude/hooks/gate_on_stop.py",),
    "PreToolUse": (".claude/hooks/guard_pack_files.py",),
}


def hook_command(event: str) -> str:
    script, *args = HOOK_SCRIPTS[event]
    return " ".join([PY, f'"$CLAUDE_PROJECT_DIR"/{script}', *args])


def legacy_hook_commands(event: str) -> list:
    """The relative-path commands that pack versions up to 0.4.2 wrote (with either interpreter name)."""
    return [" ".join([py, *HOOK_SCRIPTS[event]]) for py in ("python", "python3")]


def log(msg: str) -> None:
    print(("[dry-run] " if DRY else "") + msg)


def copytree(src: Path, dst: Path) -> None:
    if not DRY:
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


# ---------------------------------------------------------------- skills
def install_pack_skills(dest: Path, upgrade: bool) -> None:
    if not DRY:
        dest.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    for src in sorted((PACK / "skills").iterdir()):
        if not src.is_dir():
            continue
        target = dest / src.name
        if target.exists():
            if (target / ".upstream").exists():
                log(f"skip (upstream skill with same name): {target}")
                continue
            if not upgrade:
                log(f"skip (exists; use --upgrade): {target}")
                continue
            backup = dest / ".backup" / stamp / src.name
            log(f"upgrade: {target} (backup → {backup})")
            if not DRY:
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(backup))
        else:
            log(f"added: {target}")
        copytree(src, target)


def fetch_upstream(dest: Path, update: bool, ref: str = UPSTREAM_REF) -> None:
    if not shutil.which("git"):
        log("WARN: git not found; skipping upstream skills")
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "mp"
        r = subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", UPSTREAM_REPO, str(repo)], capture_output=True, text=True)
        if r.returncode == 0:
            r = subprocess.run(["git", "-C", str(repo), "checkout", "-q", ref], capture_output=True, text=True)
        if r.returncode != 0:
            log(f"WARN: could not fetch {UPSTREAM_REPO}@{ref}; skipping upstream skills")
            return
        if ref != UPSTREAM_REF:
            log(f"NOTE: upstream ref {ref} is not the pinned, reviewed revision; review the skills before use")
        rev = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        index = {p.name: p for p in (repo / "skills").glob("*/*") if (p / "SKILL.md").exists()}
        queue, done = list(UPSTREAM_SKILLS), set()
        while queue:
            name = queue.pop(0)
            if name in done:
                continue
            done.add(name)
            src = index.get(name)
            if not src:
                log(f"WARN: upstream skill '{name}' not found")
                continue
            for dep in re.findall(r'Skill tool with "([a-z0-9-]+)"', "".join(p.read_text(encoding="utf-8", errors="ignore") for p in src.rglob("*.md"))):
                queue.append(dep)
            target = dest / name
            if target.exists():
                if not (target / ".upstream").exists():
                    log(f"skip (local skill with same name): {target}")
                    continue
                if not update:
                    log(f"skip (exists; use --update-upstream): {target}")
                    continue
                if not DRY:
                    shutil.rmtree(target)
            log(f"upstream: {target} (@{rev})")
            copytree(src, target)
            if not DRY:
                shutil.copy2(repo / "LICENSE", target / "LICENSE")
                (target / ".upstream").write_text(f"source={UPSTREAM_REPO}\npath={src.relative_to(repo).as_posix()}\nrev={rev}\n", encoding="utf-8")


def link_dir(link: Path, target_rel: str, real: Path) -> None:
    """Symlink link -> target_rel; fall back to a copy where symlinks are unavailable (Windows w/o dev mode)."""
    if link.is_symlink() or link.exists():
        if link.is_symlink():
            log(f"ok (link exists): {link}")
        else:
            log(f"WARN: {link} exists and is not a link; syncing pack skills into it")
            install_pack_skills(link, upgrade=False)
        return
    if DRY:
        log(f"link: {link} -> {target_rel}")
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target_rel, link, target_is_directory=True)
        log(f"linked: {link} -> {target_rel}")
    except (OSError, NotImplementedError):
        shutil.copytree(real, link)
        log(f"copied (symlinks unavailable): {link} — re-run the installer after skill updates to resync")


def install_egm() -> None:
    """EGM needs its full plugin (skills read reviewer prompts elsewhere in the repo), so use each agent's plugin CLI."""
    succeeded = False
    for cli, cmds in EGM_CMDS.items():
        if not shutil.which(cli):
            continue
        cli_ok = True
        for cmd in cmds:
            log("egm: " + " ".join(cmd))
            if DRY:
                continue
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            except (OSError, subprocess.TimeoutExpired) as e:
                log(f"WARN: egm via {cli} failed: {e}")
                cli_ok = False
                break
            if r.returncode != 0:
                log(f"WARN: egm via {cli} failed: {(r.stderr or r.stdout).strip()[:300]}")
                cli_ok = False
                break
        if cli_ok:
            succeeded = True
            if cli == "codex":
                log("NOTE: finish in Codex with its plugin install command (see the EGM README).")
    if not succeeded:
        log("NOTE: no agent CLI found for EGM. Install it manually:")
        for cmds in EGM_CMDS.values():
            for cmd in cmds:
                log("    " + " ".join(cmd))
    log("NOTE: Antigravity App/IDE: run /plugin there and add " + f"https://github.com/{EGM_REPO}")


# ---------------------------------------------------------------- templates
def detect_profiles(root: Path) -> list:
    found = []
    if any((root / f).exists() for f in ("pyproject.toml", "requirements.txt", "setup.py", "uv.lock")):
        found.append("python")
    if (root / "package.json").exists() or (root / "tsconfig.json").exists():
        found.append("typescript")
    if (root / "go.mod").exists():
        found.append("go")
    if (root / "Cargo.toml").exists():
        found.append("rust")
    return found


def add_if_absent(src: Path, dst: Path, text: str = None) -> None:
    if dst.exists():
        log(f"skip (exists): {dst}")
        return
    log(f"added: {dst}")
    if DRY:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if text is None:
        shutil.copy2(src, dst)
    else:
        dst.write_text(text, encoding="utf-8")


def add_or_upgrade(src: Path, dst: Path, upgrade: bool) -> None:
    """A pack-owned script: added if absent; with --upgrade a different copy is replaced and backed up."""
    if not dst.exists() or not upgrade or dst.read_bytes() == src.read_bytes():
        add_if_absent(src, dst)
        return
    backup = dst.parent / ".backup" / dt.datetime.now().strftime("%Y%m%d-%H%M%S") / dst.name
    log(f"upgrade: {dst} (backup → {backup})")
    if not DRY:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(backup))
        shutil.copy2(src, dst)


# ---------------------------------------------------------------- other agents: Codex and OpenCode
# Codex has the hook events and the hook input of Claude Code, in `.codex/hooks.json`. It has no variable for the
# project folder: the command asks git. The scripts are the ones in `.claude/hooks/`.
CODEX_HOOKS = {
    "SessionStart": (None, ".agents/skills/long-horizon/scripts/memory.py", "start"),
    "PostToolUse": ("apply_patch|Edit|Write", ".claude/hooks/format_on_edit.py"),
    "Stop": (None, ".claude/hooks/gate_on_stop.py"),
    "PreToolUse": ("Bash|apply_patch|Edit|Write", ".claude/hooks/guard_pack_files.py"),
}


def codex_entry(event: str, py: str = PY) -> dict:
    matcher, script, *args = CODEX_HOOKS[event]
    hook = {"type": "command", "command": " ".join([py, f'"$(git rev-parse --show-toplevel)"/{script}', *args])}
    return {"matcher": matcher, "hooks": [hook]} if matcher else {"hooks": [hook]}


def read_json_object(path: Path):
    """The JSON object of `path`, {} if there is no file, None (with a warning) if the file is not usable."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        log(f"WARN: {path} is not valid JSON or has an unexpected shape; not modified")
        return None
    return data


def install_codex(root: Path, stop_gate: bool, guard: bool) -> None:
    path = root / ".codex" / "hooks.json"
    data = read_json_object(path)
    if data is None:
        return
    events = ["SessionStart", "PostToolUse"] + (["Stop"] if stop_gate else []) + (["PreToolUse"] if guard else [])
    hooks, changed = data.setdefault("hooks", {}), False
    for event in events:
        entry = codex_entry(event)
        existing = hooks.setdefault(event, [])
        if not isinstance(existing, list):
            log(f"WARN: {path} has an unexpected shape; not modified")
            return
        if not any(h.get("command") == entry["hooks"][0]["command"] for e in existing if isinstance(e, dict) for h in e.get("hooks", [])):
            existing.append(entry)
            changed = True
    if not changed:
        log(f"ok (hooks present): {path}")
        return
    log(f"{'merged' if path.exists() else 'added'}: {path} (Codex hooks: {', '.join(events)})")
    log("NOTE: Codex runs project hooks only after you trust them: start Codex in this repository and use /hooks. "
        "The hook commands need a POSIX shell; they were not run on Windows.")
    if not DRY:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def uninstall_codex(root: Path) -> None:
    path = root / ".codex" / "hooks.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hooks = data["hooks"]
        assert isinstance(hooks, dict)
    except Exception:
        log(f"kept (no pack hooks found, or not valid JSON): {path}")
        return
    changed = False
    for event in list(hooks):
        if event not in CODEX_HOOKS or not isinstance(hooks[event], list):
            continue
        ours = {codex_entry(event, py)["hooks"][0]["command"] for py in ("python", "python3")}
        for e in hooks[event]:
            if isinstance(e, dict) and isinstance(e.get("hooks"), list):
                kept = [h for h in e["hooks"] if not (isinstance(h, dict) and h.get("command") in ours)]
                changed = changed or len(kept) != len(e["hooks"])
                e["hooks"] = kept
        hooks[event] = [e for e in hooks[event] if not (isinstance(e, dict) and e.get("hooks") == [])]
        if not hooks[event]:
            del hooks[event]
    if not changed:
        return
    if not hooks:
        del data["hooks"]
    if not data:
        remove(path)
        remove_if_empty(root / ".codex")
        return
    log(f"removed the pack's hooks from: {path}")
    if not DRY:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


OPENCODE_AGENTS = ("evaluator", "criteria", "triage")


def opencode_agent_text(name: str) -> str:
    """The Claude Code subagent file as an OpenCode agent: the same instructions, the OpenCode header."""
    text = (PACK / "templates" / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
    head, _, body = text[4:].partition("\n---\n") if text.startswith("---\n") else ("", "", text)
    description = next((l[len("description:"):].strip() for l in head.splitlines() if l.startswith("description:")), name)
    return f"---\ndescription: {description}\nmode: subagent\n---\n{body}"


def install_opencode(root: Path, stop_gate: bool, guard: bool, upgrade: bool) -> None:
    add_or_upgrade(PACK / "templates" / "opencode" / "ai-quality-pack.js", root / ".opencode" / "plugins" / "ai-quality-pack.js", upgrade)
    for name in OPENCODE_AGENTS:
        add_if_absent(None, root / ".opencode" / "agents" / f"{name}.md", opencode_agent_text(name))
    path = root / ".opencode" / "ai-quality-pack.json"
    try:
        cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        assert isinstance(cfg, dict)
    except Exception:
        log(f"WARN: {path} is not valid JSON; not modified")
        return
    new = dict(cfg, stop_gate=bool(cfg.get("stop_gate") or stop_gate), guard=bool(cfg.get("guard") or guard))
    if new != cfg or not path.exists():
        log(f"{'updated' if path.exists() else 'added'}: {path} (stop gate: {'on' if new['stop_gate'] else 'off'}, guard: {'on' if new['guard'] else 'off'})")
        if not DRY:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    log("NOTE: the plugin is for OpenCode 2. OpenCode cannot stop the agent from finishing: on a red gate the plugin "
        "sends the gate output to the session one time. For unattended work use `memory.py gated-run`.")


def uninstall_opencode(root: Path, force: bool) -> None:
    base = root / ".opencode"
    if not base.is_dir():
        return
    remove_pack_file(PACK / "templates" / "opencode" / "ai-quality-pack.js", base / "plugins" / "ai-quality-pack.js", force)
    for name in OPENCODE_AGENTS:
        dst = base / "agents" / f"{name}.md"
        if dst.is_file() and (force or dst.read_text(encoding="utf-8") == opencode_agent_text(name)):
            remove(dst)
        elif dst.is_file():
            log(f"kept (you changed it; --force removes it): {dst}")
    if (base / "ai-quality-pack.json").is_file():
        remove(base / "ai-quality-pack.json")
    remove_if_empty(base / "plugins", base / "agents", base)


def merge_settings(path: Path, stop_gate: bool = False) -> None:
    ours = {
        "SessionStart": {"hooks": [{"type": "command", "command": hook_command("SessionStart")}]},
        "PostToolUse": {"matcher": "Edit|MultiEdit|Write", "hooks": [{"type": "command", "command": hook_command("PostToolUse")}]},
    }
    if stop_gate:
        ours["Stop"] = {"hooks": [{"type": "command", "command": hook_command("Stop")}]}
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log(f"WARN: {path} is not valid JSON; not modified")
            return
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        log(f"WARN: {path} has an unexpected shape; not modified")
        return
    hooks = data.setdefault("hooks", {})
    changed = False
    for event in HOOK_SCRIPTS:  # an older install: rewrite its relative-path commands in place, also for a
        # Stop gate that this run was not asked to add
        for e in hooks.get(event, []) if isinstance(hooks.get(event), list) else []:
            for h in e.get("hooks", []) if isinstance(e, dict) else []:
                if isinstance(h, dict) and h.get("command") in legacy_hook_commands(event):
                    h["command"] = hook_command(event)
                    changed = True
    for event, entry in ours.items():
        cmd = entry["hooks"][0]["command"]
        existing = hooks.setdefault(event, [])
        if not any(h.get("command") == cmd for e in existing for h in e.get("hooks", [])):
            existing.append(entry)
            changed = True
    if changed:
        log(f"{'merged' if path.exists() else 'added'}: {path} (SessionStart memory digest, PostToolUse formatter)")
        if not DRY:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    else:
        log(f"ok (hooks present): {path}")


def install_project(root: Path, a: argparse.Namespace) -> None:
    skills = root / ".agents" / "skills"
    install_pack_skills(skills, a.upgrade)
    if not a.no_upstream:
        fetch_upstream(skills, a.update_upstream, a.upstream_ref)
    link_dir(root / ".claude" / "skills", os.path.join("..", ".agents", "skills"), skills)
    for extra in a.link:
        lp = root / extra
        rel = os.path.relpath(skills, lp.parent)
        link_dir(lp, rel, skills)

    profiles = detect_profiles(root) if a.profile == "auto" else ([] if a.profile == "none" else [a.profile])
    log(f"profiles: {', '.join(profiles) or 'none detected (fill Commands in AGENTS.md by hand)'}")
    cmds = "\n".join(
        (f"<!-- {p} -->\n" if len(profiles) > 1 else "") + (PACK / "templates" / "profiles" / p / "commands.md").read_text(encoding="utf-8").strip()
        for p in profiles
    ) or "- Test: `<fill in>`\n- Lint: `<fill in>`\n- Typecheck: `<fill in>`"
    agents_md = (PACK / "templates" / "AGENTS.md").read_text(encoding="utf-8").replace("{{COMMANDS}}", cmds)
    add_if_absent(None, root / "AGENTS.md", agents_md)
    add_if_absent(PACK / "templates" / "CLAUDE.md", root / "CLAUDE.md")
    for agent in ("evaluator.md", "criteria.md", "triage.md"):
        add_or_upgrade(PACK / "templates" / ".claude" / "agents" / agent, root / ".claude" / "agents" / agent, a.upgrade)
    if a.with_ci:
        add_if_absent(PACK / "templates" / "ci" / "quality-gate.yml", root / ".github" / "workflows" / "quality-gate.yml")
        log("NOTE: the CI gate needs `.agent-memory/gate.json` committed, and your dependencies installed in the workflow. "
            "Protect it with CODEOWNERS: see the comments in .github/workflows/quality-gate.yml.")
    if a.with_issue_workflow:
        add_if_absent(PACK / "templates" / "ci" / "agent-issue.yml", root / ".github" / "workflows" / "agent-issue.yml")
        log("NOTE: the issue workflow needs the secret ANTHROPIC_API_KEY and a committed `.agent-memory/gate.json`. "
            "Read the comments at the top of .github/workflows/agent-issue.yml before the first use.")
    for hook in ("format_on_edit.py", "gate_on_stop.py"):
        add_or_upgrade(PACK / "templates" / ".claude" / "hooks" / hook, root / ".claude" / "hooks" / hook, a.upgrade)
    merge_settings(root / ".claude" / "settings.json", a.with_stop_gate)
    if a.with_guard:
        add_or_upgrade(PACK / "templates" / ".claude" / "hooks" / "guard_pack_files.py", root / ".claude" / "hooks" / "guard_pack_files.py", a.upgrade)
        add_guard(root / ".claude" / "settings.json")
    if a.with_sandbox:
        add_sandbox(root / ".claude" / "settings.json", a.force, a.sandbox_allow_domain)
    if a.with_codex:
        install_codex(root, a.with_stop_gate, a.with_guard)
    if a.with_opencode:
        install_opencode(root, a.with_stop_gate, a.with_guard, a.upgrade)
    if a.codeowners:
        add_codeowners(root, a.codeowners)
    for p in profiles:
        pdir = PACK / "templates" / "profiles" / p
        for f in pdir.iterdir():
            if f.name == "commands.md":
                continue
            if f.name.startswith("."):
                add_if_absent(f, root / f.name)
            else:
                log(f"NOTE: merge {f.relative_to(PACK)} into your config by hand")
    if a.with_egm:
        install_egm()
    if not DRY:
        subprocess.run([sys.executable, str(skills / "long-horizon" / "scripts" / "memory.py"), "init"], cwd=root, check=False)
        gate = root / ".agent-memory" / "gate.json"
        cmds = [c for p in profiles for c in GATES.get(p, [])]
        if cmds and not gate.exists():
            cfg = {"commands": cmds, "max_output": 3000, "timeout": 900, "max_changed_lines": 400}
            if "python" in profiles:
                cfg["max_complexity"] = 10  # same limit as the ruff C90 rule of the Python profile
            gate.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
            log(f"added: {gate} (edit to match this repo, then commit it)")
        elif not gate.exists():
            log(f"WARNING: no profile gave commands for the completion gate, so {gate} was not written. "
                "`memory.py gate` fails until you create it with {\"commands\": [...]} and commit it.")
    else:
        log("memory: init .agent-memory/ (+ gate.json from profile)")


# ---------------------------------------------------------------- CODEOWNERS and sandbox (opt-in)
OWNERS_BEGIN, OWNERS_END = "# >>> AI Quality Pack: review of the checks themselves", "# <<< AI Quality Pack"
OWNED_PATHS = ("/.agent-memory/gate.json", "/.agents/", "/.claude/", "/.github/", "/tests/")
SECRET_READ_DENY = ["Read(./.env)", "Read(./.env.*)", "Read(./secrets/**)"]


def add_codeowners(root: Path, owner: str) -> None:
    """A change of the gate, the hooks, CI or the tests then needs a review by `owner` (with branch protection)."""
    if not re.fullmatch(r"@[\w.-]+(/[\w.-]+)?|[\w.+-]+@[\w.-]+", owner):
        sys.exit(f"--codeowners needs a GitHub user or team (for example @your-org/your-team), not {owner!r}")
    path = root / ".github" / "CODEOWNERS"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    block = "\n".join([OWNERS_BEGIN] + [f"{p} {owner}" for p in OWNED_PATHS] + [OWNERS_END]) + "\n"
    if OWNERS_BEGIN in old:
        new = re.sub(re.escape(OWNERS_BEGIN) + r".*?" + re.escape(OWNERS_END) + r"\n?", block, old, flags=re.S)
    else:
        new = old + ("" if not old or old.endswith("\n") else "\n") + block
    log(f"{'updated' if path.exists() else 'added'}: {path} ({owner} reviews the gate, the hooks, CI and the tests)")
    log("NOTE: CODEOWNERS has an effect only with a branch protection rule that requires a review from code owners.")
    if not DRY:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")


def remove_codeowners(root: Path) -> None:
    path = root / ".github" / "CODEOWNERS"
    if not path.exists() or OWNERS_BEGIN not in path.read_text(encoding="utf-8"):
        return
    new = re.sub(re.escape(OWNERS_BEGIN) + r".*?" + re.escape(OWNERS_END) + r"\n?", "", path.read_text(encoding="utf-8"), flags=re.S)
    if new.strip():
        log(f"removed the pack's lines from: {path}")
        if not DRY:
            path.write_text(new, encoding="utf-8")
    else:
        remove(path)


GUARD_DENY = ["Edit(./.claude/**)", "Edit(./.agents/**)", "Edit(./.github/workflows/**)", "Edit(./.github/CODEOWNERS)",
              "Edit(./.agent-memory/gate.json)", "Edit(./.agent-memory/config.json)",
              "Edit(./.agent-memory/risk-waivers.jsonl)"]


def add_guard(path: Path) -> None:
    """Claude Code settings: the agent may not change the files that check its work (permission rules and a hook)."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log(f"WARN: {path} is not valid JSON; not modified")
            return
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        log(f"WARN: {path} has an unexpected shape; not modified")
        return
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    deny += [r for r in GUARD_DENY if r not in deny]
    cmd = hook_command("PreToolUse")
    existing = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if not any(h.get("command") == cmd for e in existing for h in e.get("hooks", [])):
        existing.append({"matcher": "Edit|MultiEdit|Write|NotebookEdit|Bash", "hooks": [{"type": "command", "command": cmd}]})
    log(f"{'merged' if path.exists() else 'added'}: {path} (the agent may not change .claude/, .agents/, CI workflows, CODEOWNERS and the gate file)")
    log("NOTE: this stops an agent that edits its checks by habit or because a file told it to. It is not a security "
        "boundary: the checks that count run in CI. A person who must change these files starts the agent with AGENT_PACK_UNLOCK=1.")
    if not DRY:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def add_sandbox(path: Path, force: bool, domains: list) -> None:
    """Claude Code settings: no read of secret files, and shell commands in the operating system sandbox."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log(f"WARN: {path} is not valid JSON; not modified")
            return
    if not isinstance(data, dict):
        log(f"WARN: {path} has an unexpected shape; not modified")
        return
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    deny += [r for r in SECRET_READ_DENY if r not in deny]
    if os.name == "nt" and not force:
        log("NOTE: the sandbox is not written on Windows: Claude Code has no sandbox on native Windows, and with "
            "`failIfUnavailable` it does not start there. The read rules for secret files are written. Use WSL2, or --force.")
    else:
        sandbox = data.setdefault("sandbox", {})
        sandbox.update(enabled=True, failIfUnavailable=True)
        if domains:  # shell commands reach these hosts only: a command cannot send data to another host
            allowed = sandbox.setdefault("network", {}).setdefault("allowedDomains", [])
            allowed += [d for d in domains if d not in allowed]
            log(f"NOTE: shell commands in the sandbox reach only: {', '.join(allowed)}")
        else:
            log("NOTE: no network list was given (--sandbox-allow-domain). Shell commands in the sandbox follow the "
                "default network rules of Claude Code.")
        log("NOTE: sandbox on, and Claude Code stops at startup where the sandbox cannot run (native Windows; Linux and "
            "WSL2 without `bubblewrap` and `socat`). The sandbox covers shell commands only: file tools, MCP servers and "
            "hooks follow the permission rules.")
    log(f"{'merged' if path.exists() else 'added'}: {path} (no read of .env and secrets/ files"
        + ("" if os.name == "nt" and not force else "; sandbox for shell commands") + ")")
    if not DRY:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- uninstall
def tree_files(d: Path) -> dict:
    return {p.relative_to(d).as_posix(): p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def same_tree(src: Path, dst: Path) -> bool:
    a, b = tree_files(src), tree_files(dst)
    return a.keys() == b.keys() and all(a[k].read_bytes() == b[k].read_bytes() for k in a)


def remove(path: Path) -> None:
    log(f"removed: {path}")
    if DRY:
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def remove_if_empty(*dirs: Path) -> None:
    for d in dirs:
        if d.is_dir() and not d.is_symlink() and not any(d.iterdir()):
            remove(d)


def remove_pack_file(src: Path, dst: Path, force: bool) -> None:
    """Removes a file that the pack wrote. A copy that differs from the pack's file is yours: it stays."""
    if not dst.is_file():
        return
    if force or dst.read_bytes() == src.read_bytes():
        remove(dst)
    else:
        log(f"kept (differs from the pack's copy; --force removes it): {dst}")


def remove_skills(dest: Path, force: bool) -> None:
    if not dest.is_dir() or dest.is_symlink():
        return
    for target in sorted(dest.iterdir()):
        if not target.is_dir():
            continue
        src = PACK / "skills" / target.name
        if (target / ".upstream").exists():
            remove(target)  # the marker says that the pack fetched it
        elif src.is_dir():
            if force or same_tree(src, target):
                remove(target)
            else:
                log(f"kept (differs from the pack's copy; --force removes it): {target}")
    remove_if_empty(dest)


def unmerge_settings(path: Path) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hooks = data["hooks"]
        assert isinstance(hooks, dict)
    except Exception:
        log(f"kept (no pack hooks found, or not valid JSON): {path}")
        return
    ours = {event: {" ".join([py, f'"$CLAUDE_PROJECT_DIR"/{HOOK_SCRIPTS[event][0]}', *HOOK_SCRIPTS[event][1:]])
                    for py in ("python", "python3")} | set(legacy_hook_commands(event)) for event in HOOK_SCRIPTS}
    changed = False
    for event in list(hooks):
        entries = hooks[event] if isinstance(hooks[event], list) else None
        if entries is None or event not in ours:
            continue
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("hooks"), list):
                kept = [h for h in e["hooks"] if not (isinstance(h, dict) and h.get("command") in ours[event])]
                changed = changed or len(kept) != len(e["hooks"])
                e["hooks"] = kept
        hooks[event] = [e for e in entries if not (isinstance(e, dict) and e.get("hooks") == [])]
        if not hooks[event]:
            del hooks[event]
    if not changed:
        log(f"ok (no pack hooks): {path}")
        return
    if not hooks:
        del data["hooks"]
    if not data:
        remove(path)
        return
    log(f"removed the pack's hooks from: {path}")
    if not DRY:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def uninstall_project(root: Path, a: argparse.Namespace) -> None:
    skills = root / ".agents" / "skills"
    for link in [root / ".claude" / "skills"] + [root / extra for extra in a.link]:
        if link.is_symlink():
            remove(link)
        else:
            remove_skills(link, a.force)  # a copy, where symbolic links were not available
    remove_skills(skills, a.force)
    remove_if_empty(root / ".agents")
    tpl = PACK / "templates"
    for rel in ("agents/evaluator.md", "agents/criteria.md", "agents/triage.md", "hooks/format_on_edit.py", "hooks/gate_on_stop.py",
                "hooks/guard_pack_files.py"):
        remove_pack_file(tpl / ".claude" / rel, root / ".claude" / rel, a.force)
    remove_pack_file(tpl / "ci" / "quality-gate.yml", root / ".github" / "workflows" / "quality-gate.yml", a.force)
    remove_pack_file(tpl / "ci" / "agent-issue.yml", root / ".github" / "workflows" / "agent-issue.yml", a.force)
    remove_pack_file(tpl / "CLAUDE.md", root / "CLAUDE.md", False)
    unmerge_settings(root / ".claude" / "settings.json")
    uninstall_codex(root)
    uninstall_opencode(root, a.force)
    remove_codeowners(root)
    for d in ("hooks", "agents"):
        pycache = root / ".claude" / d / "__pycache__"
        if pycache.is_dir() and not any(p for p in (root / ".claude" / d).iterdir() if p.name != "__pycache__"):
            remove(pycache)
        remove_if_empty(root / ".claude" / d)
    remove_if_empty(root / ".claude", root / ".github" / "workflows", root / ".github")
    memory = root / ".agent-memory"
    if memory.is_dir():
        if a.purge_memory:
            remove(memory)
        else:
            log(f"kept: {memory} (your project memory and gate; --purge-memory removes it)")
    if (root / "AGENTS.md").exists():
        log(f"kept: {root / 'AGENTS.md'} (it has your project's commands; edit or delete it by hand)")
    for backup in sorted(root.glob(".claude/**/.backup")) + sorted(root.glob(".agents/**/.backup")):
        log(f"kept: {backup} (backups from --upgrade)")
    log("NOTE: files from a language profile (for example .editorconfig) and the EGM plugin are not removed. "
        "Sandbox and permission settings from --with-sandbox and --with-guard stay in .claude/settings.json: remove them by hand.")


def uninstall_global(a: argparse.Namespace) -> None:
    home = Path.home()
    agy_plugin = home / ".gemini" / "config" / "plugins" / "ai-quality-pack"
    for d in (agy_plugin / "skills", home / ".gemini" / "antigravity-cli" / "skills", home / ".claude" / "skills"):
        remove_skills(d, a.force)
    for rel in ("plugin.json", "agents/evaluator.md", "rules/AGENTS.md", "assets/logo.svg"):
        remove_pack_file(PACK / "templates" / "antigravity" / rel, agy_plugin / rel, a.force)
    for doc in ("README.md", "LICENSE"):
        if (PACK / doc).exists():
            remove_pack_file(PACK / doc, agy_plugin / doc, a.force)
    remove_if_empty(agy_plugin / "agents", agy_plugin / "rules", agy_plugin / "assets", agy_plugin)


def main() -> None:
    global DRY
    ap = argparse.ArgumentParser(description="Install the AI Quality Pack (Antigravity + Claude Code + any Agent Skills client).")
    ap.add_argument("mode", choices=["project", "global", "uninstall"],
                    help="uninstall removes what the pack installed in DIR (with --global: in your home directory)")
    ap.add_argument("dir", nargs="?", default=".")
    ap.add_argument("--profile", default="auto", choices=["auto", "python", "typescript", "go", "rust", "none"])
    ap.add_argument("--no-upstream", action="store_true")
    ap.add_argument("--update-upstream", action="store_true")
    ap.add_argument("--upstream-ref", default=UPSTREAM_REF, help="git ref of mattpocock/skills (default: pinned, reviewed SHA)")
    ap.add_argument("--upgrade", action="store_true")
    ap.add_argument("--link", action="append", default=[], help="extra agent skills dir to link, relative to DIR")
    ap.add_argument("--with-egm", action="store_true", help="install Google's Elephant-Goldfish Model plugin")
    ap.add_argument("--with-stop-gate", action="store_true", help="Claude Code Stop hook enforcing the completion gate")
    ap.add_argument("--with-codex", action="store_true",
                    help="Codex hooks in .codex/hooks.json (digest, formatter; the Stop gate and the guard with their options)")
    ap.add_argument("--with-opencode", action="store_true",
                    help="OpenCode 2 plugin and subagents in .opencode/ (digest, formatter; the gate and the guard with their options)")
    ap.add_argument("--with-ci", action="store_true", help="GitHub Actions workflow that runs the gate on pull requests")
    ap.add_argument("--with-sandbox", action="store_true",
                    help="Claude Code settings: sandbox for shell commands (it must be available) and no read of .env and secrets/ files")
    ap.add_argument("--sandbox-allow-domain", action="append", default=[], metavar="HOST",
                    help="with --with-sandbox: a host that shell commands may reach (repeatable), for example pypi.org")
    ap.add_argument("--with-guard", action="store_true",
                    help="Claude Code settings: the agent may not change .claude/, .agents/, CI workflows and the gate file")
    ap.add_argument("--codeowners", metavar="OWNER",
                    help="add CODEOWNERS lines: OWNER (for example @your-org/your-team) reviews the gate, the hooks, CI and the tests")
    ap.add_argument("--with-issue-workflow", action="store_true",
                    help="GitHub Actions workflow: the label `agent` on an issue starts an agent run that ends in a draft pull request")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--global", dest="global_", action="store_true", help="uninstall: remove the global install")
    ap.add_argument("--force", action="store_true", help="uninstall: also remove pack files that you changed")
    ap.add_argument("--purge-memory", action="store_true", help="uninstall: also remove .agent-memory/")
    a = ap.parse_args()
    DRY = a.dry_run
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9+ required")
    if a.mode == "uninstall":
        if a.global_:
            uninstall_global(a)
        else:
            root = Path(a.dir).resolve()
            if not root.is_dir():
                sys.exit(f"{root} is not a directory")
            uninstall_project(root, a)
        log("Done. Use --dry-run to see the list without a change." if not DRY else "Done (nothing was changed).")
        return
    if a.mode == "project":
        root = Path(a.dir).resolve()
        if not root.is_dir():
            sys.exit(f"{root} is not a directory")
        install_project(root, a)
    else:
        home = Path.home()
        agy_plugin = home / ".gemini" / "config" / "plugins" / "ai-quality-pack"
        agy_skills = agy_plugin / "skills"
        install_pack_skills(agy_skills, a.upgrade)
        if not a.no_upstream:
            fetch_upstream(agy_skills, a.update_upstream, a.upstream_ref)
        agy_tpl = PACK / "templates" / "antigravity"
        for rel in ("plugin.json", "agents/evaluator.md", "rules/AGENTS.md", "assets/logo.svg"):
            src_f = agy_tpl / rel
            dst_f = agy_plugin / rel
            if src_f.exists():
                if a.upgrade and dst_f.exists() and not DRY:
                    shutil.copy2(src_f, dst_f)
                else:
                    add_if_absent(src_f, dst_f)
        for doc in ("README.md", "LICENSE"):
            if (PACK / doc).exists():
                add_if_absent(PACK / doc, agy_plugin / doc)
        for d in (home / ".gemini" / "antigravity-cli" / "skills", home / ".claude" / "skills"):
            install_pack_skills(d, a.upgrade)
            if not a.no_upstream:
                fetch_upstream(d, a.update_upstream, a.upstream_ref)
        if a.with_egm:
            install_egm()
        log("NOTE: memory is per project — run 'memory.py init' inside each repo (or install in project mode).")
    log("Done. Review AGENTS.md Commands for this repo.")


if __name__ == "__main__":
    main()
