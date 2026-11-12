#!/usr/bin/env python3
"""Check the label of each calibration case with the hidden tests. No agent runs, no tokens.

  python evals/judge-cases/check_labels.py

A case is `correct` when the hidden tests pass on its repository with its patch, and `wrong` when they fail.
Exit 1 when a label does not match. Run it after a change of the case set.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main() -> int:
    bad = 0
    cases = [json.loads(l) for l in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for c in cases:
        with tempfile.TemporaryDirectory() as t:
            ws = Path(t) / "ws"
            shutil.copytree(HERE / c["repo"], ws)
            run(["git", "init", "-q"], ws)
            if run(["git", "apply", "--whitespace=nowarn", str(HERE / c["patch"])], ws).returncode != 0:
                print(f"{c['id']}: the patch does not apply")
                bad += 1
                continue
            shutil.copytree(HERE / "hidden" / Path(c["repo"]).name, ws, dirs_exist_ok=True)
            r = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_hidden*.py", "-q"], ws)
            actual = "correct" if r.returncode == 0 else "wrong"
            if actual != c["label"]:
                print(f"{c['id']}: label {c['label']}, hidden tests say {actual}")
                bad += 1
    wrong = sum(c["label"] == "wrong" for c in cases)
    print(f"{len(cases)} cases ({wrong} wrong, {len(cases) - wrong} correct): {bad} label(s) do not match the hidden tests")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
