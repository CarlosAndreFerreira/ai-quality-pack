#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Carlos André Ferreira. Part of the AI Quality Pack (https://github.com/CarlosAndreFerreira/ai-quality-pack), MIT License: keep this notice in copies.
"""Antigravity native hook adapter for the AI Quality Pack.

Translates Antigravity camelCase lifecycle payloads (SessionStart, PreToolUse,
PostToolUse, Stop) into the pack's existing scripts without duplicating logic.
Silent outside projects with `.agent-memory/`. Never blocks on its own errors.
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
from typing import Any, Dict, List, Optional

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_REASONS = {
    "USER_CANCELED",
    "ERROR",
    "MAX_INVOCATIONS",
    "MAX_FORCED_INVOCATIONS",
    "MAX_TOKEN_BUDGET_EXCEEDED",
}


def emit(payload: Dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload) + "\n")
    return 0


def first_str(args: Dict[str, Any], keys: tuple) -> str:
    for k in keys:
        v = args.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def first_str_or_none(args: Dict[str, Any], keys: tuple) -> Optional[str]:
    for k in keys:
        v = args.get(k)
        if isinstance(v, str):
            return v
    return None


def candidate_dirs(data: Dict[str, Any]) -> List[str]:
    dirs: List[str] = []
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd and Path(cwd).is_dir():
        dirs.append(cwd)
    ws = data.get("workspacePaths")
    if isinstance(ws, list):
        for p in ws:
            if isinstance(p, str) and p and Path(p).is_dir() and p not in dirs:
                dirs.append(p)
    if not dirs:
        dirs.append(os.getcwd())
    return dirs


def project_root(data: Dict[str, Any]) -> str:
    base_dirs = candidate_dirs(data)
    candidates = list(base_dirs)
    for d in base_dirs:
        try:
            top = subprocess.run(
                ["git", "-C", d, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if top and Path(top).is_dir() and top not in candidates:
                candidates.append(top)
        except Exception:
            pass
    for d in candidates:
        if (Path(d) / ".agent-memory").is_dir():
            return d
    return candidates[0]


def resolve_scripts(project: Path) -> Dict[str, Path]:
    proj_mem = project / ".agents" / "skills" / "long-horizon" / "scripts" / "memory.py"
    plug_mem = PLUGIN_ROOT / "skills" / "long-horizon" / "scripts" / "memory.py"
    mem = proj_mem if proj_mem.is_file() else plug_mem

    scripts = {"memory": mem}
    for name in ("guard_pack_files.py", "format_on_edit.py", "gate_on_stop.py"):
        proj_hook = project / ".claude" / "hooks" / name
        plug_hook = PLUGIN_ROOT / "hooks" / name
        scripts[name] = proj_hook if proj_hook.is_file() else plug_hook
    return scripts


def run_script(script: Path, args: List[str], payload: Dict[str, Any], env: Dict[str, str],
               cwd: str, timeout: int) -> Optional[subprocess.CompletedProcess]:
    if not script.is_file():
        return None
    try:
        return subprocess.run(
            [sys.executable, str(script)] + args,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=timeout,
        )
    except Exception:
        return None


def guard_enabled(project: Path) -> bool:
    cfg_path = project / ".agent-memory" / "config.json"
    if not cfg_path.is_file():
        return True
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if isinstance(cfg, dict) and cfg.get("guard") is False:
            return False
    except Exception:
        pass
    return True


def map_tool_call(tool_call: Dict[str, Any]) -> tuple:
    raw_name = str(tool_call.get("name") or "")
    name = raw_name.lower()
    raw_args = tool_call.get("args")
    args: Dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}

    if name == "run_command":
        cmd = args.get("CommandLine") or args.get("command") or ""
        return "Bash", {"command": cmd}

    path = first_str(args, ("Path", "TargetFile", "AbsolutePath", "file_path", "filePath", "path"))
    if name in ("write_file", "write_to_file"):
        content = first_str_or_none(args, ("Content", "CodeContent", "content"))
        mapped: Dict[str, Any] = {"file_path": path}
        if content is not None:
            mapped["content"] = content
        return "Write", mapped

    if name in ("edit_file", "replace_file_content", "multi_replace_file_content"):
        mapped = {"file_path": path}
        chunks = args.get("ReplacementChunks")
        if isinstance(chunks, list):
            edits = []
            for item in chunks:
                if isinstance(item, dict):
                    edits.append({
                        "old_string": item.get("TargetContent", ""),
                        "new_string": item.get("ReplacementContent", ""),
                    })
            mapped["edits"] = edits
        else:
            old_s = first_str_or_none(args, ("Target", "TargetContent", "old_string"))
            new_s = first_str_or_none(args, ("Replacement", "ReplacementContent", "new_string"))
            if old_s is not None and new_s is not None:
                mapped["old_string"] = old_s
                mapped["new_string"] = new_s
        return "Edit", mapped

    return raw_name, args


def handle_start(data: Dict[str, Any], project: str, scripts: Dict[str, Path], env: Dict[str, str]) -> int:
    payload = {
        "session_id": data.get("conversationId") or "",
        "cwd": project,
        "source": "startup",
    }
    r = run_script(scripts["memory"], ["start"], payload, env, project, timeout=25)
    if r is not None and r.returncode == 0 and r.stdout.strip():
        return emit({"injectSteps": [{"systemMessage": {"systemMessage": r.stdout.strip()}}]})
    return emit({})


def handle_guard(data: Dict[str, Any], project: str, cwd: str, scripts: Dict[str, Path], env: Dict[str, str]) -> int:
    if not guard_enabled(Path(project)):
        return emit({"decision": "allow"})
    tool_call = data.get("toolCall")
    if not isinstance(tool_call, dict):
        return emit({"decision": "allow"})
    tool_name, tool_input = map_tool_call(tool_call)
    payload = {"tool_name": tool_name, "tool_input": tool_input, "cwd": cwd}
    r = run_script(scripts["guard_pack_files.py"], [], payload, env, project, timeout=15)
    if r is not None and r.returncode == 2:
        reason = (r.stderr or r.stdout).strip() or "Blocked by AI Quality Pack guard."
        return emit({"decision": "deny", "reason": reason})
    return emit({"decision": "allow"})


def handle_format(data: Dict[str, Any], project: str, cwd: str, scripts: Dict[str, Path], env: Dict[str, str]) -> int:
    if data.get("error"):
        return emit({})
    tool_call = data.get("toolCall")
    if not isinstance(tool_call, dict):
        return emit({})
    raw_args = tool_call.get("args")
    args: Dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
    path = first_str(args, ("Path", "TargetFile", "AbsolutePath", "file_path", "filePath", "path"))
    if not path:
        return emit({})
    payload = {"tool_name": "Edit", "tool_input": {"file_path": path}, "cwd": cwd}
    run_script(scripts["format_on_edit.py"], [], payload, env, project, timeout=55)
    return emit({})


def stop_budget(project: Path) -> int:
    try:
        cfg = json.loads((project / ".agent-memory" / "gate.json").read_text(encoding="utf-8"))
        return int(cfg.get("timeout", 900)) * max(1, len(cfg.get("commands", []))) + 60
    except Exception:
        return 1800


def handle_stop(data: Dict[str, Any], project: str, cwd: str, scripts: Dict[str, Path], env: Dict[str, str]) -> int:
    if str(data.get("terminationReason") or "") in TERMINAL_REASONS:
        return emit({})
    payload = {
        "session_id": data.get("conversationId") or "",
        "stop_hook_active": bool(data.get("continuationActive")),
        "cwd": cwd,
    }
    r = run_script(scripts["gate_on_stop.py"], [], payload, env, project, timeout=stop_budget(Path(project)))
    if r is not None and r.returncode == 2:
        reason = (r.stderr or r.stdout).strip()
        if reason:
            return emit({"decision": "continue", "reason": reason})
    return emit({})


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    if event not in ("start", "guard", "format", "stop"):
        sys.stderr.write("aqp_agy_hook.py: usage: aqp_agy_hook.py start|guard|format|stop\n")
        return 1
    try:
        raw = json.load(sys.stdin)
        data = raw if isinstance(raw, dict) else {}
    except Exception:
        return emit({"decision": "allow"} if event == "guard" else {})

    try:
        project = project_root(data)
        if not (Path(project) / ".agent-memory").is_dir():
            return emit({"decision": "allow"} if event == "guard" else {})
        cwd = first_str(data, ("cwd",)) or project
        scripts = resolve_scripts(Path(project))
        env = dict(os.environ)
        env["AGENT_PROJECT_DIR"] = project
        env["AGENT_MEMORY_SCRIPT"] = str(scripts["memory"])
        if event == "start":
            return handle_start(data, project, scripts, env)
        if event == "guard":
            return handle_guard(data, project, cwd, scripts, env)
        if event == "format":
            return handle_format(data, project, cwd, scripts, env)
        return handle_stop(data, project, cwd, scripts, env)
    except Exception:
        return emit({"decision": "allow"} if event == "guard" else {})


if __name__ == "__main__":
    sys.exit(main())
