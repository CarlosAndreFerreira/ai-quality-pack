#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Carlos André Ferreira. Part of the AI Quality Pack (https://github.com/CarlosAndreFerreira/ai-quality-pack), MIT License: keep this notice in copies.
"""Cross-platform plugin hook dispatcher for Claude Code.

Usage: aqp_hook.py start|format|guard|stop
Yields silently if the project's `.claude/settings.json` already configures the hook.
The `guard` hook stays silent outside projects with `.agent-memory/`, or when `"guard": false` in config.json.
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

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = {
    "start": ("skills/long-horizon/scripts/memory.py", ["start"]),
    "format": ("templates/.claude/hooks/format_on_edit.py", []),
    "guard": ("templates/.claude/hooks/guard_pack_files.py", []),
    "stop": ("templates/.claude/hooks/gate_on_stop.py", []),
}


def project_has_hook(project: Path, script_name: str) -> bool:
    settings_path = project / ".claude" / "settings.json"
    if not settings_path.is_file():
        return False
    text = settings_path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
    except Exception:
        return script_name in text
    if not isinstance(data, dict):
        return False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for item in entry.get("hooks") or []:
                if isinstance(item, dict) and script_name in str(item.get("command") or ""):
                    return True
    return False


def guard_enabled(project: Path) -> bool:
    if not (project / ".agent-memory").is_dir():
        return False
    cfg_path = project / ".agent-memory" / "config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and cfg.get("guard") is False:
                return False
        except Exception:
            pass
    return True


def resolve_project(raw_stdin: bytes) -> Path:
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("AGENT_PROJECT_DIR")
    if env_dir and Path(env_dir).is_dir():
        return Path(env_dir)
    try:
        data = json.loads(raw_stdin.decode("utf-8", errors="replace"))
        cwd: Optional[str] = data.get("cwd") if isinstance(data, dict) else None
        if isinstance(cwd, str) and cwd and Path(cwd).is_dir():
            return Path(cwd)
    except Exception:
        pass
    return Path(".")


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    if event not in SCRIPTS:
        sys.stderr.write(f"aqp-hook: unknown hook '{event}' (use start, format, guard or stop)\n")
        return 1

    rel_script, extra_args = SCRIPTS[event]
    script_path = PLUGIN_ROOT / rel_script
    raw_stdin = b""
    try:
        if not sys.stdin.isatty():
            raw_stdin = sys.stdin.buffer.read()
    except Exception:
        raw_stdin = b""

    project = resolve_project(raw_stdin)
    if project_has_hook(project, script_path.name):
        return 0
    if event == "guard" and not guard_enabled(project):
        return 0

    env = dict(os.environ)
    env["AGENT_MEMORY_SCRIPT"] = str(PLUGIN_ROOT / "skills" / "long-horizon" / "scripts" / "memory.py")
    r = subprocess.run([sys.executable, str(script_path)] + extra_args, input=raw_stdin, env=env)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
