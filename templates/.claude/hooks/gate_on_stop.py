#!/usr/bin/env python3
"""Claude Code Stop hook (opt-in): the completion gate must pass before the agent may finish.

- Runs `memory.py gate` (commands from .agent-memory/gate.json).
- Skipped when the workspace is unchanged since the last pass (cheap for Q&A turns).
- On failure: exit 2 with bounded output on stderr, so the agent keeps working on it.
- Never loops: if this stop was already triggered by the hook (stop_hook_active), it lets the agent stop.
  That release is written to the run log (`released-red` unless the gate passed for exactly the code
  that the agent leaves), and the next
  session-start digest reports it.
- A gate that times out counts as failed (fail closed); the hook's own timeout is sized from gate.json.
Stdlib only; never blocks on its own errors.
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
import sys
from pathlib import Path

MEM = Path(".agents/skills/long-horizon/scripts/memory.py")
# a plugin install has no copy in the project: the script is in the plugin, three folders above this file
PLUGIN_MEM = Path(__file__).resolve().parents[3] / "skills" / "long-horizon" / "scripts" / "memory.py"


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


def record(outcome: str, env: dict) -> None:
    """One `stop` line in .agent-memory/events.jsonl. A failure here must not change the hook's result."""
    try:
        subprocess.run([sys.executable, str(MEM), "event", "--ev", "stop", "--field", f"outcome={outcome}"],
                       capture_output=True, timeout=20, env=env)
    except Exception:
        pass


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    project = project_root(data if isinstance(data, dict) else {})
    if project and Path(project).is_dir():
        os.chdir(project)  # hooks may start in a subfolder; the pack paths are relative to the project root
    global MEM
    if not MEM.exists() and PLUGIN_MEM.is_file():
        MEM = PLUGIN_MEM
    gate_file = Path(".agent-memory/gate.json")
    if not MEM.exists() or not gate_file.exists():
        return 0
    env = dict(os.environ)
    if data.get("session_id"):
        env["AGENT_SESSION_ID"] = str(data["session_id"])  # the gate and stop events carry the session id
    if data.get("stop_hook_active"):
        try:  # green only for a pass on exactly this code: a pass from before the last edit does not count
            green = subprocess.run([sys.executable, str(MEM), "gate", "--check"], capture_output=True,
                                   timeout=120, env=env).returncode == 0
        except Exception:
            green = False
        record("released-green" if green else "released-red", env)
        return 0
    try:
        cfg = json.loads(gate_file.read_text(encoding="utf-8"))
        budget = int(cfg.get("timeout", 900)) * max(1, len(cfg.get("commands", []))) + 60
    except Exception:
        budget = 1800
    try:
        r = subprocess.run([sys.executable, str(MEM), "gate"], capture_output=True, text=True, timeout=budget, env=env)
    except subprocess.TimeoutExpired:
        record("blocked-timeout", env)
        sys.stderr.write(f"Completion gate did not finish within {budget}s. Treat this as a failure: "
                         "fix the hanging command, or explain to the user why the gate cannot pass.\n")
        return 2
    except Exception:
        return 0
    if r.returncode == 1:
        record("blocked", env)
        sys.stderr.write("Completion gate failed. Fix this before finishing, or explain to the user why it cannot pass:\n"
                         + (r.stdout + r.stderr)[-3000:])
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
