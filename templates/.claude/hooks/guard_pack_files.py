#!/usr/bin/env python3
"""Claude Code PreToolUse hook (opt-in): the agent may not change the files that check its work.

Protected: `.claude/`, `.agents/`, `.github/workflows/`, `.github/CODEOWNERS`, `.agent-memory/gate.json` and
`.agent-memory/config.json`. A file tool on one of these paths is blocked. A shell command is blocked when one of
its parts names a protected path and writes (redirection, rm, mv, cp, sed -i, tee, git checkout, an inline script).
Reading these files and running the pack's scripts is allowed.

This stops an agent that edits its own checks by habit or because text in a file told it to. It is not a security
boundary: a script that the agent writes elsewhere can still change these files. The checks that count run in CI,
with the copy of the default branch.

A person who must change these files starts the agent with AGENT_PACK_UNLOCK=1, or edits them by hand.
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
import re
from pathlib import Path

PROTECTED = (".claude/", ".agents/", ".github/workflows/", ".github/CODEOWNERS", ".agent-memory/gate.json", ".agent-memory/config.json")
NAMES = re.compile(r"(\.claude/|\.agents/|\.github/workflows/|\.github/CODEOWNERS|\.agent-memory/(gate|config)\.json)")
WRITES = re.compile(
    r"(^|\s)(rm|mv|cp|chmod|chown|truncate|dd|ln|tee|install|touch|mkdir|rmdir)\s"
    r"|\bsed\s+(-[A-Za-z]*i|--in-place)"
    r"|\bgit\s+(checkout|restore|apply|rm|mv|stash|reset|clean)\b"
    r"|\b(python[0-9.]*|node|perl|ruby|bash|sh)\s+-[ce]\b"
    r"|>>?")
MESSAGE = ("Blocked: {what} is one of the files that check the agent's work (gate, hooks, skills, CI). "
           "Do not change it. If the task needs this change, stop and tell the user: a person makes it.\n")


def protected(path: str, project: Path) -> bool:
    try:
        rel = Path(os.path.abspath(os.path.join(str(project), path))).relative_to(Path(os.path.abspath(str(project)))).as_posix()
    except ValueError:
        return False
    return any(rel == p.rstrip("/") or rel.startswith(p if p.endswith("/") else p + "/") or rel == p for p in PROTECTED)


def main() -> int:
    if os.environ.get("AGENT_PACK_UNLOCK") == "1":
        return 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    tool, args = str(data.get("tool_name") or ""), data.get("tool_input") or {}
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".")
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = str(args.get("file_path") or args.get("notebook_path") or "")
        if path and protected(path, project):
            sys.stderr.write(MESSAGE.format(what=path))
            return 2
    elif tool == "Bash":
        command = str(args.get("command") or "").replace("\\", "/")
        for part in re.split(r"&&|\|\||;|\n|(?<!>)\|(?!\|)", command):
            if NAMES.search(part) and WRITES.search(part):
                # running a pack script and sending its output to a file outside the protected paths is normal work
                target = re.search(r">>?\s*[\"']?([^\s\"'&|;]+)", part)
                only_redirect = target and not NAMES.search(target.group(1)) and not WRITES.search(part.replace(target.group(0), " "))
                if not only_redirect:
                    sys.stderr.write(MESSAGE.format(what="`" + part.strip()[:120] + "`"))
                    return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
