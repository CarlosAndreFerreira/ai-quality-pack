#!/usr/bin/env python3
"""AI Quality Pack v3 installer — cross-platform (Linux, macOS, Windows), stdlib only, Python 3.9+.

  python3 install.py project [DIR] [--profile auto|python|typescript|go|rust|none]
  python3 install.py global
Options:
  --no-upstream        skip mattpocock/skills (grill-me & co.)
  --update-upstream    re-fetch upstream skills (only folders marked .upstream are replaced)
  --upstream-ref REF   upstream revision (default: a pinned, reviewed SHA)
  --upgrade            replace pack-owned skills and hook scripts with this version (old copies backed up)
  --link DIR           also expose skills to another agent folder (repeatable, e.g. .codex/skills)
  --with-egm           install Google's Elephant-Goldfish Model plugin via the agents' own plugin CLIs
  --with-stop-gate     Claude Code Stop hook: the completion gate must pass before the agent finishes
  --dry-run            print actions only
Never overwrites your files: templates are added only if absent; settings.json is merged.
"""
from __future__ import annotations

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
    add_if_absent(PACK / "templates" / ".claude" / "agents" / "evaluator.md", root / ".claude" / "agents" / "evaluator.md")
    for hook in ("format_on_edit.py", "gate_on_stop.py"):
        add_or_upgrade(PACK / "templates" / ".claude" / "hooks" / hook, root / ".claude" / "hooks" / hook, a.upgrade)
    merge_settings(root / ".claude" / "settings.json", a.with_stop_gate)
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
            gate.write_text(json.dumps({"commands": cmds, "max_output": 3000, "timeout": 900}, indent=2) + "\n", encoding="utf-8")
            log(f"added: {gate} (edit to match this repo)")
    else:
        log("memory: init .agent-memory/ (+ gate.json from profile)")


def main() -> None:
    global DRY
    ap = argparse.ArgumentParser(description="Install the AI Quality Pack (Antigravity + Claude Code + any Agent Skills client).")
    ap.add_argument("mode", choices=["project", "global"])
    ap.add_argument("dir", nargs="?", default=".")
    ap.add_argument("--profile", default="auto", choices=["auto", "python", "typescript", "go", "rust", "none"])
    ap.add_argument("--no-upstream", action="store_true")
    ap.add_argument("--update-upstream", action="store_true")
    ap.add_argument("--upstream-ref", default=UPSTREAM_REF, help="git ref of mattpocock/skills (default: pinned, reviewed SHA)")
    ap.add_argument("--upgrade", action="store_true")
    ap.add_argument("--link", action="append", default=[], help="extra agent skills dir to link, relative to DIR")
    ap.add_argument("--with-egm", action="store_true", help="install Google's Elephant-Goldfish Model plugin")
    ap.add_argument("--with-stop-gate", action="store_true", help="Claude Code Stop hook enforcing the completion gate")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    DRY = a.dry_run
    if sys.version_info < (3, 9):
        sys.exit("Python 3.9+ required")
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
