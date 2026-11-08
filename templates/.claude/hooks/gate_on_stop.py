#!/usr/bin/env python3
"""Claude Code Stop hook (opt-in): the completion gate must pass before the agent may finish.

- Runs `memory.py gate` (commands from .agent-memory/gate.json).
- Skipped when the workspace is unchanged since the last pass (cheap for Q&A turns).
- On failure: exit 2 with bounded output on stderr, so the agent keeps working on it.
- Never loops: if this stop was already triggered by the hook (stop_hook_active), it lets the agent stop.
- A gate that times out counts as failed (fail closed); the hook's own timeout is sized from gate.json.
Stdlib only; never blocks on its own errors.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

MEM = Path(".agents/skills/long-horizon/scripts/memory.py")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    if data.get("stop_hook_active"):
        return 0
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project and Path(project).is_dir():
        os.chdir(project)  # hooks may start in a subfolder; the pack paths are relative to the project root
    gate_file = Path(".agent-memory/gate.json")
    if not MEM.exists() or not gate_file.exists():
        return 0
    try:
        cfg = json.loads(gate_file.read_text(encoding="utf-8"))
        budget = int(cfg.get("timeout", 900)) * max(1, len(cfg.get("commands", []))) + 60
    except Exception:
        budget = 1800
    try:
        r = subprocess.run([sys.executable, str(MEM), "gate"], capture_output=True, text=True, timeout=budget)
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"Completion gate did not finish within {budget}s. Treat this as a failure: "
                         "fix the hanging command, or explain to the user why the gate cannot pass.\n")
        return 2
    except Exception:
        return 0
    if r.returncode == 1:
        sys.stderr.write("Completion gate failed. Fix this before finishing, or explain to the user why it cannot pass:\n"
                         + (r.stdout + r.stderr)[-3000:])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
