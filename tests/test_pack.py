"""Tests for the AI Quality Pack (stdlib unittest; run: python -m unittest discover -s tests -v)."""
from __future__ import annotations

import json
import os
import re
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

    def test_gate_config_change_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
            py = sys.executable.replace("\\", "/")
            m = lambda *a: run([MEM, *a], root)
            m("init")
            gate = root / ".agent-memory/gate.json"
            gate.write_text(json.dumps({"commands": [f'"{py}" -c "pass"']}), encoding="utf-8")
            self.assertIn("PASSED", m("gate").stdout)
            gate.write_text(json.dumps({"commands": [f'"{py}" -c "import sys; sys.exit(1)"']}), encoding="utf-8")
            r = m("gate")
            self.assertNotIn("skipped", r.stdout)
            self.assertEqual(r.returncode, 1)

    def test_stop_hook_uses_project_dir_from_subfolder(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
            run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-stop-gate"], root)
            py = sys.executable.replace("\\", "/")
            (root / ".agent-memory/gate.json").write_text(
                json.dumps({"commands": [f'"{py}" -c "import sys; sys.exit(1)"']}), encoding="utf-8")
            sub = root / "src" / "pkg"
            sub.mkdir(parents=True)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
            r = run([root / ".claude/hooks/gate_on_stop.py"], sub, stdin=json.dumps({}), env=env)
            self.assertEqual(r.returncode, 2)  # without the fix the hook found no gate and let the agent stop

    def _project_with_failing_gate(self, root):
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
        r = run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-stop-gate"], root)
        self.assertEqual(r.returncode, 0, r.stderr)
        py = sys.executable.replace("\\", "/")
        (root / ".agent-memory/gate.json").write_text(
            json.dumps({"commands": [f'"{py}" -c "import sys; sys.exit(1)"']}), encoding="utf-8")
        sub = root / "src" / "pkg"
        sub.mkdir(parents=True)
        return sub, json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))

    def test_hook_commands_do_not_depend_on_the_current_directory(self):
        with tempfile.TemporaryDirectory() as t:
            _, s = self._project_with_failing_gate(Path(t))
            for event in ("SessionStart", "PostToolUse", "Stop"):
                for entry in s["hooks"][event]:
                    for hook in entry["hooks"]:
                        self.assertIn('"$CLAUDE_PROJECT_DIR"/', hook["command"], event)

    @unittest.skipIf(os.name == "nt", "needs a POSIX shell to expand $CLAUDE_PROJECT_DIR")
    def test_stop_hook_command_blocks_from_a_subfolder(self):
        """The command line of settings.json, run as Claude Code runs it after the agent did `cd src/pkg`."""
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            sub, s = self._project_with_failing_gate(root)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
            shell = lambda command: subprocess.run(command, shell=True, cwd=sub, input="{}", capture_output=True,
                                                   text=True, env=env)
            r = shell(s["hooks"]["Stop"][0]["hooks"][0]["command"])
            self.assertEqual(r.returncode, 2)
            self.assertIn("Completion gate failed", r.stderr)
            # the command that versions up to 0.4.2 wrote: the script is not found, so the gate never ran
            old = shell("python3 .claude/hooks/gate_on_stop.py")
            self.assertNotIn("Completion gate failed", old.stderr)
            self.assertIn("No such file", old.stderr)
            # the digest hook, from the same subfolder, still reads the project's memory
            r = shell(s["hooks"]["SessionStart"][0]["hooks"][0]["command"])
            self.assertIn("Session start digest", r.stdout)

    def test_installer_repairs_relative_hook_commands(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".claude").mkdir()
            old = {"hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "python3 .agents/skills/long-horizon/scripts/memory.py start"}]}],
                "Stop": [{"hooks": [{"type": "command", "command": "python .claude/hooks/gate_on_stop.py"}]},
                         {"hooks": [{"type": "command", "command": "echo mine"}]}]}}
            (root / ".claude/settings.json").write_text(json.dumps(old), encoding="utf-8")
            r = run([INST, "project", root, "--no-upstream", "--profile", "none"], root)  # no --with-stop-gate
            self.assertEqual(r.returncode, 0, r.stderr)
            s = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
            commands = {event: [h["command"] for e in entries for h in e["hooks"]] for event, entries in s["hooks"].items()}
            self.assertEqual(len(commands["SessionStart"]), 1)
            self.assertEqual(len(commands["Stop"]), 2)
            self.assertIn("echo mine", commands["Stop"])
            for event in ("SessionStart", "PostToolUse"):
                self.assertTrue(all("CLAUDE_PROJECT_DIR" in c for c in commands[event]), commands[event])
            self.assertTrue(any("CLAUDE_PROJECT_DIR" in c and "gate_on_stop.py" in c for c in commands["Stop"]))
            self.assertFalse(any(c.endswith(" .claude/hooks/gate_on_stop.py") for c in commands["Stop"]))

    def test_digest_reports_hooks_that_will_not_run(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            _, s = self._project_with_failing_gate(root)
            self.assertNotIn("hook:", run([MEM, "start"], root).stdout)
            s["hooks"]["Stop"][0]["hooks"][0]["command"] = "python3 .claude/hooks/gate_on_stop.py"
            (root / ".claude/settings.json").write_text(json.dumps(s), encoding="utf-8")
            out = run([MEM, "start"], root).stdout
            self.assertIn("Needs you", out)
            self.assertIn("Stop hook: `.claude/hooks/gate_on_stop.py` has a relative path", out)
            (root / ".claude/hooks/format_on_edit.py").unlink()
            out = run([MEM, "start"], root).stdout
            self.assertIn("PostToolUse hook: script `.claude/hooks/format_on_edit.py` is missing", out)

    def test_merge_settings_leaves_unexpected_shape_alone(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".claude").mkdir()
            (root / ".claude/settings.json").write_text("[]", encoding="utf-8")
            r = run([INST, "project", root, "--no-upstream", "--profile", "none"], root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((root / ".claude/settings.json").read_text(encoding="utf-8"), "[]")

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
            env = {"PATH": ""}
            r = run([INST, "project", t, "--no-upstream", "--profile", "none", "--with-egm"], t, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("claude plugin install egm@egm", r.stdout)

    def test_rust_profile_detection(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "Cargo.toml").write_text("[package]\nname = \"demo\"\nversion = \"0.1.0\"\n", encoding="utf-8")
            r = run([INST, "project", root, "--no-upstream"], root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("cargo clippy", (root / "AGENTS.md").read_text(encoding="utf-8"))
            gate = json.loads((root / ".agent-memory" / "gate.json").read_text(encoding="utf-8"))
            self.assertTrue(any("cargo test" in c for c in gate["commands"]))


class ObservabilityTests(unittest.TestCase):
    """The run log (.agent-memory/events.jsonl), `memory.py stats`, the Stop hook's releases, skill-eval transcripts."""

    def _repo(self, t, gate_ok=True):
        root = Path(t)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=root, check=True)
        run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-stop-gate"], root)
        py = sys.executable.replace("\\", "/")
        (root / "ok.flag").write_text("1", encoding="utf-8")
        gate = {"commands": [f'"{py}" -c "import os,sys; sys.exit(0 if os.path.exists(\'ok.flag\') else 1)"']}
        (root / ".agent-memory/gate.json").write_text(json.dumps(gate), encoding="utf-8")
        if not gate_ok:
            (root / "ok.flag").unlink()
        return root

    def _events(self, root):
        f = root / ".agent-memory/events.jsonl"
        return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    def test_session_id_from_the_hook_tags_later_events(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            r = run([MEM, "start"], root, stdin=json.dumps({"session_id": "sess-1", "source": "startup"}))
            self.assertIn("<project-memory", r.stdout)
            run([MEM, "gate"], root, stdin="")
            ev = self._events(root)
            self.assertEqual([(e["ev"], e["session"]) for e in ev], [("session_start", "sess-1"), ("gate", "sess-1")])
            self.assertEqual(ev[0]["source"], "startup")
            self.assertEqual(ev[1]["result"], "pass")
            ignored = subprocess.run(["git", "check-ignore", ".agent-memory/events.jsonl", ".agent-memory/.session"],
                                     cwd=root, capture_output=True, text=True).stdout.split()
            self.assertEqual(len(ignored), 2)  # the run log is local, not committed

    def test_start_does_not_wait_for_a_stdin_that_stays_open(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            p = subprocess.Popen([sys.executable, str(MEM), "start"], cwd=root, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))  # as run(): the digest has non-ASCII text
            try:
                p.stdin.write(json.dumps({"session_id": "open-pipe"}).encode())
                p.stdin.flush()
                rc = p.wait(timeout=20)  # stdin is still open: the command must not wait for it
                self.assertEqual(rc, 0, p.stderr.read().decode("utf-8", "replace"))
                self.assertIn(b"<project-memory", p.stdout.read())
                self.assertEqual(self._events(root)[0]["session"], "open-pipe")  # what was written is still used
            finally:
                p.stdin.close()
                p.stdout.close()
                p.stderr.close()

    def test_gate_and_feature_events_and_stats(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t, gate_ok=False)
            m = lambda *a: run([MEM, *a], root, stdin="", env={"AGENT_SESSION_ID": "s-9"})
            self.assertEqual(m("gate").returncode, 1)
            m("feature", "add", "--id", "F-1", "--desc", "d", "--criterion", "c")
            m("feature", "fail", "--id", "F-1")
            m("feature", "pass", "--id", "F-1", "--evidence", "e", "--verified-by", "evaluator")  # gate is red
            (root / "ok.flag").write_text("1", encoding="utf-8")
            self.assertEqual(m("gate").returncode, 0)
            m("gate")  # skipped
            m("feature", "add", "--id", "F-2", "--desc", "d", "--criterion", "c")
            m("feature", "pass", "--id", "F-2", "--evidence", "e", "--verified-by", "human")
            m("lesson", "add", "--key", "some-rule", "--rule", "Do the thing every time.")
            m("lesson", "vote", "--key", "some-rule", "--vote", "helpful")
            d = json.loads(m("stats", "--json").stdout)
            self.assertEqual((d["gate"]["runs"], d["gate"]["failed"], d["gate"]["skipped"]), (2, 1, 1))
            self.assertEqual(d["gate"]["fail_rate"], 0.5)
            self.assertEqual(d["sessions"], 1)
            self.assertEqual(d["features"]["passed"], 2)
            self.assertEqual(d["features"]["rounds_per_pass"], 1.5)  # F-1 needed 2 rounds, F-2 needed 1
            self.assertEqual(d["features"]["passed_without_green_gate"], ["F-1"])
            self.assertEqual(d["features"]["verified_by"], {"evaluator": 1, "human": 1})
            self.assertEqual((d["lessons"]["added"], d["lessons"]["helpful"]), (1, 1))
            text = m("stats").stdout
            self.assertIn("1 failed (50%)", text)
            self.assertIn("F-1", text)
            fail = [e for e in self._events(root) if e["ev"] == "gate" and e["result"] == "fail"][0]
            cmd = json.loads((root / ".agent-memory/gate.json").read_text(encoding="utf-8"))["commands"][0]
            self.assertTrue(cmd.startswith(fail["failed"].rstrip("…")), fail["failed"])  # bounded to 120 characters

    def test_events_can_be_turned_off_and_never_break_a_command(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertEqual(run([MEM, "gate"], root, stdin="", env={"AGENT_MEMORY_EVENTS": "0"}).returncode, 0)
            self.assertEqual(self._events(root), [])
            (root / ".agent-memory/events.jsonl").mkdir()  # an unwritable log
            self.assertEqual(run([MEM, "gate", "--force"], root, stdin="").returncode, 0)
            self.assertEqual(run([MEM, "event", "--ev", "stop", "--field", "outcome=api_key=abc"], root).returncode, 2)

    def test_stop_hook_records_block_and_release_and_digest_reports_it(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t, gate_ok=False)
            hook = root / ".claude/hooks/gate_on_stop.py"
            self.assertEqual(run([hook], root, stdin=json.dumps({"session_id": "s-1", "stop_hook_active": False})).returncode, 2)
            self.assertEqual(run([hook], root, stdin=json.dumps({"session_id": "s-1", "stop_hook_active": True})).returncode, 0)
            stops = [(e["outcome"], e["session"]) for e in self._events(root) if e["ev"] == "stop"]
            self.assertEqual(stops, [("blocked", "s-1"), ("released-red", "s-1")])
            digest = run([MEM, "start"], root, stdin="").stdout
            self.assertIn("Needs you", digest)
            self.assertIn("without a passing completion gate", digest)
            self.assertIn("1 released without a passing gate", run([MEM, "stats"], root).stdout)
            (root / "ok.flag").write_text("1", encoding="utf-8")
            run([MEM, "gate"], root, stdin="")
            self.assertNotIn("without a passing completion gate", run([MEM, "start"], root, stdin="").stdout)

    def test_release_is_green_only_for_a_pass_on_the_final_code(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            hook = root / ".claude/hooks/gate_on_stop.py"
            release = json.dumps({"session_id": "s-1", "stop_hook_active": True})
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 0)
            self.assertEqual(run([MEM, "gate", "--check"], root, stdin="").returncode, 0)
            (root / "later_edit.py").write_text("x = 1\n", encoding="utf-8")  # after the pass: nothing checked it
            self.assertEqual(run([MEM, "gate", "--check"], root, stdin="").returncode, 1)
            self.assertEqual(run([hook], root, stdin=release).returncode, 0)
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 0)
            self.assertEqual(run([hook], root, stdin=release).returncode, 0)
            stops = [e["outcome"] for e in self._events(root) if e["ev"] == "stop"]
            self.assertEqual(stops, ["released-red", "released-green"])

    def test_init_keeps_a_gitignore_line_that_has_no_final_newline(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / ".agent-memory").mkdir()
            (root / ".agent-memory/.gitignore").write_text(".lock\nevals/results/", encoding="utf-8")  # an older install
            self.assertEqual(run([MEM, "init"], root).returncode, 0)
            lines = (root / ".agent-memory/.gitignore").read_text(encoding="utf-8").splitlines()
            for line in ("evals/results/", "events.jsonl", "events.1.jsonl", ".session"):
                self.assertIn(line, lines)

    def test_upgrade_replaces_an_older_hook_script(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            hook = root / ".claude/hooks/gate_on_stop.py"
            hook.write_text("# old copy\n", encoding="utf-8")
            run([INST, "project", root, "--no-upstream", "--profile", "none"], root)
            self.assertEqual(hook.read_text(encoding="utf-8"), "# old copy\n")  # never without --upgrade
            run([INST, "project", root, "--no-upstream", "--profile", "none", "--upgrade"], root)
            self.assertIn("released-red", hook.read_text(encoding="utf-8"))
            self.assertTrue(list((root / ".claude/hooks/.backup").rglob("gate_on_stop.py")))

    def test_skill_eval_keeps_transcripts_and_costs_by_tokens(self):
        agent = ("import json, pathlib\n"
                 "s = pathlib.Path('.agents/skills/tdd-loop/SKILL.md').read_text(encoding='utf-8')\n"
                 "ok = 'EVAL-MARKER' in s\n"
                 "pathlib.Path('result.txt').write_text('pass' if ok else 'fail', encoding='utf-8')\n"
                 "print(json.dumps({'total_cost_usd': 0.3 if ok else 0.1, 'num_turns': 2,\n"
                 "                  'usage': {'input_tokens': 300 if ok else 100, 'output_tokens': 0}}))\n")
        with tempfile.TemporaryDirectory() as t:
            se = SkillEvalTests()
            root, py = se._repo(t)
            (root / "json_agent.py").write_text(agent, encoding="utf-8")
            subprocess.run(["git", "add", "json_agent.py"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "agent"], cwd=root, check=True)
            p = se._proposal(root, "- EVAL-MARKER: check this.")
            r = run([EVAL, "run", "--proposal", p, "--repeats", "1", "--agent-cmd", f'"{py}" json_agent.py'], root)
            self.assertIn("VERDICT: IMPROVES", r.stdout, r.stdout + r.stderr)
            self.assertIn("cost ×3.0 (cost_usd)", r.stdout)
            res = root / ".agent-memory/evals/results"
            rec = json.loads(next(res.glob("*-proposal-p.json")).read_text(encoding="utf-8"))
            run1 = rec["per_task"]["TASK-A"]["candidate"][0]
            self.assertEqual((run1["tokens"], run1["cost_usd"], run1["turns"]), (300, 0.3, 2))
            self.assertEqual(rec["summary"]["evolve"]["cost_basis"], "cost_usd")
            log = Path(rec["transcripts"]) if Path(rec["transcripts"]).is_absolute() else root / rec["transcripts"]
            self.assertEqual(len(list(log.glob("*.log"))), 4)
            self.assertIn("total_cost_usd", (log / run1["transcript"]).read_text(encoding="utf-8"))


class EvolutionTests(unittest.TestCase):
    """Reproduction check, gate guards, doctor, and the skill-eval statistics."""

    def _git(self, root, *args):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True, capture_output=True)

    def _repo(self, t):
        root = Path(t)
        self._git(root, "init", "-q")
        (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")  # the defect
        self._git(root, "add", "calc.py")
        self._git(root, "commit", "-q", "-m", "init")
        self.assertEqual(run([MEM, "init"], root).returncode, 0)
        self.py = sys.executable.replace("\\", "/")
        (root / "test_calc.py").write_text("import calc, sys\nsys.exit(0 if calc.add(2, 2) == 4 else 1)\n", encoding="utf-8")
        return root

    def _events(self, root, ev):
        path = root / ".agent-memory/events.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        return [e for e in map(json.loads, lines) if e["ev"] == ev]

    def _repro(self, root, *extra):
        return run([MEM, "repro", "--test", f'"{self.py}" test_calc.py', "--test-file", "test_calc.py", *extra], root)

    def test_repro_is_verified_when_the_test_fails_on_the_base_and_passes_now(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")  # the fix, not committed
            r = self._repro(root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("repro VERIFIED", r.stdout)
            self.assertEqual([e["result"] for e in self._events(root, "repro")], ["verified"])
            self.assertEqual(run([MEM, "repro", "--check"], root).returncode, 0)
            (root / "calc.py").write_text("def add(a, b):\n    return a + b + 0\n", encoding="utf-8")
            self.assertEqual(run([MEM, "repro", "--check"], root).returncode, 1)  # verified for other code
            worktrees = subprocess.run(["git", "worktree", "list"], cwd=root, capture_output=True, text=True).stdout
            self.assertEqual(len(worktrees.strip().splitlines()), 1)  # the throw-away checkout is gone
            self.assertIn("1 verified", run([MEM, "stats"], root).stdout)

    def test_repro_rejects_a_test_that_passes_on_the_base_or_still_fails(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            r = self._repro(root)  # no fix: the test fails on the base and on the current code
            self.assertEqual(r.returncode, 1)
            self.assertIn("repro STILL-FAILING", r.stdout)
            (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            (root / "test_calc.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")  # cannot fail
            r = self._repro(root)
            self.assertEqual(r.returncode, 1)
            self.assertIn("repro NOT-REPRODUCED", r.stdout)
            (root / "test_calc.py").write_text("import calc, sys\nsys.exit(0 if calc.add(2, 2) == 4 else 1)\n", encoding="utf-8")
            r = self._repro(root, "--expect", "AssertionError: wrong sum")  # fails on the base for another reason
            self.assertEqual(r.returncode, 1)
            self.assertIn("repro WRONG-FAILURE", r.stdout)
            self.assertEqual(run([MEM, "repro", "--check"], root).returncode, 1)

    def test_gate_runs_the_committed_gate_json_and_reports_the_edit(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            gate = root / ".agent-memory/gate.json"
            gate.write_text(json.dumps({"commands": [f'"{self.py}" -c "import sys; sys.exit(1)"']}), encoding="utf-8")
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 1)  # not tracked yet: used as it is
            self._git(root, "add", ".agent-memory/gate.json")
            self._git(root, "commit", "-q", "-m", "gate")
            gate.write_text(json.dumps({"commands": [f'"{self.py}" -c "import sys; sys.exit(0)"']}), encoding="utf-8")
            r = run([MEM, "gate"], root, stdin="")  # the agent made the gate easy: the committed one still runs
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("gate WARNING: .agent-memory/gate.json differs from HEAD", r.stdout)
            digest = run([MEM, "start"], root, stdin="").stdout
            self.assertIn("Gate warning: .agent-memory/gate.json differs from HEAD", digest)
            self._git(root, "commit", "-q", "-am", "a person accepts the new gate")
            r = run([MEM, "gate"], root, stdin="")
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertNotIn("WARNING", r.stdout)
            self.assertNotIn("Gate warning", run([MEM, "start"], root, stdin="").stdout)

    def test_gate_reports_deleted_tests_and_new_skip_markers(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            (root / "tests").mkdir()
            (root / "tests/test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
            (root / "tests/test_b.py").write_text("def test_b():\n    assert True\n", encoding="utf-8")
            (root / "notes.py").write_text("x = 1\n", encoding="utf-8")
            (root / ".agent-memory/gate.json").write_text(
                json.dumps({"commands": [f'"{self.py}" -c "import sys; sys.exit(0)"']}), encoding="utf-8")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-q", "-m", "tests")
            self.assertNotIn("WARNING", run([MEM, "gate"], root, stdin="").stdout)
            (root / "tests/test_a.py").unlink()
            (root / "tests/test_b.py").write_text("import pytest\n\n@pytest.mark.skip(reason='flaky')\ndef test_b():\n    assert True\n", encoding="utf-8")
            (root / "notes.py").write_text("# @pytest.mark.skip is fine outside a test file\n", encoding="utf-8")
            r = run([MEM, "gate"], root, stdin="")
            self.assertEqual(r.returncode, 0, r.stdout)  # reported, not blocked
            self.assertIn("gate WARNING: test file deleted: tests/test_a.py", r.stdout)
            self.assertIn("gate WARNING: skip marker added in tests/test_b.py", r.stdout)
            self.assertNotIn("notes.py", r.stdout)
            self.assertEqual(len(self._events(root, "gate")[-1]["warnings"]), 2)
            self.assertIn("Gate warning: test file deleted", run([MEM, "start"], root, stdin="").stdout)

    def test_doctor_finds_a_gate_command_that_cannot_run(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            r = run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-stop-gate"], root)
            self.assertEqual(r.returncode, 0, r.stderr)
            mem = root / ".agents/skills/long-horizon/scripts/memory.py"
            (root / ".agent-memory/gate.json").write_text(
                json.dumps({"commands": [f'"{self.py}" -c "import sys; sys.exit(0)"']}), encoding="utf-8")
            r = run([mem, "doctor"], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("doctor: 0 problem(s)", r.stdout)
            self.assertIn("--bare", r.stdout)  # the Stop gate does not run there
            (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": ["no-such-tool-xyz check ."]}), encoding="utf-8")
            (root / ".claude/hooks/gate_on_stop.py").unlink()
            r = run([mem, "doctor"], root)
            self.assertEqual(r.returncode, 1)
            self.assertIn("`no-such-tool-xyz` is not installed or not on PATH", r.stdout)
            self.assertIn("gate_on_stop.py` is missing", r.stdout)

    def test_skill_eval_reports_paired_interval_and_pass_all(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("skill_eval_under_test", EVAL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        runs = lambda *passed: [{"passed": p, "tampered": False, "seconds": 1.0} for p in passed]
        per_task = {  # baseline passes 2 of 3 on every task; the candidate passes all runs on 3 of 4 tasks
            f"T{i}": {"split": "evolve", "base": runs(True, True, False), "cand": runs(*([True] * 3 if i else [False] * 3))}
            for i in range(4)}
        s = mod.summarise(per_task, "base", "cand")["evolve"]
        self.assertEqual((s["base"]["pass_all"], s["cand"]["pass_all"]), (0.0, 0.75))
        self.assertEqual(s["tasks"], 4)
        low, high = s["delta_ci95"]
        self.assertLess(low, 0)  # 4 tasks: the interval of the difference includes zero
        self.assertGreater(high, s["delta"])
        self.assertIsNone(mod.paired_ci([0.5]))
        self.assertEqual(mod.paired_ci([0.2] * 5), [0.2, 0.2])

    def test_skill_eval_power_says_when_the_task_set_is_too_small(self):
        with tempfile.TemporaryDirectory() as t:
            r = run([EVAL, "power", "--delta", "0.15", "--rho", "0.6", "--tasks", "10"], t)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("paired design (same tasks, both variants): 67 tasks", r.stdout)
            self.assertIn("independent samples: 167 tasks", r.stdout)
            self.assertIn("10 tasks cannot show a change of +15%", r.stdout)
            self.assertEqual(run([EVAL, "power", "--delta", "0"], t).returncode, 2)


class EvaluatorViewAndCiTests(unittest.TestCase):
    """The evaluator's view of a change, the subagents, the CI template, and console encoding."""

    def _git(self, root, *args):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True, capture_output=True)

    def _repo(self, t):
        root = Path(t)
        self._git(root, "init", "-q")
        (root / "pool.py").write_text("def take(pool):\n    return pool.pop()\n", encoding="utf-8")
        (root / "pool.js").write_text("function take(pool) {\n  return pool.pop();\n}\n", encoding="utf-8")
        (root / "pool.c").write_text("int take(int *pool);\n", encoding="utf-8")
        self._git(root, "add", "-A")
        self._git(root, "commit", "-q", "-m", "init")
        self.assertEqual(run([MEM, "init"], root).returncode, 0)
        return root

    def test_diff_view_hides_the_comments_that_the_change_added(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            (root / "pool.py").write_text(
                "def take(pool):\n    # Thread-safe: the lock is held upstream\n    item = pool.pop()  # newest first\n    return item\n", encoding="utf-8")
            (root / "pool.js").write_text(
                "function take(pool) {\n  // safe: callers hold the lock\n  /* reviewed */\n  return pool.shift();\n}\n", encoding="utf-8")
            (root / "pool.c").write_text("#include <stdio.h>\nint take(int *pool);\n", encoding="utf-8")
            (root / "new_module.py").write_text("x = 1\n", encoding="utf-8")
            r = run([MEM, "diff-view"], root)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("Thread-safe", r.stdout)
            self.assertNotIn("callers hold the lock", r.stdout)
            self.assertNotIn("reviewed", r.stdout)
            self.assertIn("+    item = pool.pop()  # newest first", r.stdout)  # code stays, with its trailing comment
            self.assertIn("+  return pool.shift();", r.stdout)
            self.assertIn("+#include <stdio.h>", r.stdout)  # not a comment in C
            self.assertIn("new file that git does not track (read it directly): new_module.py", r.stdout)
            self.assertIn("3 comment line(s)", r.stdout)
            self.assertNotIn(".agent-memory", r.stdout)

    def test_installer_adds_the_subagents_and_upgrades_an_older_evaluator(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            agents = root / ".claude/agents"
            agents.mkdir(parents=True)
            (agents / "evaluator.md").write_text("old evaluator\n", encoding="utf-8")
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none"], root).returncode, 0)
            self.assertEqual((agents / "evaluator.md").read_text(encoding="utf-8"), "old evaluator\n")  # never without --upgrade
            criteria = (agents / "criteria.md").read_text(encoding="utf-8")
            self.assertIn("tools: Read, Grep, Glob\n", criteria)  # read-only: it cannot write the implementation
            self.assertFalse((root / ".github").exists())  # CI only on request
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none", "--upgrade"], root).returncode, 0)
            evaluator = (agents / "evaluator.md").read_text(encoding="utf-8")
            for text in ("diff-view", "repro --check", "UNKNOWN", "find defects"):
                self.assertIn(text, evaluator)
            self.assertTrue(list((agents / ".backup").rglob("evaluator.md")))

    def test_with_ci_adds_a_workflow_that_uses_the_base_branch_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            r = run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-ci"], root)
            self.assertEqual(r.returncode, 0, r.stderr)
            wf = (root / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8")
            self.assertIn("AGENT_GATE_REF: origin/${{ github.base_ref }}", wf)
            self.assertIn("memory.py gate --force", wf)
            self.assertIn("contents: read", wf)
            self.assertNotIn("\t", wf)

    def test_workflows_pin_actions_by_commit(self):
        import re
        files = list((PACK / ".github/workflows").glob("*.yml")) + list((PACK / "templates/ci").glob("*.yml"))
        self.assertGreaterEqual(len(files), 2)
        for f in files:
            uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", f.read_text(encoding="utf-8"), re.M)
            self.assertTrue(uses, f)
            for u in uses:
                self.assertRegex(u, r"@[0-9a-f]{40}$", f"{f.name}: {u} is not pinned by commit")

    def test_output_to_a_pipe_is_utf8_without_help_from_the_environment(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            run([MEM, "task", "open", "--title", "ask the user", "--status", "needs-human"], root)
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
            env["PYTHONLEGACYWINDOWSSTDIO"] = ""
            r = subprocess.run([sys.executable, str(MEM), "start"], cwd=root, input=b"", capture_output=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            text = r.stdout.decode("utf-8")  # raises if the script wrote the console code page
            self.assertIn("Session start digest", text)
            self.assertIn("⚑", text)  # a character that the Windows console code page does not have


JUDGE = """
import pathlib
work = pathlib.Path('work.txt').read_text(encoding='utf-8')
if 'unsure' not in work:  # a judge that cannot decide prints no verdict line
    print('checked the change')
    print('VERDICT: FAIL' if 'bug' in work else 'VERDICT: PASS')
"""


class JudgeAndEvidenceTests(unittest.TestCase):
    """Evaluator calibration on cases with a known answer, and the evidence block."""

    def _git(self, root, *args):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True, capture_output=True)

    def _repo(self, t):
        root = Path(t)
        self._git(root, "init", "-q")
        (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (root / "judge.py").write_text(JUDGE, encoding="utf-8")
        self._git(root, "add", "-A")
        self._git(root, "commit", "-q", "-m", "init")
        self.py = sys.executable.replace("\\", "/")
        return root

    def _case(self, cid, label, work):
        setup = f'"{self.py}" -c "open(\'work.txt\', \'w\').write(\'{work}\')"'
        return json.dumps({"id": cid, "label": label, "prompt": "Judge the change in work.txt.", "setup": setup})

    def test_judge_reports_wrong_work_approved_and_correct_work_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none"], root).returncode, 0)
            cases = root / "cases.jsonl"
            cases.write_text("\n".join([
                "# labels stay out of the prompt",
                self._case("w1", "wrong", "bug"),        # caught
                self._case("w2", "wrong", "looks fine"),  # approved: the failure that matters
                self._case("c1", "correct", "fine"),
                self._case("c2", "correct", "bug-like"),  # rejected without cause
                self._case("c3", "correct", "unsure"),    # no verdict line
            ]) + "\n", encoding="utf-8")
            judge_cmd = f'"{self.py}" judge.py'
            r = run([EVAL, "judge", "--cases", cases, "--judge-cmd", judge_cmd, "--max-runs", "2"], root)
            self.assertEqual(r.returncode, 2)  # 5 runs planned: the budget guard stops it
            r = run([EVAL, "judge", "--cases", cases, "--judge-cmd", judge_cmd], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("wrong work approved:    1/2 (50%", r.stdout)
            self.assertIn("correct work rejected:  1/3 (33%", r.stdout)
            self.assertIn("no decision (UNKNOWN):  1/5 (20%)", r.stdout)
            self.assertIn("c3", r.stdout)
            self.assertIn("(no verdict line)", r.stdout)
            reports = list((root / ".agent-memory/evals/results").glob("*-judge.json"))
            self.assertEqual(len(reports), 1)
            summary = json.loads(reports[0].read_text(encoding="utf-8"))["summary"]
            self.assertEqual((summary["wrong_approved"], summary["correct_rejected"], summary["unknown"]), (1, 1, 1))
            self.assertEqual(summary["mcc_decided"], 0.0)  # 1 of each outcome: no better than chance
            self.assertEqual(len(list((root / ".agent-memory/evals/results").glob("*-judge-transcripts/*.txt"))), 5)
            worktrees = subprocess.run(["git", "worktree", "list"], cwd=root, capture_output=True, text=True).stdout
            self.assertEqual(len(worktrees.strip().splitlines()), 1)

    def test_judge_refuses_a_case_without_a_label(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            run([INST, "project", root, "--no-upstream", "--profile", "none"], root)
            (root / "cases.jsonl").write_text(json.dumps({"id": "x", "prompt": "p"}) + "\n", encoding="utf-8")
            r = run([EVAL, "judge", "--cases", "cases.jsonl", "--judge-cmd", "echo VERDICT: PASS"], root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("label (correct|wrong)", r.stderr)

    def test_evidence_lists_what_is_verified_and_what_is_not(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertEqual(run([MEM, "init"], root).returncode, 0)
            r = run([MEM, "evidence", "--strict"], root)
            self.assertEqual(r.returncode, 1)  # nothing is verified yet
            for text in ("no completion gate", "Reproduction: none verified", "no acceptance criteria were recorded"):
                self.assertIn(text, r.stdout)
            (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            (root / "test_calc.py").write_text("import calc, sys\nsys.exit(0 if calc.add(2, 2) == 4 else 1)\n", encoding="utf-8")
            test = f'"{self.py}" test_calc.py'
            (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": [test]}), encoding="utf-8")
            self.assertEqual(run([MEM, "repro", "--test", test, "--test-file", "test_calc.py"], root).returncode, 0)
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 0)
            run([MEM, "feature", "add", "--id", "F-1", "--desc", "add sums", "--criterion", "add(2, 2) == 4"], root)
            run([MEM, "feature", "pass", "--id", "F-1", "--evidence", "test_calc passes", "--verified-by", "evaluator"], root)
            r = run([MEM, "evidence", "--strict"], root)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("Gate: PASSED for exactly this code (1 commands)", r.stdout)
            self.assertIn("Reproduction: VERIFIED", r.stdout)
            self.assertIn("1 of 1 features graded as passing (F-1 by evaluator)", r.stdout)
            self.assertIn("1 file changed", r.stdout)
            self.assertIn("- nothing: every check above has a record for this code", r.stdout)
            (root / "calc.py").write_text("def add(a, b):\n    return a + b + 0\n", encoding="utf-8")  # a later edit
            r = run([MEM, "evidence", "--strict"], root)
            self.assertEqual(r.returncode, 1)
            self.assertIn("Gate: NOT passed for this code", r.stdout)
            self.assertIn("Reproduction: none verified for this code", r.stdout)

    def test_evidence_names_a_feature_that_was_not_graded_by_an_independent_verifier(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            run([MEM, "init"], root)
            run([MEM, "feature", "add", "--id", "F-1", "--desc", "x", "--criterion", "c1"], root)
            run([MEM, "feature", "add", "--id", "F-2", "--desc", "y", "--criterion", "c2"], root)
            run([MEM, "feature", "pass", "--id", "F-1", "--evidence", "ok", "--verified-by", "human"], root)
            out = run([MEM, "evidence"], root).stdout
            self.assertIn("1 of 2 features graded as passing (F-1 by human)", out)
            self.assertIn("features not graded as passing: F-2", out)
            self.assertNotIn("without an independent verifier", out)


AGENT = """
import pathlib, sys
task = sys.stdin.read()
fixed = 'gate failed' in task and 'never' not in task
pathlib.Path('calc.py').write_text('def add(a, b):\\n    return a %s b\\n' % ('+' if fixed else '-'), encoding='utf-8')
pathlib.Path('rounds.txt').open('a', encoding='utf-8').write(task[:40].replace('\\n', ' ') + '\\n')
"""


class HeadlessTests(unittest.TestCase):
    """The gate without hooks, and scripts that start on an old Python."""

    def _repo(self, t):
        root = Path(t)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
        (root / "agent.py").write_text(AGENT, encoding="utf-8")
        (root / "test_calc.py").write_text("import calc, sys\nsys.exit(0 if calc.add(2, 2) == 4 else 1)\n", encoding="utf-8")
        self.py = sys.executable.replace("\\", "/")
        self.assertEqual(run([MEM, "init"], root).returncode, 0)
        return root

    def _gate(self, root):
        (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": [f'"{self.py}" test_calc.py']}), encoding="utf-8")

    def test_gated_run_gives_a_red_gate_back_to_the_agent(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self._gate(root)
            r = run([MEM, "gated-run", "--agent-cmd", f'"{self.py}" agent.py', "--prompt", "make add work"], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("gate FAILED", r.stdout)
            self.assertIn("the gate passed after 2 agent round(s)", r.stdout)
            rounds = (root / "rounds.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rounds), 2)
            self.assertTrue(rounds[0].startswith("make add work"))
            self.assertTrue(rounds[1].startswith("The completion gate failed"))
            events = [json.loads(l) for l in (root / ".agent-memory/events.jsonl").read_text(encoding="utf-8").splitlines()]
            last = [e for e in events if e["ev"] == "gated-run"][-1]
            self.assertEqual((last["result"], last["rounds"]), ("pass", 2))
            self.assertEqual(run([MEM, "gate", "--check"], root).returncode, 0)

    def test_gated_run_exits_1_when_the_gate_stays_red(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self._gate(root)
            r = run([MEM, "gated-run", "--agent-cmd", f'"{self.py}" agent.py', "--prompt", "never fix it", "--retries", "1"], root)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("the gate still fails after 2 agent round(s)", r.stdout)
            self.assertEqual(len((root / "rounds.txt").read_text(encoding="utf-8").splitlines()), 2)

    def test_gated_run_refuses_a_repository_without_a_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            r = run([MEM, "gated-run", "--agent-cmd", f'"{self.py}" agent.py', "--prompt", "x"], root)
            self.assertEqual(r.returncode, 2)
            self.assertIn("the run would have no check", r.stderr)
            self.assertFalse((root / "rounds.txt").exists())

    @unittest.skipIf(sys.version_info < (3, 8), "ast.parse has no feature_version")
    def test_scripts_parse_on_python_3_6_so_that_the_version_message_can_run(self):
        import ast
        scripts = [INST, *sorted((PACK / "skills").glob("*/scripts/*.py")), *sorted((PACK / "templates/.claude/hooks").glob("*.py"))]
        self.assertGreaterEqual(len(scripts), 7)
        for path in scripts:
            text = path.read_text(encoding="utf-8")
            with self.subTest(script=path.name):
                ast.parse(text, feature_version=(3, 6))
                self.assertNotIn("from __future__ import annotations", text)  # a SyntaxError on 3.6, before any code runs
                self.assertIn("sys.version_info < (3, 9)", text)
                tree = ast.parse(text)  # with the guard gone, an annotation such as `dict | None` fails on Python 3.9
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        notes = [x.annotation for x in node.args.args + node.args.kwonlyargs if x.annotation] + ([node.returns] if node.returns else [])
                        for note in notes:
                            self.assertFalse(any(isinstance(n, ast.BinOp) for n in ast.walk(note)), f"{path.name}:{node.lineno}")


class UninstallTests(unittest.TestCase):
    def _installed(self, t):
        root = Path(t)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
        (root / ".claude").mkdir()
        (root / ".claude/settings.json").write_text(json.dumps({
            "permissions": {"deny": ["Read(./.env)"]},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}), encoding="utf-8")
        r = run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-stop-gate", "--with-ci"], root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return root

    def test_uninstall_removes_what_the_pack_installed_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._installed(t)
            self.assertTrue((root / ".agents/skills/long-horizon/SKILL.md").exists())
            r = run([INST, "uninstall", root, "--dry-run"], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("[dry-run] removed:", r.stdout)
            self.assertTrue((root / ".agents/skills/long-horizon/SKILL.md").exists())  # a dry run changes nothing
            r = run([INST, "uninstall", root], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for gone in (".agents", ".claude/skills", ".claude/agents", ".claude/hooks", ".github", "CLAUDE.md"):
                self.assertFalse((root / gone).exists() or (root / gone).is_symlink(), gone)
            settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["permissions"], {"deny": ["Read(./.env)"]})
            self.assertEqual(settings["hooks"], {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]})
            self.assertTrue((root / "AGENTS.md").exists())
            self.assertTrue((root / ".agent-memory").is_dir())
            self.assertIn("--purge-memory removes it", r.stdout)
            r = run([INST, "uninstall", root, "--purge-memory"], root)  # a second run finds nothing more of the pack
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse((root / ".agent-memory").exists())

    def test_uninstall_keeps_a_pack_file_that_the_user_changed(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._installed(t)
            evaluator = root / ".claude/agents/evaluator.md"
            evaluator.write_text(evaluator.read_text(encoding="utf-8") + "\nOur team rule.\n", encoding="utf-8")
            (root / ".agents/skills/evaluator/notes.md").write_text("ours\n", encoding="utf-8")
            r = run([INST, "uninstall", root], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(evaluator.exists())
            self.assertTrue((root / ".agents/skills/evaluator/notes.md").exists())
            self.assertFalse((root / ".agents/skills/long-horizon").exists())
            self.assertEqual(r.stdout.count("kept (differs from the pack's copy"), 2)
            r = run([INST, "uninstall", root, "--force"], root)
            self.assertFalse(evaluator.exists())
            self.assertFalse((root / ".agents").exists())

    def test_uninstall_removes_the_settings_file_that_only_the_pack_wrote(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none"], root).returncode, 0)
            self.assertTrue((root / ".claude/settings.json").exists())
            self.assertEqual(run([INST, "uninstall", root], root).returncode, 0)
            self.assertFalse((root / ".claude").exists())


class PluginTests(unittest.TestCase):
    """The repository as a Claude Code plugin and marketplace."""

    def test_manifests_name_files_that_exist(self):
        plugin = json.loads((PACK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertRegex(plugin["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertFalse(plugin["name"].startswith(("claude-", "anthropic-")))
        for rel in plugin["agents"]:
            self.assertTrue(rel.startswith("./") and ".." not in rel and (PACK / rel).is_file(), rel)
        market = json.loads((PACK / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(market["owner"]["name"], plugin["author"]["name"])
        self.assertEqual([(p["name"], p["source"]) for p in market["plugins"]], [(plugin["name"], "./")])
        self.assertFalse((PACK / "CLAUDE.md").exists())  # a CLAUDE.md at a plugin root is not loaded
        hooks = json.loads((PACK / "hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(sorted(hooks), ["PostToolUse", "SessionStart", "Stop"])
        launcher = (PACK / "bin/aqp-hook").read_text(encoding="utf-8")
        for event, entries in hooks.items():
            command = entries[0]["hooks"][0]["command"]
            self.assertTrue(command.startswith('"${CLAUDE_PLUGIN_ROOT}"/bin/aqp-hook '), command)
            self.assertIn(f"\n  {command.split()[-1]}) ", launcher)
        for script in re.findall(r'script="([^"]+)"', launcher):
            self.assertTrue((PACK / script).is_file(), script)
        for name in ("aqp-hook", "aqp-memory"):
            raw = (PACK / "bin" / name).read_bytes()
            self.assertTrue(raw.startswith(b"#!/bin/sh\n"), name)

    @unittest.skipIf(os.name == "nt", "the launchers are POSIX shell scripts")
    def test_plugin_hooks_run_from_the_plugin_and_yield_to_a_project_install(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), CLAUDE_PLUGIN_ROOT=str(PACK))
            sh = lambda *args, stdin="{}": subprocess.run(["sh", *map(str, args)], cwd=root, env=env, input=stdin,
                                                          capture_output=True, text=True)
            r = sh(PACK / "bin/aqp-memory", "init")
            self.assertEqual(r.returncode, 0, r.stderr)
            r = sh(PACK / "bin/aqp-hook", "start")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("# Session start digest", r.stdout)
            self.assertIn("run `aqp-memory` in its place", r.stdout)
            self.assertEqual(sh(PACK / "bin/aqp-hook", "stop").returncode, 0)  # no gate file: nothing to enforce
            py = sys.executable
            (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": [f'"{py}" -c "import sys; sys.exit(1)"']}), encoding="utf-8")
            r = sh(PACK / "bin/aqp-hook", "stop")
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # the gate is red: the agent may not stop
            self.assertIn("Completion gate failed", r.stderr)
            self.assertEqual(sh(PACK / "bin/aqp-hook", "nonsense").returncode, 1)
            # a project with the pack's own install keeps its hooks; the plugin's copies stay silent
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-stop-gate"], root).returncode, 0)
            r = sh(PACK / "bin/aqp-hook", "start")
            self.assertEqual((r.returncode, r.stdout), (0, ""))
            self.assertEqual(sh(PACK / "bin/aqp-hook", "stop").returncode, 0)

    def test_doctor_names_the_plugin_install(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            run([MEM, "init"], root)
            out = run([MEM, "doctor"], root).stdout
            self.assertIn("the pack runs as a plugin", out)
            self.assertNotIn("hooks are not installed", out)


FAKE_GH = """
import json, pathlib, sys
log = pathlib.Path(__file__).with_name('gh_calls.jsonl')
log.open('a', encoding='utf-8').write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1:3] == ['pr', 'list']:
    print(pathlib.Path(__file__).with_name('open_prs.json').read_text(encoding='utf-8'))
elif sys.argv[1:3] == ['pr', 'create']:
    body = pathlib.Path(sys.argv[sys.argv.index('--body-file') + 1]).read_text(encoding='utf-8')
    pathlib.Path(__file__).with_name('pr_body.md').write_text(body, encoding='utf-8')
    print('https://example.invalid/pull/7')
"""


class PullRequestTests(unittest.TestCase):
    """Risk label and cost in the evidence block; a draft pull request only after a green gate; the issue workflow."""

    def _git(self, root, *args):
        r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def _repo(self, t, good=True):
        """A clone with a remote, a committed gate on main, and one commit of work on the branch agent/issue-12."""
        base, tools = Path(t), Path(t) / "tools"
        tools.mkdir()
        (tools / "gh.py").write_text(FAKE_GH, encoding="utf-8")
        (tools / "open_prs.json").write_text("[]", encoding="utf-8")
        self._git(base, "init", "-q", "--bare", "remote.git")
        root = base / "work"
        root.mkdir()
        self._git(root, "init", "-q", "-b", "main")
        self.py = sys.executable.replace("\\", "/")
        (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (root / "test_calc.py").write_text("import calc, sys\nsys.exit(0 if calc.add(2, 2) == 4 else 1)\n", encoding="utf-8")
        self.assertEqual(run([MEM, "init"], root).returncode, 0)
        (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": [f'"{self.py}" test_calc.py']}), encoding="utf-8")
        self._git(root, "add", "-A")
        self._git(root, "commit", "-q", "-m", "base")
        self._git(root, "remote", "add", "origin", str(base / "remote.git"))
        self._git(root, "push", "-q", "-u", "origin", "main")
        self._git(root, "checkout", "-q", "-b", "agent/issue-12")
        (root / "calc.py").write_text("def add(a, b):\n    return a %s b\n" % ("+" if good else "//"), encoding="utf-8")
        self._git(root, "commit", "-q", "-am", "fix add")
        self.env = dict(os.environ, AGENT_GH=f'"{self.py}" "{(tools / "gh.py").as_posix()}"')
        self.tools = tools
        return root

    def _calls(self):
        f = self.tools / "gh_calls.jsonl"
        return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []

    def test_pr_opens_a_draft_with_the_evidence_after_a_green_gate(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            r = run([MEM, "pr", "--title", "Fix add", "--issue", "12", "--base", "origin/main", "--cost-usd", "0.4", "--dry-run"], root, env=self.env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("would push `agent/issue-12`", r.stdout)
            self.assertEqual([c[:2] for c in self._calls()], [["pr", "list"]])  # a dry run opens nothing
            r = run([MEM, "pr", "--title", "Fix add", "--issue", "12", "--base", "origin/main", "--cost-usd", "0.4"], root, env=self.env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("draft pull request opened", r.stdout)
            self.assertIn("https://example.invalid/pull/7", r.stdout)
            create = [c for c in self._calls() if c[:2] == ["pr", "create"]]
            self.assertEqual(len(create), 1)
            self.assertIn("--draft", create[0])
            self.assertEqual(create[0][create[0].index("--base") + 1], "main")
            self.assertFalse(any("merge" in c for c in self._calls()))
            body = (self.tools / "pr_body.md").read_text(encoding="utf-8")
            for text in ("Gate: PASSED for exactly this code", "Review risk: MEDIUM", "Cost: $0.40", "Closes #12",
                         "no test was shown to fail before the change", "the agent does not merge"):
                self.assertIn(text, body)
            self.assertIn("agent/issue-12", self._git(Path(t) / "remote.git", "branch", "--list"))  # the branch was pushed

    def test_pr_refuses_a_red_gate_a_duplicate_and_work_that_is_not_committed(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t, good=False)
            r = run([MEM, "pr", "--title", "Fix add", "--issue", "12", "--base", "origin/main"], root, env=self.env)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("The gate is red. No pull request was opened.".lower(), r.stdout.lower())
            self.assertEqual(self._calls(), [])  # nothing reached GitHub
            self.assertNotIn("agent/issue-12", self._git(Path(t) / "remote.git", "branch", "--list"))
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            (self.tools / "open_prs.json").write_text(json.dumps([
                {"number": 3, "title": "Other work", "headRefName": "x", "body": "nothing", "url": "u3"},
                {"number": 5, "title": "Add fix", "headRefName": "someone/else", "body": "Fixes #12", "url": "u5"}]), encoding="utf-8")
            r = run([MEM, "pr", "--title", "Fix add", "--issue", "12", "--base", "origin/main"], root, env=self.env)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertIn("#5 Add fix", r.stdout)
            self.assertNotIn("#3", r.stdout)
            self.assertFalse([c for c in self._calls() if c[:2] == ["pr", "create"]])
            (root / "calc.py").write_text("def add(a, b):\n    return b + a\n", encoding="utf-8")
            r = run([MEM, "pr", "--title", "Fix add", "--base", "origin/main"], root, env=self.env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("not committed", r.stderr)
            self._git(root, "checkout", "-q", "--", "calc.py")
            self._git(root, "checkout", "-q", "main")
            r = run([MEM, "pr", "--title", "Fix add", "--base", "origin/main"], root, env=self.env)
            self.assertEqual(r.returncode, 2)
            self.assertIn("its own branch", r.stderr)

    def test_evidence_gives_a_high_review_risk_for_a_change_to_ci_or_dependencies(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertIn("Review risk: HIGH (the gate did not pass)", run([MEM, "evidence", "--base", "origin/main"], root).stdout)
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 0)
            out = run([MEM, "evidence", "--base", "origin/main"], root).stdout
            self.assertIn("Review risk: MEDIUM", out)  # a small change, but checks have no record
            self.assertIn("Cost: not recorded", out)
            (root / "requirements.txt").write_text("requests==2.0\n", encoding="utf-8")
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/ci.yml").write_text("name: x\n", encoding="utf-8")
            self._git(root, "add", "-A")
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 0)
            out = run([MEM, "evidence", "--base", "origin/main"], root).stdout
            self.assertIn("Review risk: HIGH", out)
            self.assertNotIn("the gate did not pass", out)
            self.assertIn("it changes CI, the hooks or the gate", out)
            self.assertIn("it changes dependencies", out)

    def test_issue_workflow_template_keeps_the_gate_and_the_pull_request_outside_the_agent(self):
        wf = (PACK / "templates/ci/agent-issue.yml").read_text(encoding="utf-8")
        self.assertNotIn("\t", wf)
        for text in ("types: [labeled]", "github.event.label.name == 'agent'", "--max-turns", "--max-budget-usd",
                     "$MEMORY pr --title", "gh issue comment", "Do not push. Do not open a pull request. Do not merge."):
            self.assertIn(text, wf)
        runs = "\n".join(re.findall(r"^\s+run: \|\n((?:\s{10,}.*\n?)+)", wf, re.M))
        self.assertTrue(runs)
        # text from the issue reaches a shell only through an environment variable, never by interpolation
        self.assertNotIn("github.event.issue.title }}", runs)
        self.assertNotIn("github.event.issue.body }}", runs)
        self.assertNotIn("gh pr merge", wf)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            r = run([INST, "project", root, "--no-upstream", "--profile", "none", "--with-issue-workflow"], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue((root / ".github/workflows/agent-issue.yml").is_file())
            self.assertIn("ANTHROPIC_API_KEY", r.stdout)
            self.assertEqual(run([INST, "uninstall", root], root).returncode, 0)
            self.assertFalse((root / ".github").exists())


class TriageAndFactoryTests(unittest.TestCase):
    """Triage of a requirement before work, and the numbers of the agent line."""

    def _repo(self, t):
        root = Path(t)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
        self.assertEqual(run([MEM, "init"], root).returncode, 0)
        return root

    def test_triage_sends_a_thin_issue_back_with_questions(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            r = run([MEM, "triage"], root, stdin="Login is broken")
            self.assertEqual(r.returncode, 4)
            self.assertIn("### Before work can start on this issue", r.stdout)
            self.assertIn("What happens now, and what must happen after the change?", r.stdout)
            (root / "issue.md").write_text("# Export is wrong\n\nThe monthly export gives the wrong numbers for some customers, "
                                           "and we need this fixed before the end of the quarter.\n", encoding="utf-8")
            r = run([MEM, "triage", "--file", "issue.md", "--json"], root)
            self.assertEqual(r.returncode, 4)
            data = json.loads(r.stdout)
            self.assertEqual((data["result"], data["type"]), ("NEEDS-INFO", "fix"))
            self.assertIn("How can the problem be seen?", data["questions"][0])
            template = "## Steps to reproduce\n\n## Expected behaviour\n\n## Actual behaviour\n"
            self.assertEqual(run([MEM, "triage"], root, stdin=template).returncode, 4)

    def test_triage_lets_a_workable_issue_pass(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            issue = ("`DataArray.integrate` has a `dim` argument, but `Dataset.integrate` has a `coord` argument.\n"
                     "It should be `coord` in both. Should this need a deprecation cycle?\n")
            r = run([MEM, "triage"], root, stdin=issue)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("triage: READY", r.stdout)
            # a long text with empty template sections is still workable: a note, not a stop
            long_text = issue * 6 + "\n## Other comments\n\n## Release notes\n"
            r = run([MEM, "triage"], root, stdin=long_text)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("note: Fill in the empty sections", r.stdout)
            self.assertEqual(run([MEM, "triage"], Path(t).parent, stdin=issue).returncode, 0)  # works without .agent-memory/

    def test_triage_subagent_and_workflow_step_are_installed(self):
        wf = (PACK / "templates/ci/agent-issue.yml").read_text(encoding="utf-8")
        self.assertLess(wf.index("- name: Triage"), wf.index("- name: Agent"))
        self.assertIn("if: steps.triage.outputs.ready == 'true'", wf)
        self.assertIn("$MEMORY triage --file .agent-issue.md", wf)
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none"], root).returncode, 0)
            agent = (root / ".claude/agents/triage.md").read_text(encoding="utf-8")
            self.assertIn("tools: Read, Grep, Glob", agent)  # it cannot write code
            self.assertIn("TRIAGE: ASK", agent)
            self.assertTrue((root / ".agents/skills/triage/SKILL.md").is_file())

    def test_factory_report_counts_merges_time_cost_and_reverts(self):
        import datetime
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            tools = root / "tools"
            tools.mkdir()
            (tools / "gh.py").write_text(FAKE_GH, encoding="utf-8")
            now = datetime.datetime.now(datetime.timezone.utc)
            iso = lambda hours: (now - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
            body = "## Verification evidence\n- Review risk: LOW (small change)\n- Cost: $0.50 (given by the caller)\n"
            prs = [
                {"number": 1, "title": "Fix add", "headRefName": "agent/issue-1", "state": "MERGED", "isDraft": False,
                 "createdAt": iso(50), "mergedAt": iso(48), "closedAt": iso(48), "body": body},
                {"number": 2, "title": "Fix sub", "headRefName": "agent/issue-2", "state": "CLOSED", "isDraft": False,
                 "createdAt": iso(40), "mergedAt": None, "closedAt": iso(30), "body": "- Review risk: HIGH (it changes dependencies)\n"},
                {"number": 3, "title": "Fix mul", "headRefName": "agent/issue-3", "state": "OPEN", "isDraft": True,
                 "createdAt": iso(5), "mergedAt": None, "closedAt": None, "body": ""},
                {"number": 4, "title": "Human work", "headRefName": "feature/x", "state": "MERGED", "isDraft": False,
                 "createdAt": iso(20), "mergedAt": iso(19), "closedAt": iso(19), "body": ""},
                {"number": 5, "title": "Revert \"Fix add\"", "headRefName": "revert-1", "state": "MERGED", "isDraft": False,
                 "createdAt": iso(10), "mergedAt": iso(9), "closedAt": iso(9), "body": "Reverts owner/repo#1"},
                {"number": 6, "title": "Old agent work", "headRefName": "agent/issue-0", "state": "MERGED", "isDraft": False,
                 "createdAt": iso(24 * 90), "mergedAt": iso(24 * 89), "closedAt": iso(24 * 89), "body": ""},
            ]
            (tools / "open_prs.json").write_text(json.dumps(prs), encoding="utf-8")
            py = sys.executable.replace("\\", "/")
            env = dict(os.environ, AGENT_GH=f'"{py}" "{(tools / "gh.py").as_posix()}"')
            run([MEM, "triage"], root, stdin="Login is broken")
            run([MEM, "triage"], root, stdin="`add(2, 2)` returns 0. It should return 4.")
            r = run([MEM, "factory"], root, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for text in ("pull requests: 3 opened · 1 merged · 1 closed without merge · 1 open (1 drafts)",
                         "merge rate (of the decided ones): 50% (95% interval",
                         "time to merge: median 2.0 hours",
                         "cost: $0.50 in 1 of 3 pull requests",
                         "review risk: HIGH 1 · LOW 1",
                         "stability: 1 of 1 merged pull requests were reverted",
                         "triage: 1 ready · 1 sent back with questions"):
                self.assertIn(text, r.stdout)
            data = json.loads(run([MEM, "factory", "--json"], root, env=env).stdout)
            self.assertEqual(data["github"]["revert_rate"], 1.0)
            self.assertIsNone(data["github"]["cost_per_merged_usd"])  # one pull request has no cost: no average is given
            env_bad = dict(os.environ, AGENT_GH=f'"{py}" -c "import sys; sys.exit(1)"')
            r = run([MEM, "factory"], root, env=env_bad)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("GitHub: not available", r.stdout)


class GovernanceTests(unittest.TestCase):
    """Secret scan in the gate, provenance trailer, audit record, and what a maintainer checks."""

    def _git(self, root, *args):
        r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def _repo(self, t, gate=None):
        root = Path(t)
        self._git(root, "init", "-q", "-b", "main")
        (root / "app.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(run([MEM, "init"], root).returncode, 0)
        py = sys.executable.replace("\\", "/")
        (root / ".agent-memory/gate.json").write_text(json.dumps(gate or {"commands": [f'"{py}" -c "print(1)"']}), encoding="utf-8")
        self._git(root, "add", "-A")
        self._git(root, "commit", "-q", "-m", "base")
        return root

    def test_gate_stops_on_a_secret_in_the_change_and_hides_its_value(self):
        key = "AKIA" + "ABCDEFGHIJKLMNOP"  # built here, so that this file holds no key-shaped text
        token = "ghp_" + "a1B2" * 9
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            (root / "app.py").write_text(f'x = 1\nAWS_ID = "{key}"\n', encoding="utf-8")
            (root / "new.py").write_text(f'TOKEN = "{token}"\npassword = "Hunter2-real-value"\n', encoding="utf-8")
            r = run([MEM, "gate"], root, stdin="")
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("gate FAILED: secret scan", r.stdout)
            self.assertIn("app.py:2: AWS access key id", r.stdout)
            self.assertIn("new.py:1: GitHub token", r.stdout)
            self.assertIn("new.py:2: password, token or key in an assignment", r.stdout)
            for value in (key, token, "Hunter2-real-value"):
                self.assertNotIn(value, r.stdout)
            self.assertEqual(run([MEM, "gate", "--check"], root).returncode, 1)
            self.assertEqual(run([MEM, "secrets"], root).returncode, 1)
            # placeholders and marked lines are not secrets
            (root / "app.py").write_text(f'x = 1\nAWS_ID = "{key}"  # pack:allow-secret (public example id)\n', encoding="utf-8")
            (root / "new.py").write_text('password = "changeme-1234"\napi_key = "${API_KEY}"\ntoken = os.environ["TOKEN"]\n', encoding="utf-8")
            r = run([MEM, "gate"], root, stdin="")
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(run([MEM, "secrets"], root).returncode, 0)

    def test_secret_scan_can_be_turned_off_and_reads_committed_work_against_a_base(self):
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        with tempfile.TemporaryDirectory() as t:
            py = sys.executable.replace("\\", "/")
            root = self._repo(t, {"commands": [f'"{py}" -c "print(1)"'], "secret_scan": False})
            (root / "app.py").write_text(f'AWS_ID = "{key}"\n', encoding="utf-8")
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 0)
            self._git(root, "checkout", "-q", "-b", "work")
            self._git(root, "commit", "-q", "-am", "work")
            self.assertEqual(run([MEM, "secrets"], root).returncode, 0)                    # nothing since HEAD
            r = run([MEM, "secrets", "--base", "main"], root)                               # the branch against its base
            self.assertEqual(r.returncode, 1)
            self.assertIn("app.py:1: AWS access key id", r.stdout)

    def test_gate_warns_about_a_change_that_is_too_large(self):
        with tempfile.TemporaryDirectory() as t:
            py = sys.executable.replace("\\", "/")
            root = self._repo(t, {"commands": [f'"{py}" -c "print(1)"'], "max_changed_lines": 5})
            (root / "app.py").write_text("".join(f"x{i} = {i}\n" for i in range(12)), encoding="utf-8")
            r = run([MEM, "gate"], root, stdin="")
            self.assertEqual(r.returncode, 0, r.stdout)  # a warning: a person decides
            self.assertIn("gate WARNING: the change has 13 lines in 1 files (limit 5): split it", r.stdout)

    def test_provenance_trailer_is_off_until_set_and_then_checked(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertIn("provenance: off", run([MEM, "provenance"], root).stdout)
            self.assertEqual(run([MEM, "provenance", "--check", "main"], root).returncode, 0)
            self.assertEqual(run([MEM, "provenance", "--set", "no colon here"], root).returncode, 2)
            self.assertEqual(run([MEM, "provenance", "--set", "Assisted-by: AI coding agent"], root).returncode, 0)
            self.assertEqual(run([MEM, "provenance"], root).stdout.strip(), "Assisted-by: AI coding agent")
            self._git(root, "checkout", "-q", "-b", "work")
            (root / "app.py").write_text("x = 2\n", encoding="utf-8")
            self._git(root, "commit", "-q", "-am", "change without the trailer")
            (root / "app.py").write_text("x = 3\n", encoding="utf-8")
            self._git(root, "commit", "-q", "-am", "change with it", "-m", "Assisted-by: AI coding agent")
            r = run([MEM, "provenance", "--check", "main"], root)
            self.assertEqual(r.returncode, 1)
            self.assertIn("change without the trailer", r.stdout)
            self.assertNotIn("change with it", r.stdout)
            self.assertIn("1 commit(s) since main without", r.stdout)
            self.assertEqual(run([MEM, "provenance", "--off"], root).returncode, 0)
            self.assertEqual(run([MEM, "provenance", "--check", "main"], root).returncode, 0)

    def test_audit_writes_the_run_log_with_a_checksum(self):
        import hashlib
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertEqual(run([MEM, "gate"], root, stdin="").returncode, 0)
            run([MEM, "triage"], root, stdin="Login is broken")
            r = run([MEM, "audit", "--out", "audit.jsonl"], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            body = (root / "audit.jsonl").read_bytes()
            events = [json.loads(l) for l in body.decode("utf-8").splitlines()]
            self.assertEqual(sorted({e["ev"] for e in events}), ["gate", "triage"])
            self.assertIn("sha256 " + hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest(), r.stdout)
            self.assertIn("gate:pass", r.stdout)

    def test_doctor_and_evaluator_cover_what_a_maintainer_checks(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertIn("the gate has no lint or type check command", run([MEM, "doctor"], root).stdout)
            (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": ["git --version", "ruff check ."]}), encoding="utf-8")
            self.assertNotIn("no lint or type check", run([MEM, "doctor"], root).stdout)
        evaluator = (PACK / "templates/.claude/agents/evaluator.md").read_text(encoding="utf-8")
        for text in ("Merge readiness", "MERGE-READY: YES", "a rule that the change breaks is a FAIL", "400 changed lines"):
            self.assertIn(text, evaluator)
        self.assertEqual(re.findall(r"^(\d+)\. ", evaluator, re.M), [str(i) for i in range(11)])  # steps 0 to 10, in order
        wf = (PACK / "templates/ci/agent-issue.yml").read_text(encoding="utf-8")
        self.assertIn("$MEMORY audit --out", wf)
        self.assertIn("actions/upload-artifact@", wf)


COMPLEX = """
def simple(x):
    return x + 1


def old_and_complex(a, b, c, d):
    if a:
        return 1
    if b:
        return 2
    if c:
        return 3
    if d and a or b:
        return 4
    for i in range(3):
        if i:
            return i
    return 0
"""


class MemoryAndComplexityTests(unittest.TestCase):
    """A smaller digest, lessons that a person confirms, and the complexity of the change."""

    def _git(self, root, *args):
        r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def _repo(self, t):
        root = Path(t)
        self._git(root, "init", "-q", "-b", "main")
        (root / "app.py").write_text(COMPLEX, encoding="utf-8")
        self.assertEqual(run([MEM, "init"], root).returncode, 0)
        self._git(root, "add", "-A")
        self._git(root, "commit", "-q", "-m", "base")
        return root

    def test_a_lesson_from_an_agent_enters_the_digest_only_after_a_person_confirms_it(self):
        human = {"AGENT_MEMORY_HUMAN": "1"}
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            rule = "Close the cursor before the function returns."
            r = run([MEM, "lesson", "add", "--key", "close-cursor", "--rule", rule], root, stdin="")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("after a person confirms it", r.stdout)
            digest = run([MEM, "start"], root, stdin="").stdout
            self.assertNotIn(rule, digest)
            self.assertIn("1 lesson(s) that an agent recorded wait for a person", digest)
            listed = run([MEM, "lesson", "list"], root, stdin="").stdout
            self.assertRegex(listed, r"close-cursor: .*\[not confirmed; by agent at [0-9a-f]{7,}\]")
            r = run([MEM, "lesson", "confirm", "--key", "close-cursor"], root, stdin="")
            self.assertEqual(r.returncode, 2)  # no terminal: an agent cannot confirm by habit
            self.assertIn("a person confirms a lesson", r.stderr)
            r = run([MEM, "lesson", "add", "--key", "other-rule", "--rule", "Name the unit in each log line.", "--by", "human"], root, stdin="")
            self.assertEqual(r.returncode, 2)
            self.assertEqual(run([MEM, "lesson", "confirm", "--key", "close-cursor"], root, stdin="", env=human).returncode, 0)
            digest = run([MEM, "start"], root, stdin="").stdout
            self.assertIn(rule, digest)
            self.assertNotIn("wait for a person", digest)
            r = run([MEM, "lesson", "add", "--key", "other-rule", "--rule", "Name the unit in each log line.", "--by", "human"], root, stdin="", env=human)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Name the unit in each log line.", run([MEM, "start"], root, stdin="").stdout)

    def test_a_lesson_from_before_origins_were_recorded_stays_in_the_digest(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            old = {"key": "old-rule", "kind": "mistake", "rule": "Keep the old rule visible.", "count": 1, "helpful": 0,
                   "harmful": 0, "seen": ["x"], "status": "active"}
            (root / ".agent-memory/lessons.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")
            self.assertIn("Keep the old rule visible.", run([MEM, "start"], root, stdin="").stdout)

    def test_the_digest_has_a_size_limit(self):
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            for i in range(30):
                run([MEM, "feature", "add", "--id", f"F-{i}", "--desc", "a feature with a long description " * 5, "--criterion", "c"], root)
            full = run([MEM, "start", "--max-chars", "0", "--features", "30"], root, stdin="").stdout
            self.assertNotIn("the digest was cut", full)
            self.assertGreater(len(full), 4000)
            cut = run([MEM, "start", "--max-chars", "1000", "--features", "30"], root, stdin="").stdout
            self.assertIn("the digest was cut at 1000 of", cut)
            self.assertLess(len(cut), 1700)
            self.assertIn("Ritual:", cut)  # the last line is kept
            default = run([MEM, "start", "--features", "30"], root, stdin="").stdout
            self.assertLess(len(default), 6800)

    def test_complexity_reports_only_what_the_change_made_worse(self):
        grown = COMPLEX + "\n\ndef new_and_complex(a, b, c):\n" + "".join(f"    if a == {i}:\n        return {i}\n" for i in range(7)) + "    return b or c\n"
        with tempfile.TemporaryDirectory() as t:
            root = self._repo(t)
            self.assertEqual(run([MEM, "complexity", "--max", "5"], root).returncode, 0)  # nothing changed
            (root / "app.py").write_text(grown, encoding="utf-8")
            (root / "extra.py").write_text("def tiny():\n    return 1\n", encoding="utf-8")
            r = run([MEM, "complexity", "--max", "5"], root)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("app.py: `new_and_complex` has complexity 9 (limit 5, new function)", r.stdout)
            self.assertNotIn("old_and_complex", r.stdout)  # over the limit before the change, and not worse
            self.assertNotIn("tiny", r.stdout)
            py = sys.executable.replace("\\", "/")
            (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": [f'"{py}" -c "print(1)"'], "max_complexity": 5}), encoding="utf-8")
            r = run([MEM, "gate"], root, stdin="")
            self.assertEqual(r.returncode, 0, r.stdout)  # a warning: a person decides
            self.assertIn("gate WARNING: app.py: `new_and_complex` has complexity 9", r.stdout)

    def test_python_profile_gate_has_the_size_and_complexity_limits(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
            self.assertEqual(run([INST, "project", root, "--no-upstream"], root).returncode, 0)
            gate = json.loads((root / ".agent-memory/gate.json").read_text(encoding="utf-8"))
            self.assertEqual((gate["max_complexity"], gate["max_changed_lines"]), (10, 400))


CASE_JUDGE = """
import os, subprocess, sys
here = sorted(os.listdir('.'))
assert 'cases.jsonl' not in here and 'hidden' not in here, here      # the labels are not in reach of the judge
assert os.path.isfile('.claude/agents/evaluator.md') and os.path.isdir('.agents/skills/evaluator'), here
diff = subprocess.run(['git', 'diff', 'HEAD'], capture_output=True, text=True).stdout
assert 'calc.py' in diff and '.claude' not in diff, diff              # only the work under review is in the diff
print('VERDICT: FAIL' if 'a - b' in open('calc.py').read() else 'VERDICT: PASS')
"""


class EvalsAndHardeningTests(unittest.TestCase):
    """The shipped calibration set, cases with their own repository, changed tests, CODEOWNERS and sandbox."""

    def _git(self, root, *args):
        r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_calibration_set_labels_match_the_hidden_tests(self):
        r = run([PACK / "evals/judge-cases/check_labels.py"], PACK)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("24 cases (12 wrong, 12 correct): 0 label(s) do not match", r.stdout)
        cases = [json.loads(l) for l in (PACK / "evals/judge-cases/cases.jsonl").read_text(encoding="utf-8").splitlines()]
        for c in cases:
            self.assertRegex(c["id"], r"^c\d\d$")                     # the id does not give the label away
            self.assertNotIn("wrong", c["patch"])
            self.assertNotIn("hidden", c["prompt"])
        installed = [p.name for p in (PACK / "skills").iterdir()] + [p.name for p in (PACK / "templates").iterdir()]
        self.assertNotIn("evals", installed)                          # the installer copies skills and templates only

    def test_judge_runs_a_case_with_its_own_repository_away_from_the_labels(self):
        with tempfile.TemporaryDirectory() as t:
            root, cases = Path(t) / "project", Path(t) / "caseset"
            root.mkdir()
            self._git(root, "init", "-q")
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none"], root).returncode, 0)
            self._git(root, "add", "-A")
            self._git(root, "commit", "-q", "-m", "init")
            (cases / "repos/calc").mkdir(parents=True)
            (cases / "hidden").mkdir()
            (cases / "repos/calc/calc.py").write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
            patch = "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return 0\n+    return a %s b\n"
            (cases / "good.diff").write_text(patch % "+", encoding="utf-8")
            (cases / "bad.diff").write_text(patch % "-", encoding="utf-8")
            (cases / "judge.py").write_text(CASE_JUDGE, encoding="utf-8")
            (cases / "cases.jsonl").write_text("\n".join(json.dumps(
                {"id": i, "label": label, "repo": "repos/calc", "patch": f"{name}.diff", "prompt": "Judge the change."})
                for i, label, name in (("c01", "correct", "good"), ("c02", "wrong", "bad"))) + "\n", encoding="utf-8")
            py = sys.executable.replace("\\", "/")
            r = run([EVAL, "judge", "--cases", cases / "cases.jsonl", "--judge-cmd", f'"{py}" "{(cases / "judge.py").as_posix()}"'], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("wrong work approved:    0/1", r.stdout)
            self.assertIn("correct work rejected:  0/1", r.stdout)
            leftovers = [p for p in Path(tempfile.gettempdir()).glob("skill-eval-case-*") if (p / "calc.py").exists()]
            self.assertEqual(leftovers, [])                           # each case repository is removed

    def test_gate_warns_when_the_change_rewrites_an_existing_test(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self._git(root, "init", "-q")
            (root / "tests").mkdir()
            (root / "tests/test_calc.py").write_text("def test_add():\n    assert 2 + 2 == 4\n", encoding="utf-8")
            self.assertEqual(run([MEM, "init"], root).returncode, 0)
            py = sys.executable.replace("\\", "/")
            (root / ".agent-memory/gate.json").write_text(json.dumps({"commands": [f'"{py}" -c "print(1)"']}), encoding="utf-8")
            self._git(root, "add", "-A")
            self._git(root, "commit", "-q", "-m", "base")
            (root / "tests/test_calc.py").write_text("def test_add():\n    assert 2 + 2 == 4\n\n\ndef test_more():\n    assert 1 + 1 == 2\n", encoding="utf-8")
            (root / "tests/test_new.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
            self.assertNotIn("existing test changed", run([MEM, "gate"], root, stdin="").stdout)   # new tests are normal work
            (root / "tests/test_calc.py").write_text("def test_add():\n    assert 2 + 2 == 5\n", encoding="utf-8")
            r = run([MEM, "gate"], root, stdin="")
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("gate WARNING: existing test changed: tests/test_calc.py (1 line(s) removed or replaced)", r.stdout)
            self.assertIn("Review risk: HIGH", run([MEM, "evidence"], root).stdout)

    def test_installer_adds_codeowners_and_sandbox_settings_on_request(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self._git(root, "init", "-q")
            (root / ".github").mkdir()
            (root / ".github/CODEOWNERS").write_text("*.md @docs-team\n", encoding="utf-8")
            base = [INST, "project", root, "--no-upstream", "--profile", "none"]
            self.assertNotEqual(run(base + ["--codeowners", "not an owner"], root).returncode, 0)
            r = run(base + ["--codeowners", "@acme/quality", "--with-sandbox"], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            owners = (root / ".github/CODEOWNERS").read_text(encoding="utf-8")
            self.assertIn("*.md @docs-team", owners)
            for path in ("/.agent-memory/gate.json", "/.claude/", "/.github/", "/tests/"):
                self.assertIn(f"{path} @acme/quality", owners)
            self.assertIn("branch protection", r.stdout)
            self.assertEqual(run(base + ["--codeowners", "@acme/quality"], root).returncode, 0)   # a second run adds no second block
            self.assertEqual((root / ".github/CODEOWNERS").read_text(encoding="utf-8").count("/tests/ @acme/quality"), 1)
            settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["permissions"]["deny"], ["Read(./.env)", "Read(./.env.*)", "Read(./secrets/**)"])
            self.assertIn("SessionStart", settings["hooks"])
            if os.name == "nt":
                self.assertNotIn("sandbox", settings)                 # no sandbox on native Windows
                self.assertIn("not written on Windows", r.stdout)
            else:
                self.assertEqual(settings["sandbox"], {"enabled": True, "failIfUnavailable": True})
            self.assertEqual(run([INST, "uninstall", root], root).returncode, 0)
            self.assertEqual((root / ".github/CODEOWNERS").read_text(encoding="utf-8"), "*.md @docs-team\n")

    def test_ci_template_audits_dependencies_with_a_pinned_tool(self):
        wf = (PACK / "templates/ci/quality-gate.yml").read_text(encoding="utf-8")
        self.assertIn("\n  audit:\n", wf)
        self.assertRegex(wf, r"pip-audit==\d+\.\d+\.\d+")
        self.assertIn("npm audit --audit-level=high", wf)
        self.assertNotIn("\t", wf)


class EvaluatorCopiesTests(unittest.TestCase):
    def test_antigravity_evaluator_has_the_same_steps_as_the_claude_code_one(self):
        steps = {}
        for name in ("templates/.claude/agents/evaluator.md", "templates/antigravity/agents/evaluator.md"):
            body = (PACK / name).read_text(encoding="utf-8").split("---\n", 2)[2]
            steps[name] = re.sub(r"(?m)^0\. .*\n", "", body)        # step 0 names where memory.py is: it differs by agent
        a, b = steps.values()
        self.assertEqual(a, b)
        self.assertIn("MERGE-READY", a)
        agy = (PACK / "templates/antigravity/agents/evaluator.md").read_text(encoding="utf-8")
        self.assertIn("~/.gemini/config/plugins/ai-quality-pack/skills/long-horizon/scripts/memory.py", agy)
        self.assertNotIn("UNVERIFIABLE", agy)


class ReleaseTests(unittest.TestCase):
    def test_one_version_in_the_manifests_the_readme_and_the_changelog(self):
        plugin = json.loads((PACK / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
        agy = json.loads((PACK / "templates/antigravity/plugin.json").read_text(encoding="utf-8"))["version"]
        changelog = re.search(r"(?m)^## (\d+\.\d+\.\d+) ", (PACK / "CHANGELOG.md").read_text(encoding="utf-8")).group(1)
        readme = re.search(r"Status: v(\d+\.\d+\.\d+)", (PACK / "README.md").read_text(encoding="utf-8")).group(1)
        self.assertEqual({plugin, agy, changelog, readme}, {plugin})
        self.assertNotIn("## Unreleased", (PACK / "CHANGELOG.md").read_text(encoding="utf-8").split(f"## {plugin} ")[0] + "x")

    def test_judge_reads_the_cost_from_a_json_list_of_events(self):
        events = [{"type": "system"}, {"type": "assistant", "message": {"content": "VERDICT: PASS"}},
                  {"type": "result", "result": "VERDICT: PASS", "total_cost_usd": 0.0125, "num_turns": 3}]
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            self.assertEqual(run([INST, "project", root, "--no-upstream", "--profile", "none"], root).returncode, 0)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "i"], cwd=root, check=True, capture_output=True)
            (root / "judge.py").write_text("print(%r)\n" % json.dumps(events), encoding="utf-8")
            (root / "cases.jsonl").write_text(json.dumps({"id": "a", "label": "correct", "prompt": "p"}) + "\n"
                                              + json.dumps({"id": "b", "label": "wrong", "prompt": "p"}) + "\n", encoding="utf-8")
            py = sys.executable.replace("\\", "/")
            r = run([EVAL, "judge", "--cases", "cases.jsonl", "--judge-cmd", f'"{py}" "{(root / "judge.py").as_posix()}"'], root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("cost:                   $0.03 for 2 of 2 runs", r.stdout)
            report = json.loads(sorted((root / ".agent-memory/evals/results").glob("*-judge.json"))[-1].read_text(encoding="utf-8"))
            self.assertEqual([row["cost_usd"] for row in report["rows"]], [0.0125, 0.0125])


if __name__ == "__main__":
    unittest.main()
