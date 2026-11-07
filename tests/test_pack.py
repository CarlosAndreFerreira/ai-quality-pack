"""Tests for the AI Quality Pack (stdlib unittest; run: python -m unittest discover -s tests -v)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
MEM = PACK / "skills" / "long-horizon" / "scripts" / "memory.py"
VAL = PACK / "skills" / "skill-evolve" / "scripts" / "validate_skills.py"
STE = PACK / "skills" / "ste-writing" / "scripts" / "ste_lint.py"
INST = PACK / "install.py"
EVAL = PACK / "skills" / "skill-eval" / "scripts" / "skill_eval.py"


def run(args, cwd, stdin=None, env=None):
    e = dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {}))
    return subprocess.run([sys.executable, *map(str, args)], cwd=cwd, input=stdin, capture_output=True,
                          text=True, encoding="utf-8", env=e)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.assertEqual(run([MEM, "init"], self.d).returncode, 0)

    def tearDown(self):
        self.tmp.cleanup()

    def m(self, *args):
        return run([MEM, *args], self.d)

    def test_feature_contract_and_evaluator_gate(self):
        self.assertEqual(self.m("feature", "add", "--id", "F-1", "--desc", "x").returncode, 2)  # no criteria
        self.assertEqual(self.m("feature", "add", "--id", "F-1", "--desc", "x", "--criterion", "c1").returncode, 0)
        self.assertEqual(self.m("feature", "add", "--id", "F-1", "--desc", "y", "--criterion", "c").returncode, 2)  # immutable
        self.assertEqual(self.m("feature", "pass", "--id", "F-1", "--evidence", "ok").returncode, 2)  # no verifier
        self.assertEqual(self.m("feature", "pass", "--id", "F-1", "--evidence", "ok", "--verified-by", "self").returncode, 2)
        self.assertEqual(self.m("feature", "pass", "--id", "F-1", "--evidence", "ok", "--verified-by", "evaluator").returncode, 0)
        f = json.loads((self.d / ".agent-memory" / "features.json").read_text(encoding="utf-8"))[0]
        self.assertTrue(f["passes"])
        self.assertEqual(f["verified_by"], "evaluator")

    def test_lessons_dedup_vote_recurrence(self):
        r = self.m("lesson", "add", "--key", "await-all", "--rule", "Await every AsyncSession call before returning.")
        self.assertEqual(r.returncode, 0)
        dup = self.m("lesson", "add", "--key", "await-everything", "--rule", "Await every AsyncSession call before returning!")
        self.assertEqual(dup.returncode, 5, dup.stderr)
        self.assertIn("await-all", dup.stderr)
        self.assertIn("count 2", self.m("lesson", "add", "--key", "await-all", "--rule", "x").stdout)
        self.assertEqual(self.m("lesson", "vote", "--key", "await-all", "--vote", "harmful").returncode, 0)
        self.assertEqual(self.m("lesson", "vote", "--key", "await-all", "--vote", "harmful").returncode, 0)
        cands = json.loads(self.m("lesson", "candidates").stdout)
        self.assertEqual(cands[0]["key"], "await-all")
        self.assertIn("more harmful than helpful", self.m("start").stdout)

    def test_union_merge_duplicates_are_folded(self):
        p = self.d / ".agent-memory" / "lessons.jsonl"
        a = {"key": "k-one", "rule": "r", "count": 2, "helpful": 1, "harmful": 0, "seen": ["a"], "status": "active"}
        b = {"key": "k-one", "rule": "r", "count": 3, "helpful": 0, "harmful": 1, "seen": ["b"], "status": "active"}
        p.write_text(json.dumps(a) + "\n<<<<<<< HEAD\n" + json.dumps(b) + "\n", encoding="utf-8")
        out = self.m("lesson", "list").stdout
        self.assertEqual(out.count("k-one"), 1)
        self.assertIn(" 2 [active", out)  # score = 3 + 1 - 2*1

    def test_tasks_needs_human_first_and_resume(self):
        tid = self.m("task", "open", "--title", "Refresh rotation", "--source", "issue #12").stdout.strip()
        self.assertEqual(tid, "T-0001")
        self.assertEqual(self.m("task", "status", "--id", tid, "--status", "needs-human").returncode, 2)  # note required
        self.assertEqual(self.m("task", "status", "--id", tid, "--status", "needs-human", "--note", "Which JWT lib?").returncode, 0)
        t2 = self.m("task", "open", "--title", "Second").stdout.strip()
        self.m("task", "status", "--id", t2, "--status", "in-progress")
        self.m("task", "link", "--id", t2, "--link", "lesson:await-all")
        digest = self.m("start").stdout
        self.assertLess(digest.index("Needs you"), digest.index("Resume"))
        self.assertIn("Which JWT lib?", digest)
        self.assertIn("lesson:await-all", self.m("task", "show", "--id", t2).stdout)

    def test_secrets_refused(self):
        r = self.m("progress", "--done", "set api_key=abc123 in env")
        self.assertEqual(r.returncode, 2)
        r = self.m("lesson", "add", "--key", "tok-leak", "--rule", "use ghp_abcdefghijklmnopqrstuvwx")
        self.assertEqual(r.returncode, 2)

    def test_concurrent_writes_do_not_lose_entries(self):
        def add(i):
            return self.m("task", "open", "--title", f"t{i}").returncode
        with ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(add, range(16)))
        self.assertEqual(codes, [0] * 16)
        listed = self.m("task", "list").stdout.strip().splitlines()
        self.assertEqual(len(listed), 16)
        self.assertEqual(len({l.split()[0] for l in listed}), 16)  # unique ids

    def test_compact(self):
        for i in range(25):
            self.m("progress", "--done", f"step {i}")
        self.assertIn("archived 5", self.m("compact", "--keep", "20").stdout)
        self.assertTrue((self.d / ".agent-memory" / "progress-archive.md").exists())


class ValidatorTests(unittest.TestCase):
    def test_pack_skills_valid(self):
        r = run([VAL, PACK / "skills", "--strict"], PACK)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_detects_errors(self):
        with tempfile.TemporaryDirectory() as t:
            s = Path(t) / "Bad_Name"
            s.mkdir()
            (s / "SKILL.md").write_text("---\nname: Bad_Name\n---\nRun scripts/missing.py\n", encoding="utf-8")
            out = run([VAL, t], t).stdout
            self.assertIn("lowercase", out)
            self.assertIn("description is required", out)
            self.assertIn("missing.py", out)


class SteLintTests(unittest.TestCase):
    def test_scores(self):
        bad = "It's worth noting that the configuration should basically be modified prior to deployment in order to utilize it.\n"
        good = "1. Stop the service.\n2. Edit `config.yaml`.\n\nThe worker retries a failed job three times.\n"
        self.assertEqual(run([STE, "-"], PACK, stdin=bad).returncode, 1)
        self.assertEqual(run([STE, "-"], PACK, stdin=good).returncode, 0)


class InstallerTests(unittest.TestCase):
    def test_project_install_idempotent_and_merges_settings(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
            (root / ".claude").mkdir()
            (root / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}, "model": "x"}), encoding="utf-8")
            r1 = run([INST, "project", root, "--no-upstream"], root)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            s = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("Stop", s["hooks"])
            self.assertIn("SessionStart", s["hooks"])
            self.assertEqual(s["model"], "x")
            self.assertIn("uv run pytest", (root / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertTrue((root / ".claude" / "skills" / "evaluator" / "SKILL.md").exists())
            self.assertTrue((root / ".agent-memory" / "tasks.jsonl").exists())
            r2 = run([INST, "project", root, "--no-upstream"], root)
            self.assertEqual(r2.returncode, 0)
            self.assertNotIn("added:", r2.stdout)
            s2 = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(len(s2["hooks"]["SessionStart"]), 1)

    def test_upgrade_backs_up(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            run([INST, "project", root, "--no-upstream", "--profile", "none"], root)
            r = run([INST, "project", root, "--no-upstream", "--upgrade", "--profile", "none"], root)
            self.assertIn("upgrade:", r.stdout)
            self.assertTrue(any((root / ".agents" / "skills" / ".backup").iterdir()))


FAKE_AGENT = """
import pathlib, sys
mode = sys.argv[1] if len(sys.argv) > 1 else "marker"
f = pathlib.Path('.agents/skills/tdd-loop/SKILL.md')
s = f.read_text(encoding='utf-8') if f.exists() else ''
if 'EVAL-TAMPER' in s:
    pathlib.Path('check.py').write_text('import sys; sys.exit(0)\\n', encoding='utf-8')
