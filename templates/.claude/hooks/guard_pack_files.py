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

import difflib
import fnmatch
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional, Set, Tuple

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
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|specs?)/|(^|/)test_[^/]+\.py$|_test\.(py|go|rs)$"
                          r"|\.(test|spec)\.[cm]?[jt]sx?$|(^|/)[^/]+Tests?\.(java|kt|cs)$")
SKIP_RE = re.compile(r"@(pytest\.mark\.(skip|skipif|xfail)|unittest\.(skip|skipIf|skipUnless|expectedFailure)|Disabled|Ignore)\b"
                     r"|\bpytest\.skip\(|\b(it|test|describe)\.(skip|todo)\(|\bx(it|describe)\(|\bt\.Skip(f|Now)?\(|#\[ignore\]")
TEST_FILE_NAME_RE = re.compile(r"(^|/)test_[^/]+\.py$|_test\.(py|go|rs)$|\.(test|spec)\.[cm]?[jt]sx?$|(^|/)[^/]+Tests?\.(java|kt|cs)$")
TRUNCATE_REDIRECT = re.compile(r"(?<![0-9&>])[0-9]?>\|?(?!>)\s*([\"']?[^\s\"'&|;<>]+)")
APPEND_REDIRECT = re.compile(r"(?<![0-9&])[0-9]?>>\s*([\"']?[^\s\"'&|;<>]+)")
INLINE_EVAL = re.compile(r"^(python[0-9.]*|node|perl|ruby|bash|sh|zsh|fish)$")
DISABLED_SUFFIXES = (".bak", ".disabled", ".orig", ".tmp", ".txt", ".md", ".off")
TEST_MESSAGE = ("Blocked: {what} removes or turns off an existing test.\n"
                "Keep existing tests active and passing; add new tests if needed, "
                "or stop and ask a person if this test must be removed or skipped.\n")


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


def guard_tests_mode(project: Path) -> str:
    try:
        cfg = json.loads((project / ".agent-memory" / "config.json").read_text(encoding="utf-8"))
    except Exception:
        return "no-delete"
    if not isinstance(cfg, dict):
        return "no-delete"
    mode = str(cfg.get("guard_tests") or "no-delete").lower()
    return mode if mode in ("no-delete", "append-only", "off") else "no-delete"


