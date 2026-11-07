#!/usr/bin/env python3
"""Claude Code PostToolUse hook: format the edited file with the project's formatter, if installed.

Never blocks the agent: always exits 0. Stdlib only, cross-platform.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd):
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception:
        pass


def main():
    try:
        path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
    except Exception:
        return
    if not path or not Path(path).is_file():
        return
    ext = Path(path).suffix.lower()
    if ext in (".py", ".pyi"):
        if shutil.which("uv"):
            run(["uv", "run", "--quiet", "ruff", "format", path])
            run(["uv", "run", "--quiet", "ruff", "check", "--fix", "--quiet", path])
        elif shutil.which("ruff"):
            run(["ruff", "format", path])
            run(["ruff", "check", "--fix", "--quiet", path])
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
