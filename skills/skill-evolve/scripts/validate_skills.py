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
import os
import re
import sys
from pathlib import Path

FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.S)
PORTABLE = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# A skill is a set of instructions that an agent follows. These checks look at the skill as an attacker's way in.
# Characters that a person does not see in a review and that an agent reads.
HIDDEN_ERROR = {**{c: "bidirectional control character" for c in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A))},
                0x200B: "zero-width space", 0x2060: "word joiner", 0xFEFF: "byte order mark inside the text"}
HIDDEN_WARN = {0x200C: "zero-width non-joiner", 0x200D: "zero-width joiner", 0x00AD: "soft hyphen"}
# Text that tells an agent to act against the user. Heuristic: it finds the plain forms, and a person reads the hit.
SUSPECT = (
    ("tells the agent to drop its other instructions",
     re.compile(r"(?i)\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|other|system)\b[^.\n]{0,20}\b(instructions?|rules?|prompts?|messages?)")),
    ("tells the agent to hide an action from the user",
     re.compile(r"(?i)\b(do not|don't|never|without)\b[^.\n]{0,30}\b(tell|telling|mention|mentioning|inform|informing|reveal|revealing|notify|notifying)\b[^.\n]{0,30}\b(user|human|developer|maintainer)\b")),
    ("sends local data to a network address",
     re.compile(r"(?i)\b(curl|wget|ncat|nc|Invoke-WebRequest|iwr)\b[^\n]{0,120}(\.env\b|id_rsa|\.ssh/|\.aws/|credentials|secret|token|api[_-]?key)")),  # skill-scan: ok (the rule itself)
    ("runs code from the network",
     re.compile(r"(?i)\b(curl|wget|iwr)\b[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z|k)?sh\b|\biex\s*\(")),  # skill-scan: ok (the rule itself)
    ("reads credential files",
     re.compile(r"(?i)(~|\$HOME|/home/\w+|/root)/\.(ssh|aws|gnupg|netrc|docker/config|config/gh)\b")),  # skill-scan: ok (the rule itself)
    ("turns off a safety check",
     re.compile(r"(?i)--no-verify\b|--dangerously-skip-permissions|\bgit\s+push\s+(-f\b|--force\b(?!-with-lease))|chmod\s+(-R\s+)?777")),  # skill-scan: ok (the rule itself)
)
ALLOW = "skill-scan: ok"  # on the line, after a person read it (for example a rule that says "never do X")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".txt", ".json", ".yaml", ".yml", ".js", ".ts", ".toml", ""}
STOP = set("""the and for with that this from when before after into your you are not use used using any all each which what will must
should can may its their them then than also only more most have has had was were been being does done about over under other such
they there here where while without within between both either able make made need needs every very just like well""".split())


def skill_files(sk: Path):
    for p in sorted(sk.rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and p.name not in (".upstream", "LICENSE") \
                and "__pycache__" not in p.parts and p.stat().st_size < 1_000_000:
            yield p


def scan_file(sk: Path, path: Path) -> tuple:
    """(errors, warnings) for hidden characters and suspect instructions in one file of a skill."""
    errors, warnings = [], []
    rel = f"{sk.name}/{path.relative_to(sk).as_posix()}"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return [f"{rel}: not readable as UTF-8 text"], []
    for n, line in enumerate(text.splitlines(), 1):
        for col, ch in enumerate(line, 1):
            code = ord(ch)
            if code == 0xFEFF and n == 1 and col == 1:
                continue
            if code in HIDDEN_ERROR or 0xE0000 <= code <= 0xE007F:
                errors.append(f"{rel}:{n}: hidden {HIDDEN_ERROR.get(code, 'tag character')} U+{code:04X} (a reviewer does not see it; an agent reads it)")
                break
            if code in HIDDEN_WARN:
                warnings.append(f"{rel}:{n}: {HIDDEN_WARN[code]} U+{code:04X}")
                break
        if ALLOW in line:
            continue
        for what, rx in SUSPECT:
            if rx.search(line):
                warnings.append(f"{rel}:{n}: {what}: `{line.strip()[:90]}` (read it; if it is intended, put `{ALLOW}` on the line)")
    return errors, warnings


def words(text: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z0-9-]{3,}", text.lower()) if w not in STOP}


def overlaps(descriptions: dict, threshold: float) -> list:
    """Pairs of skills whose descriptions share most of their words: the agent chooses a skill from its description."""
    out, names = [], sorted(descriptions)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            wa, wb = words(descriptions[a]), words(descriptions[b])
            if len(wa) >= 5 and len(wb) >= 5:
                score = len(wa & wb) / len(wa | wb)
                if score >= threshold:
                    out.append((round(score, 2), a, b, sorted(wa & wb)[:8]))
    return sorted(out, reverse=True)


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
    ap.add_argument("--overlap", type=float, default=0.5, help="warn when two descriptions share this share of their words (default 0.5; 0 = off)")
    ap.add_argument("--scanner", action="append", default=[], metavar="CMD",
                    help="an external scanner to run on the skills directory, for example \"gitleaks detect --no-git --source {dir}\" (repeatable)")
    ap.add_argument("--allow-missing-scanner", action="store_true", help="a scanner that is not installed is a warning, not an incomplete check")
    a = ap.parse_args()
    root = Path(a.dir)
    if not root.is_dir():
        print(f"error: {root} is not a directory")
        return 1
    errors, warnings, names, descriptions, incomplete = [], [], {}, {}, []
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
        if desc:
            descriptions[sk.name] = desc
        for path in skill_files(sk):
            e, w = scan_file(sk, path)
            errors += e
            warnings += w
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
    if a.overlap:
        for score, x, y, shared in overlaps(descriptions, a.overlap):
            warnings.append(f"{x} and {y}: the descriptions share {score:.0%} of their words ({', '.join(shared)}): "
                            "the agent may choose the wrong one. Say in each description when to use it and when not")
    import shlex
    import shutil
    import subprocess
    for cmd in a.scanner:
        try:
            parts = shlex.split(cmd.replace("{dir}", str(root)), posix=os.name != "nt")
        except ValueError:
            parts = []
        exe = parts[0].strip('"') if parts else ""
        if not exe or not (shutil.which(exe) or Path(exe).exists()):
            # a check that did not run is not a check that passed
            (warnings if a.allow_missing_scanner else incomplete).append(f"scanner `{exe or cmd}` is not installed: this check did not run")
            continue
        try:
            r = subprocess.run([p.strip('"') for p in parts], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            if r.returncode != 0:
                errors.append(f"scanner `{exe}` reported a problem (exit {r.returncode}): {(r.stdout + r.stderr).strip()[-300:]}")
        except (OSError, subprocess.TimeoutExpired) as e:
            incomplete.append(f"scanner `{exe}` did not finish: {e}")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    for i in incomplete:
        print(f"INCOMPLETE {i}")
    print(f"{len(names)} skill(s) checked: {len(errors)} error(s), {len(warnings)} warning(s)"
          + (f", {len(incomplete)} check(s) did not run" if incomplete else ""))
    if errors or (a.strict and warnings):
        return 1
    return 3 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