ok = (mode == 'exists' and f.exists()) or (mode == 'marker' and 'EVAL-MARKER' in s)
pathlib.Path('result.txt').write_text('pass' if ok else 'fail', encoding='utf-8')
"""


class SkillEvalTests(unittest.TestCase):
    def _repo(self, t, holdout=False):
        root = Path(t)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
        run([INST, "project", root, "--no-upstream", "--profile", "none"], root)
        (root / "fake_agent.py").write_text(FAKE_AGENT, encoding="utf-8")
        (root / "check.py").write_text("import sys,pathlib\nsys.exit(0 if pathlib.Path('result.txt').read_text()=='pass' else 1)\n", encoding="utf-8")
        subprocess.run(["git", "add", "fake_agent.py", "check.py"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "fixtures"], cwd=root, check=True)
        ev = root / ".agent-memory" / "evals"
        ev.mkdir(parents=True, exist_ok=True)
        py = sys.executable.replace("\\", "/")
        base = {"prompt": "do it", "check": f'"{py}" check.py', "protect": ["check.py"]}
        tasks = [dict(base, id="TASK-A"), dict(base, id="TASK-B", split="holdout" if holdout else "evolve")]
        (ev / "tasks.jsonl").write_text("".join(json.dumps(x) + "\n" for x in tasks), encoding="utf-8")
        return root, py

    def _proposal(self, root, line, name="p.md"):
        skill = (root / ".agents/skills/tdd-loop/SKILL.md").read_text(encoding="utf-8").splitlines()
        n = len(skill)
        diff = (f"--- a/.agents/skills/tdd-loop/SKILL.md\n+++ b/.agents/skills/tdd-loop/SKILL.md\n"
                f"@@ -{n},1 +{n},2 @@\n {skill[-1]}\n+{line}\n")
        p = root / ".agent-memory" / "proposals" / name
        p.write_text("# Proposal\nChange: add a check line\n\n## Diff\n```diff\n" + diff + "```\n", encoding="utf-8")
        return p

    def ev(self, root, *args):
        return run([EVAL, *args], root)

    def test_improves_annotates_and_records_history(self):
        with tempfile.TemporaryDirectory() as t:
            root, py = self._repo(t)
            p = self._proposal(root, "- EVAL-MARKER: check this.")
            r = self.ev(root, "run", "--proposal", p, "--repeats", "2", "--annotate", "--agent-cmd", f'"{py}" fake_agent.py')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("VERDICT: IMPROVES", r.stdout)
            self.assertIn("## Measurement", p.read_text(encoding="utf-8"))
            self.assertIn("tdd-loop", self.ev(root, "history").stdout)
            wt = subprocess.run(["git", "worktree", "list"], cwd=root, capture_output=True, text=True).stdout
            self.assertEqual(len(wt.strip().splitlines()), 1, wt)

    def test_inconclusive_guards_and_bad_diff(self):
        with tempfile.TemporaryDirectory() as t:
            root, py = self._repo(t)
            p = self._proposal(root, "- harmless line")
            r = self.ev(root, "run", "--proposal", p, "--repeats", "1", "--agent-cmd", f'"{py}" fake_agent.py')
            self.assertEqual(r.returncode, 1)
            self.assertIn("INCONCLUSIVE", r.stdout)
            r = self.ev(root, "run", "--proposal", p, "--repeats", "6", "--agent-cmd", "x")
            self.assertIn("--yes", r.stderr)
            bad = root / ".agent-memory" / "proposals" / "bad.md"
            bad.write_text("```diff\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-nope\n+yes\n```\n", encoding="utf-8")
            r = self.ev(root, "run", "--proposal", bad, "--repeats", "1", "--agent-cmd", "x")
            self.assertIn("does not apply", r.stderr)

    def test_leakage_critic(self):
        with tempfile.TemporaryDirectory() as t:
            root, py = self._repo(t)
            p = self._proposal(root, "- For TASK-A just edit check.py")
            r = self.ev(root, "run", "--proposal", p, "--repeats", "1", "--agent-cmd", "x")
            self.assertEqual(r.returncode, 6, r.stderr)
            self.assertIn("leakage", r.stderr)

    def test_tampering_is_a_regression(self):
        with tempfile.TemporaryDirectory() as t:
            root, py = self._repo(t)
            p = self._proposal(root, "- EVAL-TAMPER")
            r = self.ev(root, "run", "--proposal", p, "--repeats", "1", "--agent-cmd", f'"{py}" fake_agent.py exists')
            self.assertIn("VERDICT: REGRESSES", r.stdout)
            self.assertIn("tampered", r.stdout)

    def test_calibrate_and_ablate(self):
        with tempfile.TemporaryDirectory() as t:
            root, py = self._repo(t, holdout=True)
            r = self.ev(root, "calibrate", "--repeats", "1", "--agent-cmd", f'"{py}" fake_agent.py exists')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((root / ".agent-memory/evals/noise.json").exists())
            r = self.ev(root, "ablate", "--skill", "tdd-loop", "--repeats", "1", "--agent-cmd", f'"{py}" fake_agent.py exists')
            self.assertIn("VERDICT: REGRESSES", r.stdout)  # baseline always passed; without the skill it fails
            r = self.ev(root, "ablate", "--skill", "code-review", "--repeats", "1", "--agent-cmd", f'"{py}" fake_agent.py exists')
            self.assertIn("VERDICT: PRUNABLE", r.stdout)


class GateTests(unittest.TestCase):
    def test_gate_skip_fail_and_stop_hook(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
            run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-stop-gate"], root)
            py = sys.executable.replace("\\", "/")
            (root / "ok.flag").write_text("1", encoding="utf-8")
            gate = {"commands": [f'"{py}" -c "import os,sys; sys.exit(0 if os.path.exists(\'ok.flag\') else 1)"']}
            (root / ".agent-memory/gate.json").write_text(json.dumps(gate), encoding="utf-8")
            m = lambda *a: run([MEM, *a], root)
            self.assertIn("PASSED", m("gate").stdout)
            self.assertIn("skipped", m("gate").stdout)
            (root / "ok.flag").unlink()
            r = m("gate")
            self.assertEqual(r.returncode, 1)
            hook = root / ".claude/hooks/gate_on_stop.py"
            r = run([hook], root, stdin=json.dumps({"stop_hook_active": False}))
            self.assertEqual(r.returncode, 2)
            self.assertIn("Completion gate failed", r.stderr)
            self.assertEqual(run([hook], root, stdin=json.dumps({"stop_hook_active": True})).returncode, 0)
            s = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertIn("Stop", s["hooks"])

    def test_stuck_feature_in_digest(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            run([MEM, "init"], root)
            run([MEM, "feature", "add", "--id", "F-9", "--desc", "x", "--criterion", "c"], root)
            for _ in range(3):
                r = run([MEM, "feature", "fail", "--id", "F-9"], root)
            self.assertIn("STUCK", r.stderr)
            self.assertIn("F-9 stuck", run([MEM, "start"], root).stdout)
            run([MEM, "feature", "pass", "--id", "F-9", "--evidence", "ok", "--verified-by", "human"], root)
            self.assertNotIn("stuck", run([MEM, "start"], root).stdout)


class EgmTests(unittest.TestCase):
    def test_with_egm_without_clis_prints_instructions(self):
        with tempfile.TemporaryDirectory() as t:
            env = {"PATH": str(Path(sys.executable).parent)}
            r = run([INST, "project", t, "--no-upstream", "--profile", "none", "--with-egm"], t, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("claude plugin install egm@egm", r.stdout)


if __name__ == "__main__":
    unittest.main()