def load_tracked_tests(project: Path) -> Tuple[bool, Set[str]]:
    try:
        chk = subprocess.run(["git", "-C", str(project), "rev-parse", "--is-inside-work-tree"],
                             capture_output=True, text=True, timeout=10)
        if chk.returncode != 0:
            return False, set()
    except Exception:
        return False, set()
    tracked: Set[str] = set()
    for cmd in (["ls-files"], ["ls-tree", "-r", "--name-only", "HEAD"]):
        try:
            r = subprocess.run(["git", "-C", str(project)] + cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    p = line.strip()
                    if p and TEST_PATH_RE.search(p):
                        tracked.add(p)
        except Exception:
            pass
    return True, tracked


def _rel_from(raw: str, base_dir: Path, project: Path) -> str:
    raw = raw.strip().strip("\"'").replace("\\", "/")
    if not raw:
        return ""
    abs_proj = os.path.abspath(str(project))
    cand = raw if os.path.isabs(raw) else os.path.join(str(base_dir), raw)
    try:
        rel = Path(os.path.abspath(cand)).relative_to(Path(abs_proj)).as_posix()
        return "." if rel == "." else rel
    except ValueError:
        return ""


def resolve_tracked_test(raw: str, base_dir: Path, project: Path, in_git: bool, tracked: Set[str]) -> str:
    for b in (base_dir, project) if base_dir != project and not os.path.isabs(raw) else (base_dir,):
        rel = _rel_from(raw, b, project)
        if rel and rel != ".":
            if rel in tracked:
                return rel
            if not in_git and (project / rel).is_file() and TEST_PATH_RE.search(rel):
                return rel
    return ""


def _read_current_test(project: Path, rel: str) -> str:
    p = project / rel
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    try:
        r = subprocess.run(["git", "-C", str(project), "show", f"HEAD:./{rel}"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _drops_existing_lines(old_text: str, new_text: str) -> bool:
    for line in difflib.ndiff(old_text.splitlines(), new_text.splitlines()):
        if line.startswith("- ") and line[2:].strip():
            return True
    return False


def _has_new_skip(old_text: str, new_text: str) -> bool:
    return len(SKIP_RE.findall(new_text)) > len(SKIP_RE.findall(old_text))


def _valid_test_dest(src_rel: str, dest_raw: str, base_dir: Path, project: Path, tracked: Set[str]) -> bool:
    dest_rel = _rel_from(dest_raw, base_dir, project)
    if not dest_rel or dest_rel == ".":
        return False
    if (base_dir / dest_raw).is_dir() or dest_raw.rstrip().endswith("/"):
        dest_rel = f"{dest_rel.rstrip('/')}/{Path(src_rel).name}"
    if dest_rel in tracked and dest_rel != src_rel:
        return False
    if dest_rel.lower().endswith(DISABLED_SUFFIXES) or not TEST_PATH_RE.search(dest_rel):
        return False
    if TEST_FILE_NAME_RE.search(src_rel) and not TEST_FILE_NAME_RE.search(dest_rel):
        return False
    return True


def check_file_tool_tests(tool: str, args: dict, cwd: Path, project: Path, in_git: bool, tracked: Set[str], mode: str) -> str:
    raw = next((args[k] for k in ("file_path", "filePath", "notebook_path", "path") if isinstance(args.get(k), str)), "")
    if not raw:
        return ""
    rel = resolve_tracked_test(raw, cwd, project, in_git, tracked)
    if not rel:
        return ""
    edits = args.get("edits")
    if isinstance(edits, list):
        for item in edits:
            if not isinstance(item, dict):
                continue
            old_s = next((item[k] for k in ("old_string", "oldString", "oldText") if isinstance(item.get(k), str)), "")
            new_s = next((item[k] for k in ("new_string", "newString", "newText") if isinstance(item.get(k), str)), "")
            if _has_new_skip(old_s, new_s) or (mode == "append-only" and _drops_existing_lines(old_s, new_s)):
                return rel
        return ""
    old_s = next((args[k] for k in ("old_string", "oldString", "oldText") if isinstance(args.get(k), str)), None)
    new_s = next((args[k] for k in ("new_string", "newString", "newText") if isinstance(args.get(k), str)), None)
    if old_s is not None and new_s is not None:
        if _has_new_skip(old_s, new_s) or (mode == "append-only" and _drops_existing_lines(old_s, new_s)):
            return rel
        return ""
    content = args.get("content") if isinstance(args.get("content"), str) else args.get("new_source")
    if isinstance(content, str):
        cur = _read_current_test(project, rel)
        if not content.strip() and cur.strip():
            return rel
        if _has_new_skip(cur, content) or (mode == "append-only" and _drops_existing_lines(cur, content)):
            return rel
    return ""


def check_patch_tests(patch: str, cwd: Path, project: Path, in_git: bool, tracked: Set[str], mode: str) -> str:
    if PATCH_FILE.search(patch):
        cur_rel, plus_skips, minus_skips = "", 0, 0
        for line in patch.splitlines():
            m_hdr = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$", line)
            if m_hdr:
                if cur_rel and plus_skips > minus_skips:
                    return cur_rel
                action, raw_path = m_hdr.group(1), m_hdr.group(2)
                rel = resolve_tracked_test(raw_path, cwd, project, in_git, tracked)
                if action == "Delete" and rel:
                    return rel
                cur_rel, plus_skips, minus_skips = rel, 0, 0
                continue
            m_move = re.match(r"^\*\*\* Move to: (.+?)\s*$", line)
            if m_move:
                if cur_rel and not _valid_test_dest(cur_rel, m_move.group(1), cwd, project, tracked):
                    return f"{cur_rel} -> {m_move.group(1).strip()}"
                continue
            if not cur_rel:
                continue
            if line.startswith("+") and not line.startswith("+++ "):
                plus_skips += len(SKIP_RE.findall(line[1:]))
            elif line.startswith("-") and not line.startswith("--- "):
                minus_skips += len(SKIP_RE.findall(line[1:]))
                if mode == "append-only" and line[1:].strip():
                    return cur_rel
        if cur_rel and plus_skips > minus_skips:
            return cur_rel
        return ""
    # Unified diff fallback (--- a/... +++ b/...)
    old_raw, cur_rel, plus_skips, minus_skips, in_hunk = "", "", 0, 0, False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            if cur_rel and plus_skips > minus_skips:
                return cur_rel
            old_raw, cur_rel, plus_skips, minus_skips, in_hunk = "", "", 0, 0, False
            continue
        if line.startswith("--- "):
            if cur_rel and plus_skips > minus_skips:
                return cur_rel
            old_raw = line[4:].strip()
            if old_raw.startswith("a/"):
                old_raw = old_raw[2:]
            cur_rel = "" if old_raw == "/dev/null" else resolve_tracked_test(old_raw, cwd, project, in_git, tracked)
            plus_skips, minus_skips, in_hunk = 0, 0, False
            continue
        if line.startswith("+++ "):
            new_raw = line[4:].strip()
            if new_raw.startswith("b/"):
                new_raw = new_raw[2:]
            if cur_rel:
                if new_raw == "/dev/null" or not _valid_test_dest(cur_rel, new_raw, cwd, project, tracked):
                    return cur_rel
            elif new_raw != "/dev/null":
                cur_rel = resolve_tracked_test(new_raw, cwd, project, in_git, tracked)
            in_hunk = False
            continue
        if line.startswith("@@ "):
            in_hunk = True
            continue
        if not in_hunk or not cur_rel:
            continue
        if line.startswith("+"):
            plus_skips += len(SKIP_RE.findall(line[1:]))
        elif line.startswith("-"):
            minus_skips += len(SKIP_RE.findall(line[1:]))
            if mode == "append-only" and line[1:].strip():
                return cur_rel
    if cur_rel and plus_skips > minus_skips:
        return cur_rel
    return ""


def _split_shell_commands(cmd: str) -> List[str]:
    """Split a shell command on unquoted &&, ||, ;, newlines, and pipes."""
    parts: List[str] = []
    cur: List[str] = []
    quote = ""
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < n:
                cur.append(cmd[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            cur.append(ch)
            i += 1
        elif ch == "\\" and i + 1 < n:
            cur.append(ch)
            cur.append(cmd[i + 1])
            i += 2
        elif ch in (";", "\n"):
            parts.append("".join(cur))
            cur = []
            i += 1
        elif cmd.startswith("&&", i) or cmd.startswith("||", i):
            parts.append("".join(cur))
            cur = []
            i += 2
        elif ch == "|":
            if cur and cur[-1] == ">":
                cur.append(ch)
            else:
                parts.append("".join(cur))
                cur = []
            i += 1
        else:
            cur.append(ch)
            i += 1
    if cur:
        parts.append("".join(cur))
    return parts


def _split_shell_tokens(part: str) -> List[str]:
    cleaned = re.sub(r"(?<![0-9&])[0-9]?>>?\|?\s*[\"']?[^\s\"'&|;<>]+|(?<![0-9&])[0-9]?<&\d+|(?<![0-9&])[0-9]?>&\d+", " ", part)
    try:
        return shlex.split(cleaned)
    except ValueError:
        return cleaned.split()


def _arg_hits_tracked_test(arg: str, sim_cwd: Path, project: Path, in_git: bool, tracked: Set[str], include_dirs: bool = False) -> bool:
    if resolve_tracked_test(arg, sim_cwd, project, in_git, tracked):
        return True
    rel = _rel_from(arg, sim_cwd, project)
    if rel and any(ch in arg for ch in "*?["):
        if any(fnmatch.fnmatchcase(t, rel) for t in tracked):
            return True
    if include_dirs and rel:
        if rel == ".":
            return bool(tracked)
        prefix = rel.rstrip("/") + "/"
        if any(t.startswith(prefix) for t in tracked):
            return True
    return False


def _move_violates(args_tok: List[str], sim_cwd: Path, project: Path, in_git: bool, tracked: Set[str]) -> bool:
    paths: List[str] = []
    dest_dir: Optional[str] = None
    i = 0
    while i < len(args_tok):
        tok = args_tok[i]
        if tok == "--":
            paths.extend(args_tok[i + 1:])
            break
        if tok in ("-t", "--target-directory") and i + 1 < len(args_tok):
            dest_dir = args_tok[i + 1]
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        paths.append(tok)
        i += 1
    if dest_dir is not None:
        sources, dest = paths, dest_dir
    elif len(paths) >= 2:
        sources, dest = paths[:-1], paths[-1]
    else:
        return False
    for src in sources:
        src_rel = resolve_tracked_test(src, sim_cwd, project, in_git, tracked)
        if src_rel:
            if not _valid_test_dest(src_rel, dest, sim_cwd, project, tracked):
                return True
        elif _arg_hits_tracked_test(src, sim_cwd, project, in_git, tracked, include_dirs=True):
            dest_rel = _rel_from(dest, sim_cwd, project)
            if not dest_rel or dest_rel.lower().endswith(DISABLED_SUFFIXES):
                return True
    return False


def _find_deletes_tracked(args_tok: List[str], sim_cwd: Path, project: Path, in_git: bool, tracked: Set[str]) -> bool:
    roots: List[str] = []
    for tok in args_tok:
        if tok.startswith(("-", "!", "(")):
            break
        roots.append(tok)
    if not roots:
        roots = ["."]
    deletes = "-delete" in args_tok
    for i, tok in enumerate(args_tok):
        if tok in ("-exec", "-execdir", "-ok", "-okdir") and i + 1 < len(args_tok):
            if Path(args_tok[i + 1]).name in ("rm", "unlink", "shred", "truncate", "rmdir"):
                deletes = True
                break
    if not deletes:
        return False
    name_globs: List[str] = []
    iname_globs: List[str] = []
    for i, tok in enumerate(args_tok):
        if tok == "-name" and i + 1 < len(args_tok):
            name_globs.append(args_tok[i + 1])
        elif tok == "-iname" and i + 1 < len(args_tok):
            iname_globs.append(args_tok[i + 1].lower())
    for root in roots:
        rel_root = _rel_from(root, sim_cwd, project)
        if not rel_root:
            continue
        if rel_root == ".":
            under = list(tracked)
        else:
            prefix = rel_root.rstrip("/") + "/"
            under = [t for t in tracked if t == rel_root or t.startswith(prefix)]
        if not under:
            continue
        if not name_globs and not iname_globs:
            return True
        for t in under:
            b = Path(t).name
            if any(fnmatch.fnmatchcase(b, g) for g in name_globs) or any(fnmatch.fnmatchcase(b.lower(), g) for g in iname_globs):
                return True
    return False


def _inline_names_tracked(part: str, sim_cwd: Path, project: Path, tracked: Set[str]) -> bool:
    for t in tracked:
        if t in part:
            return True
        try:
            rel_cwd = Path(os.path.abspath(str(project / t))).relative_to(Path(os.path.abspath(str(sim_cwd)))).as_posix()
            if rel_cwd in part:
                return True
        except ValueError:
            pass
    return False


def check_shell_tests(command: str, cwd: Path, project: Path, in_git: bool, tracked: Set[str], mode: str) -> str:
    cmd = command.replace("\\", "/")
    if not tracked:
        return ""
    sim_cwd = cwd
    has_append_to_tracked = False
    for raw_part in _split_shell_commands(cmd):
        part = raw_part.strip()
        if not part:
            continue
        for m in TRUNCATE_REDIRECT.finditer(part):
            if _arg_hits_tracked_test(m.group(1), sim_cwd, project, in_git, tracked):
                return part[:120]
        for m in APPEND_REDIRECT.finditer(part):
            if _arg_hits_tracked_test(m.group(1), sim_cwd, project, in_git, tracked):
                has_append_to_tracked = True
                if SKIP_RE.search(part):
                    return part[:120]
        toks = _split_shell_tokens(part)
        if not toks:
            continue
        while toks and toks[0].lstrip("(") in ("env", "command", "sudo") and len(toks) > 1:
            toks = toks[1:]
        exe = Path(toks[0].lstrip("(")).name
        args_tok = [toks[i].rstrip(")") if i == len(toks) - 1 and toks[i].endswith(")") and "(" not in toks[i] else toks[i]
                    for i in range(1, len(toks))]
        if exe == "cd":
            target = next((a for a in args_tok if a != "--"), "")
            if target:
                sim_cwd = Path(os.path.abspath(os.path.join(str(sim_cwd), target)))
            continue
        if INLINE_EVAL.match(exe) and any(a.startswith("-") and ("c" in a or "e" in a) for a in args_tok):
            if _inline_names_tracked(part, sim_cwd, project, tracked):
                return part[:120]
            continue
        if exe in ("rm", "unlink", "shred", "truncate", "rmdir"):
            recursive = exe == "rm" and any(a.startswith("-") and any(ch in a for ch in "rRd") for a in args_tok)
            if any(_arg_hits_tracked_test(a, sim_cwd, project, in_git, tracked, include_dirs=(recursive or exe == "rmdir"))
                   for a in args_tok if not a.startswith("-")):
                return part[:120]
        elif exe == "dd":
            for a in args_tok:
                if a.startswith("of=") and _arg_hits_tracked_test(a[3:], sim_cwd, project, in_git, tracked):
                    return part[:120]
        elif exe == "mv":
            if _move_violates(args_tok, sim_cwd, project, in_git, tracked):
                return part[:120]
        elif exe == "cp":
            pos = [a for a in args_tok if not a.startswith("-")]
            if len(pos) >= 2 and _arg_hits_tracked_test(pos[-1], sim_cwd, project, in_git, tracked):
                if pos[0] == "/dev/null" or mode == "append-only":
                    return part[:120]
        elif exe == "find":
            if _find_deletes_tracked(args_tok, sim_cwd, project, in_git, tracked):
                return part[:120]
        elif exe == "git" and args_tok:
            sub = args_tok[0]
            sub_args = args_tok[1:]
            if sub == "rm":
                if any(_arg_hits_tracked_test(a, sim_cwd, project, in_git, tracked, include_dirs=True)
                       for a in sub_args if not a.startswith("-")):
                    return part[:120]
            elif sub == "mv":
                if _move_violates(sub_args, sim_cwd, project, in_git, tracked):
                    return part[:120]
        elif mode == "append-only":
            if exe == "sed" and any(a.startswith("-i") or a == "--in-place" or a.startswith("--in-place=") for a in args_tok):
                if any(_arg_hits_tracked_test(a, sim_cwd, project, in_git, tracked) for a in args_tok if not a.startswith("-")):
                    return part[:120]
            elif exe in ("perl", "ruby") and any(a.startswith("-") and "i" in a for a in args_tok):
                if any(_arg_hits_tracked_test(a, sim_cwd, project, in_git, tracked) for a in args_tok if not a.startswith("-")):
                    return part[:120]
            elif exe == "tee" and not any(a in ("-a", "--append") for a in args_tok):
                if any(_arg_hits_tracked_test(a, sim_cwd, project, in_git, tracked) for a in args_tok if not a.startswith("-")):
                    return part[:120]
    if has_append_to_tracked and SKIP_RE.search(cmd):
        return cmd.strip()[:120]
    return ""


def _extract_patch(tool: str, args: dict) -> str:
    for k in ("command", "patchText", "patch", "input"):
        v = args.get(k)
        if isinstance(v, str) and PATCH_FILE.search(v):
            return v
    if tool in ("apply_patch", "patch"):
        for k in ("command", "patchText", "patch", "input"):
            v = args.get(k)
            if isinstance(v, str):
                return v
    for k in ("patchText", "patch"):
        v = args.get(k)
        if isinstance(v, str) and ("--- " in v and "+++ " in v):
            return v
    return ""


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
    cwd = Path(str(data.get("cwd") or "") or str(project))
    # The names differ between agents: Claude Code has Edit/Write (`file_path`) and Bash (`command`), OpenCode has
    # edit/write (`filePath`) and a shell tool, Codex sends a patch in `command`. So the check reads the arguments.
    patch = _extract_patch(tool, args)
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
        norm_cmd = command.replace("\\", "/")
        for part in _split_shell_commands(norm_cmd):
            if not NAMES.search(part):
                continue
            # A part that names a protected path is blocked when it has a write command, or sends output into such a
            # path. Running a pack script, with `2>&1` or with output to another file, is normal work.
            to_protected = any(NAMES.search(m.group(1)) for m in REDIRECT.finditer(part))
            if WRITES.search(part) or to_protected:
                sys.stderr.write(MESSAGE.format(what="`" + part.strip()[:120] + "`"))
                return 2
    mode = guard_tests_mode(project)
    if mode != "off":
        in_git, tracked = load_tracked_tests(project)
        bad = ""
        if patch:
            bad = check_patch_tests(patch, cwd, project, in_git, tracked, mode)
        elif not isinstance(command, str):
            bad = check_file_tool_tests(tool, args, cwd, project, in_git, tracked, mode)
        elif isinstance(command, str):
            bad = check_shell_tests(command, cwd, project, in_git, tracked, mode)
        if bad:
            sys.stderr.write(TEST_MESSAGE.format(what="`" + bad + "`" if bad else "this command"))
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
