#!/usr/bin/env python3
"""validate_skills.py — lint a skills directory against the Agent Skills open standard (stdlib only).

Errors (exit 1):
  - missing SKILL.md / malformed YAML frontmatter
  - name missing-slug rules: lowercase letters, digits, single hyphens, <= 64 chars, == folder name
  - description missing or > 1024 chars
  - duplicate names
  - referenced scripts/ references/ assets/ files that do not exist
Warnings:
  - frontmatter keys outside the portable set (agent-specific extensions; other agents ignore them)
  - body longer than --max-lines
  - nested reference chains (references deeper than one level)
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

import argparse
import re
import sys
from pathlib import Path

FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.S)
PORTABLE = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def parse_fm(block: str) -> dict:
    out: dict = {}
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)  # top-level keys only
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate SKILL.md files (Agent Skills open standard).")
    ap.add_argument("dir", nargs="?", default=".agents/skills")
    ap.add_argument("--max-lines", type=int, default=150)
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    a = ap.parse_args()
    root = Path(a.dir)
    if not root.is_dir():
        print(f"error: {root} is not a directory")
        return 1
    errors, warnings, names = [], [], {}
    for sk in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        f = sk / "SKILL.md"
        if not f.exists():
            errors.append(f"{sk.name}: missing SKILL.md")
            continue
        m = FM.match(f.read_text(encoding="utf-8"))
        if not m:
            errors.append(f"{sk.name}: missing or malformed YAML frontmatter")
            continue
        fm, body = parse_fm(m.group(1)), m.group(2)
        upstream = (sk / ".upstream").exists()
        name, desc = fm.get("name", ""), fm.get("description", "")
        if not name:
            errors.append(f"{sk.name}: name is required")
        elif not NAME_RE.fullmatch(name) or len(name) > 64:
            errors.append(f"{sk.name}: name '{name}' must be lowercase letters/digits/single hyphens, <= 64 chars")
        elif name != sk.name:
            errors.append(f"{sk.name}: name '{name}' does not match folder")
        if not desc:
            errors.append(f"{sk.name}: description is required")
        elif len(desc) > 1024:
            errors.append(f"{sk.name}: description is {len(desc)} chars (> 1024)")
        if name and name in names:
            errors.append(f"{sk.name}: duplicate name (also {names[name]})")
        names[name or sk.name] = sk.name
        extra = sorted(set(fm) - PORTABLE)
        if extra:
            warnings.append(f"{sk.name}: non-portable frontmatter {extra} (agent-specific; others ignore)" + (" [upstream]" if upstream else ""))
        n = body.count("\n")
        if n > a.max_lines:
            warnings.append(f"{sk.name}: body has {n} lines (> {a.max_lines}); move detail to references/")
        for ref in set(re.findall(r"(?<![\w/.-])((?:scripts|references|resources|examples|assets)/[\w./-]+\.\w+)", body)):
            target = sk / ref
            if not target.exists():
                errors.append(f"{sk.name}: referenced file '{ref}' not found")
            elif target.suffix == ".md" and re.search(r"\]\((?:\.\./)?(?:references|resources)/", target.read_text(encoding="utf-8")):
                warnings.append(f"{sk.name}: '{ref}' links to further references (keep one level deep)")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(names)} skill(s) checked: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors or (a.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
