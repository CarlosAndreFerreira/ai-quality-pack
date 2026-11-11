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
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                self.assertEqual(p.wait(timeout=20), 0)  # stdin is still open: the command must not wait for it
                self.assertIn(b"<project-memory", p.stdout.read())
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
            self.assertIn("ok.flag", fail["failed"])

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
            self.assertIn("completion gate still failing", digest)
            self.assertIn("1 released with the gate still failing", run([MEM, "stats"], root).stdout)
            (root / "ok.flag").write_text("1", encoding="utf-8")
            run([MEM, "gate"], root, stdin="")
            self.assertNotIn("completion gate still failing", run([MEM, "start"], root, stdin="").stdout)

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


if __name__ == "__main__":
    unittest.main()
