#!/usr/bin/env python3
"""Claude Code PostToolUse hook: format the edited file with the project's formatter, if installed.

Never blocks the agent: always exits 0. Stdlib only, cross-platform.
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
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=60).returncode in (0, 1)
    except Exception:
        return False


def ruff(path: str) -> None:
    # Prefer the project's pinned ruff without syncing the environment on every edit
    # (`uv run` would otherwise create .venv / rewrite uv.lock); fall back to ruff on PATH.
    if shutil.which("uv") and run(["uv", "run", "--no-sync", "--quiet", "ruff", "format", path]):
        run(["uv", "run", "--no-sync", "--quiet", "ruff", "check", "--fix", "--quiet", path])
    elif shutil.which("ruff"):
        run(["ruff", "format", path])
        run(["ruff", "check", "--fix", "--quiet", path])


def main():
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project and Path(project).is_dir():
        os.chdir(project)
    try:
        path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
    except Exception:
        return
    if not path or not Path(path).is_file():
        return
    ext = Path(path).suffix.lower()
    if ext in (".py", ".pyi"):
        ruff(path)
    elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".css", ".md"):
        if Path("node_modules/.bin/prettier").exists() or Path("node_modules/.bin/prettier.cmd").exists():
            run(["npx", "--no-install", "prettier", "--write", "--log-level", "warn", path])
    elif ext == ".go" and shutil.which("gofmt"):
        run(["gofmt", "-w", path])
    elif ext == ".rs" and shutil.which("rustfmt"):
        run(["rustfmt", path])


if __name__ == "__main__":
    main()
    sys.exit(0)
