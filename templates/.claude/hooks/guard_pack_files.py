#!/usr/bin/env python3
"""Claude Code PreToolUse hook (opt-in): the agent may not change the files that check its work.

Protected: `.claude/`, `.agents/`, `.codex/`, `.opencode/`, `.github/workflows/`, `.github/CODEOWNERS`, `.agent-memory/gate.json` and
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
import subprocess
from pathlib import Path

PROTECTED = (".claude/", ".agents/", ".codex/", ".opencode/", ".github/workflows/", ".github/CODEOWNERS",
             ".agent-memory/gate.json", ".agent-memory/config.json")
NAMES = re.compile(r"(\.claude/|\.agents/|\.codex/|\.opencode/|\.github/workflows/|\.github/CODEOWNERS|\.agent-memory/(gate|config)\.json)")
# tools that change nothing: no check (OpenCode sends each tool call to the guard)
READ_ONLY = {"read", "grep", "glob", "list", "ls", "notebookread", "webfetch", "websearch", "skill", "task", "subagent",
             "agent", "todowrite", "todoread", "update_plan", "lsp", "question"}
# the files of a patch (Codex `apply_patch`, OpenCode `patch`)
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$", re.M)
WRITES = re.compile(
    r"(^|\s)(rm|mv|cp|chmod|chown|truncate|dd|ln|tee|install|touch|mkdir|rmdir)\s"
    r"|\bsed\s+(-[A-Za-z]*i|--in-place)"
    r"|\bgit\s+(checkout|restore|apply|rm|mv|stash|reset|clean)\b"
    r"|\b(python[0-9.]*|node|perl|ruby|bash|sh)\s+-[ce]\b")
# where a redirection writes: `> file`, `>> file`, `2> file`. `2>&1` and `>&2` join two streams and write no file.
REDIRECT = re.compile(r"(?<![0-9&])[0-9]?>>?\s*[\"']?([^\s\"'&|;<>]+)")
MESSAGE = ("Blocked: {what} is one of the files that check the agent's work (gate, hooks, skills, CI). "
           "Do not change it. If the task needs this change, stop and tell the user: a person makes it.\n")


def project_root(data: dict) -> str:
    """The project folder. Claude Code gives CLAUDE_PROJECT_DIR. Other agents (Codex, OpenCode) give the session
    folder in `cwd`: the project is that folder, or the git top level above it, where the pack's files are."""
    for name in ("CLAUDE_PROJECT_DIR", "AGENT_PROJECT_DIR"):
        if os.environ.get(name) and Path(os.environ[name]).is_dir():
            return os.environ[name]
    cwd = str(data.get("cwd") or "") or os.getcwd()
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except Exception:
        top = ""
    for folder in (cwd, top):
        if folder and (Path(folder, ".agent-memory").is_dir() or Path(folder, ".agents").is_dir()):
            return folder
    return top or cwd


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
    tool, args = str(data.get("tool_name") or "").lower(), data.get("tool_input") or {}
    if tool in READ_ONLY or not isinstance(args, dict):
        return 0
    project = Path(project_root(data))
    # The names differ between agents: Claude Code has Edit/Write (`file_path`) and Bash (`command`), OpenCode has
    # edit/write (`filePath`) and a shell tool, Codex sends a patch in `command`. So the check reads the arguments.
    patch = next((args[k] for k in ("command", "patchText", "patch", "input")
                  if isinstance(args.get(k), str) and PATCH_FILE.search(args[k])), "")
    paths = [args[k] for k in ("file_path", "filePath", "notebook_path", "path") if isinstance(args.get(k), str)]
    paths += [a or b for a, b in PATCH_FILE.findall(patch)]
    for path in paths:
        if protected(path, project):
            sys.stderr.write(MESSAGE.format(what=path))
            return 2
    command = args.get("command")
    if isinstance(command, list):
        command = " ".join(str(c) for c in command)
    if isinstance(command, str) and not patch:
        command = command.replace("\\", "/")
        for part in re.split(r"&&|\|\||;|\n|(?<![>&])\|(?!\|)", command):
            if not NAMES.search(part):
                continue
            # A part that names a protected path is blocked when it has a write command, or sends output into such a
            # path. Running a pack script, with `2>&1` or with output to another file, is normal work.
            to_protected = any(NAMES.search(m.group(1)) for m in REDIRECT.finditer(part))
            if WRITES.search(part) or to_protected:
                sys.stderr.write(MESSAGE.format(what="`" + part.strip()[:120] + "`"))
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
