#!/usr/bin/env python3
"""skill_eval.py — measure a skill change before accepting it (stdlib only, Python 3.9+).

Runs a headless coding agent on a small set of verifiable tasks, in throw-away git worktrees:
  baseline  = current skills
  candidate = a proposal's diff applied (`run`), or one skill removed (`ablate`)
A task passes when its `check` command exits 0.

Design sources:
  * GEPA / gskill: evaluate with vs without skills on verifiable repository tasks.
  * Google Research RRSI (regularised recursive self-improvement of harnesses): noise-adjusted
    acceptance floor, non-compensatory guards, cost-aware acceptance, held-out split, auditable
    edit history (falsified hypotheses are not re-proposed), leakage critic, pruning by ablation.
  * Prime Agent: guard against reward hacking (protected check files, tamper detection).

Commands: init | calibrate | run --proposal FILE | ablate --skill NAME | history
Task line (JSONL): {"id","prompt","check", "setup"?, "protect"?: [paths], "split"?: "evolve"|"holdout"}
Agent command template placeholders: {prompt} (shell-quoted), {prompt_file}, {workdir}.
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
import datetime as dt
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MEM = Path(os.environ.get("AGENT_MEMORY_DIR", ".agent-memory"))
EVALS = MEM / "evals"
TASKS = EVALS / "tasks.jsonl"
RESULTS = EVALS / "results"
NOISE = EVALS / "noise.json"
HISTORY = MEM / "skill-history.jsonl"
DIFF_RE = re.compile(r"```(?:diff|patch)\s*\n(.*?)```", re.S)
COST_TOLERANCE = 1.25  # candidate may be ≤25% slower without needing a gain

EXAMPLE = {
    "id": "T1",
    "prompt": "Add slugify(text) to src/app/text.py: lowercase, trim, join words with '-'. Follow the repo skills.",
    "check": "uv run pytest tests/test_text.py -q",
    "protect": ["tests/test_text.py"],
    "split": "evolve",
}


def q(arg: str) -> str:
    """Quote for the platform shell (POSIX sh vs Windows cmd)."""
    return subprocess.list2cmdline([arg]) if os.name == "nt" else shlex.quote(arg)


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def sh(cmd: str, cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), shell=True, capture_output=True, text=True, timeout=timeout)


def git(*args: str, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def repo_root() -> Path:
    top = git("rev-parse", "--show-toplevel").stdout.strip()
    if not top or not git("rev-parse", "HEAD").stdout.strip():
        die("run inside a git repository with at least one commit")
    return Path(top).resolve()


def load_tasks(path: Path) -> List[dict]:
    if not path.exists():
        die(f"{path} not found — run `skill_eval.py init` and write 3–10 verifiable tasks")
    tasks = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            t = json.loads(line)
        except json.JSONDecodeError:
            die(f"{path}:{n} is not valid JSON")
        if not t.get("id") or not t.get("prompt") or not t.get("check"):
            die(f"{path}:{n} needs id, prompt and check")
        t.setdefault("split", "evolve")
        t.setdefault("protect", [])
        tasks.append(t)
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        die("task ids must be unique")
    return tasks


def extract_diff(proposal: Path) -> str:
    if not proposal.exists():
        die(f"{proposal} not found")
    m = DIFF_RE.search(proposal.read_text(encoding="utf-8"))
    if not m:
        die(f"no ```diff block in {proposal}")
    d = m.group(1)
    return d if d.endswith("\n") else d + "\n"


def leakage(diff: str, tasks: List[dict]) -> List[str]:
    """Critic: a skill change must not embed task-specific answers, ids or check paths."""
    added = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    hits = []
    for t in tasks:
        needles = [t["id"]] if len(t["id"]) >= 4 else []
        needles += [p for p in t.get("protect", []) if p]
        needles += re.findall(r"[\w./-]+\.(?:py|ts|js|go|rs|json)", t["check"])
        for nd in needles:
            if nd and re.search(r"(?<![\w-])" + re.escape(nd) + r"(?![\w-])", added):
                hits.append(f"{t['id']}: diff mentions '{nd}'")
    return sorted(set(hits))


# ---------------------------------------------------------------- what the agent reported
TOKEN_KEYS = ("input_tokens", "output_tokens", "thinking_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "cache_read_tokens")
LOG_LIMIT = 200_000


def _text(x) -> str:
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")


def parse_usage(stdout: str) -> dict:
    """Tokens, cost and turns from an agent that prints a JSON result (e.g. `claude -p ... --output-format json`,
    or the last line of `stream-json`). Any other output gives {} and the run is costed by its duration."""
    lines = [l for l in stdout.strip().splitlines() if l.strip()]
    for cand in ([stdout.strip()] + lines[-1:]) if lines else []:
        try:
            d = json.loads(cand)
        except ValueError:
            continue
        if isinstance(d, list):  # a list of events: the result event is the last one with a cost or a turn count
            d = next((e for e in reversed(d) if isinstance(e, dict) and (e.get("type") == "result" or "total_cost_usd" in e)), None)
        if not isinstance(d, dict):
            continue
        out = {}
        if isinstance(d.get("total_cost_usd"), (int, float)):
            out["cost_usd"] = round(float(d["total_cost_usd"]), 4)
        u = d.get("usage")
        if isinstance(u, dict) and any(isinstance(u.get(k), int) for k in TOKEN_KEYS):
            out["tokens"] = sum(u[k] for k in TOKEN_KEYS if isinstance(u.get(k), int))
        if isinstance(d.get("num_turns"), int):
            out["turns"] = d["num_turns"]
        return out
    return {}


def new_logdir(kind: str) -> Path:
    d = RESULTS / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{kind}-transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- worktree runs
def prepare_worktree(repo: Path, skills_src: Path, mutate: Optional[Callable[[Path], None]]) -> Path:
    wt = Path(tempfile.mkdtemp(prefix="skill-eval-"))
    wt.rmdir()
    r = git("worktree", "add", "--detach", str(wt), "HEAD", cwd=repo)
    if r.returncode != 0:
        die(f"git worktree add failed: {r.stderr.strip()}")
    dst = wt / ".agents" / "skills"
    if dst.is_symlink():
        dst.unlink()
    elif dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(skills_src, dst, symlinks=False, ignore=shutil.ignore_patterns("__pycache__", ".backup"))
    link = wt / ".claude" / "skills"
    if not link.exists() and not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(os.path.join("..", ".agents", "skills"), link, target_is_directory=True)
        except (OSError, NotImplementedError):
            shutil.copytree(dst, link)
    if mutate:
        try:
            mutate(wt)
        except SystemExit:
            cleanup(repo, wt)
            raise
    return wt


def cleanup(repo: Path, wt: Path) -> None:
    git("worktree", "remove", "--force", str(wt), cwd=repo)
    shutil.rmtree(wt, ignore_errors=True)
    git("worktree", "prune", cwd=repo)


def apply_diff(diff: str) -> Callable[[Path], None]:
    def _m(wt: Path) -> None:
        pf = wt / ".skill-eval.patch"
        pf.write_text(diff, encoding="utf-8")
        r = subprocess.run(["git", "apply", "--whitespace=nowarn", str(pf)], cwd=str(wt), capture_output=True, text=True)
        pf.unlink()
        if r.returncode != 0:
            die(f"proposal diff does not apply: {r.stderr.strip()}")
    return _m


def remove_skill(name: str) -> Callable[[Path], None]:
    def _m(wt: Path) -> None:
        target = wt / ".agents" / "skills" / name
        if not target.is_dir():
            die(f"skill '{name}' not found")
        shutil.rmtree(target)
    return _m


def skills_used(stdout: str, names: List[str]) -> Optional[List[str]]:
    """Skills that the agent used in a run, from its transcript: a call of the Skill tool, or a tool call that names a
    file of the skill (it read SKILL.md or ran a script). None when the output has no tool calls to look at
    (an agent that prints only its answer): then the use of a skill is not observable."""
    events = []
    try:
        d = json.loads(stdout)
        events = d if isinstance(d, list) else [d]
    except ValueError:
        for line in stdout.splitlines():
            if line.startswith("{"):
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
    calls = []
    for e in events:
        content = (e.get("message") or {}).get("content") if isinstance(e, dict) else None
        for c in content if isinstance(content, list) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                calls.append((str(c.get("name") or ""), c.get("input") or {}))
    if not calls:
        return None
    used = set()
    for tool, args in calls:
        text = json.dumps(args, ensure_ascii=False).replace("\\\\", "/")
        for n in names:
            if (tool == "Skill" and str(args.get("skill") or "").split(":")[-1] == n) or re.search(rf"skills/{re.escape(n)}/", text):
                used.add(n)
    return sorted(used)


def activation(per_task: Dict[str, dict], variant: str, skill: str) -> Optional[tuple]:
    """(runs that used the skill, runs where the use is observable) for one variant; None when no run is observable."""
    runs = [r for v in per_task.values() for r in v.get(variant, []) if r.get("skills_used") is not None]
    return (sum(skill in r["skills_used"] for r in runs), len(runs)) if runs else None


def activation_note(per_task: Dict[str, dict], variant: str, skill: str) -> tuple:
    """(line for the report, True when the skill was never used). A result says nothing about a skill that did not run."""
    act = activation(per_task, variant, skill)
    if act is None:
        return (f"activation of `{skill}`: not observable (the agent command prints no tool calls; "
                "use an output format with the transcript, for example `--output-format stream-json --verbose`)"), False
    used, n = act
    return f"activation of `{skill}`: used in {used} of {n} runs ({variant})", used == 0


def run_once(repo: Path, skills: Path, mutate, task: dict, agent_cmd: str, timeout: int,
             log: Optional[Path] = None) -> dict:
    wt = prepare_worktree(repo, skills, mutate)
    t0 = time.time()
    try:
        if task.get("setup"):
            sh(task["setup"], wt, timeout)
        pfile = wt / ".skill-eval-prompt.txt"
        pfile.write_text(task["prompt"], encoding="utf-8")
        cmd = agent_cmd.format(prompt=q(task["prompt"]), prompt_file=q(str(pfile)), workdir=q(str(wt)))
        try:
            r = sh(cmd, wt, timeout)
            agent_rc, stdout, stderr = r.returncode, r.stdout or "", r.stderr or ""
        except subprocess.TimeoutExpired as e:
            agent_rc, stdout, stderr = "timeout", _text(e.stdout), _text(e.stderr)
        usage = parse_usage(stdout)
        seen = skills_used(stdout, sorted(p.name for p in skills.iterdir() if p.is_dir()))
        if seen is not None:
            usage["skills_used"] = seen
        if log:  # the transcript explains a verdict; results/ is git-ignored
            try:
                log.write_text(f"$ {cmd}\nexit: {agent_rc}\n--- stdout ---\n{stdout[-LOG_LIMIT:]}\n--- stderr ---\n{stderr[-LOG_LIMIT:]}\n",
                               encoding="utf-8")
            except OSError:
                pass
        agent_seconds = round(time.time() - t0, 1)
        # reward-hacking guard: the agent must not change the files that judge it
        tampered = []
        for p in task.get("protect", []):
            if git("diff", "--quiet", "HEAD", "--", p, cwd=wt).returncode != 0 or not (wt / p).exists():
                tampered.append(p)
            git("checkout", "HEAD", "--", p, cwd=wt)
        try:
            passed = sh(task["check"], wt, timeout).returncode == 0
        except subprocess.TimeoutExpired:
            passed = False
        if tampered:
            passed = False
        return {"passed": passed, "agent_rc": agent_rc, "seconds": agent_seconds, "tampered": tampered, **usage,
                **({"transcript": log.name} if log else {})}
    finally:
        cleanup(repo, wt)


def measure(repo, skills, tasks, agent_cmd, repeats, timeout, variants, logdir: Optional[Path] = None) -> Dict[str, dict]:
    per_task: Dict[str, dict] = {}
    for t in tasks:
        res = {name: [] for name, _ in variants}
        for i in range(repeats):
            for name, mutate in variants:
                log = logdir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', t['id'])}-{name}-{i + 1}.log" if logdir else None
                r = run_once(repo, skills, mutate, t, agent_cmd, timeout, log)
                res[name].append(r)
                flag = " TAMPERED " + ",".join(r["tampered"]) if r["tampered"] else ""
                spent = (f"  {r['tokens']} tok" if "tokens" in r else "") + (f"  ${r['cost_usd']}" if "cost_usd" in r else "")
                print(f"  {t['id']:<8} [{t['split']:<7}] {name:<9} {'PASS' if r['passed'] else 'fail'}  {r['seconds']}s{spent}{flag}")
        per_task[t["id"]] = {"split": t["split"], **res}
    return per_task


# ---------------------------------------------------------------- statistics
def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def wilson(passed: int, n: int, z: float = 1.96) -> list:
    if n == 0:
        return [0.0, 0.0]
    p, d = passed / n, 1 + z * z / n
    c, r = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - r) / d, 2), round((c + r) / d, 2)]


# two-sided 95% Student t for 1..29 degrees of freedom (above that, the normal 1.96)
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
       2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045]


def paired_ci(diffs: List[float]) -> Optional[list]:
    """95% interval of the mean per-task difference (candidate - baseline). Tasks are the sample: the same
    task runs under both variants, so the difference removes how hard each task is (Miller 2024)."""
    n = len(diffs)
    if n < 2:
        return None
    m = sum(diffs) / n
    se = math.sqrt(sum((d - m) ** 2 for d in diffs) / (n - 1) / n)
    t = T95[n - 2] if n - 1 <= len(T95) else 1.96
    return [round(m - t * se, 3), round(m + t * se, 3)]


def pass_all(rows: Dict[str, dict], name: str) -> float:
    """pass^k with k = the repeats: the share of tasks where every run passed. A variant that passes
    2 of 3 runs on each task has a 67% pass rate and a pass^3 of 0."""
    return round(sum(all(r["passed"] for r in v[name]) for v in rows.values()) / len(rows), 3)


def reliability_line(name: str, x: dict, basis: str, repeats: int) -> str:
    """One line to quote: how reliable, with its interval, and what one passed run costs."""
    per = x.get("per_pass")
    unit = {"cost_usd": f"${per:.4f}", "tokens": f"{per:,.0f} tokens", "seconds": f"{per:.0f} s"}[basis] if per is not None else ""
    low, high = x["pass_all_ci95"]
    runs = "the run" if repeats == 1 else f"each of {repeats} runs"
    return (f"{name}: {runs} passed on {x['pass_all']:.0%} of the tasks (95% CI {low:.0%} to {high:.0%}); "
            + (f"{unit} for each passed run" if unit else "no run passed, thus no cost for each passed run"))


def rate(runs: List[dict]) -> float:
    return sum(r["passed"] for r in runs) / len(runs) if runs else 0.0


def summarise(per_task: Dict[str, dict], a: str, b: str) -> dict:
    out = {}
    for split in ("evolve", "holdout"):
        rows = {k: v for k, v in per_task.items() if v["split"] == split}
        if not rows:
            continue
        ap = sum(sum(r["passed"] for r in v[a]) for v in rows.values())
        bp = sum(sum(r["passed"] for r in v[b]) for v in rows.values())
        n = sum(len(v[a]) for v in rows.values())
        wins = sum(rate(v[b]) > rate(v[a]) for v in rows.values())
        losses = sum(rate(v[b]) < rate(v[a]) for v in rows.values())
        hard_losses = [k for k, v in rows.items() if rate(v[a]) == 1.0 and rate(v[b]) < 1.0]
        tampered = [k for k, v in rows.items() if any(r["tampered"] for r in v[b])]

        def total(key: str, name: str) -> Optional[float]:
            vals = [r.get(key) for v in rows.values() for r in v[name]]
            return sum(vals) if vals and all(isinstance(x, (int, float)) for x in vals) else None

        # cost basis: money, else tokens, when every run of both variants reported it; else wall-clock time
        basis = next((k for k in ("cost_usd", "tokens") if total(k, a) and total(k, b) is not None), "seconds")
        spent = {name: {k: round(total(k, name), 4) for k in ("cost_usd", "tokens") if total(k, name) is not None} for name in (a, b)}

        def reliability(name: str, passed: int) -> dict:
            """pass^k with its interval (the unit is the task), and the total spend divided by the runs that passed."""
            solid = sum(all(r["passed"] for r in v[name]) for v in rows.values())
            return {"pass_all": pass_all(rows, name), "pass_all_ci95": wilson(solid, len(rows)),
                    "per_pass": round(total(basis, name) / passed, 4) if passed else None}

        out[split] = {
            a: {"passed": ap, "runs": n, "rate": round(ap / n, 3), "ci95": wilson(ap, n), **reliability(a, ap), **spent[a]},
            b: {"passed": bp, "runs": n, "rate": round(bp / n, 3), "ci95": wilson(bp, n), **reliability(b, bp), **spent[b]},
            "delta": round((bp - ap) / n, 3), "tasks": len(rows),
            "delta_ci95": paired_ci([rate(v[b]) - rate(v[a]) for v in rows.values()]), "tasks_better": wins, "tasks_worse": losses,
            "sign_test_p": round(sign_test(wins, losses), 3), "hard_losses": hard_losses,
            "tampered": tampered, "cost_ratio": round(total(basis, b) / (total(basis, a) or 1e-9), 2), "cost_basis": basis,
        }
    return out


def task_signal(per_task: Dict[str, dict], a: str, b: str) -> dict:
    """Which tasks can show a difference between the two variants. A task at the ceiling (each run of the two
    variants passed) cannot show a gain. A task at the floor (each run failed) cannot show a loss."""
    out = {"ceiling": [], "floor": [], "mixed": []}
    for k, v in per_task.items():
        runs = [r["passed"] for name in (a, b) for r in v[name]]
        out["ceiling" if all(runs) else "floor" if not any(runs) else "mixed"].append(k)
    return out


def signal_line(sig: dict) -> str:
    n = sum(len(x) for x in sig.values())
    return (f"task signal: {len(sig['mixed'])} of {n} tasks had a failed run and a passed run; "
            f"{len(sig['ceiling'])} at the ceiling (each run passed), {len(sig['floor'])} at the floor (each run failed)")


def signal_guard(per_task: Dict[str, dict], a: str, b: str, v: str, reasons: List[str], mode: str) -> tuple:
    """A task set that cannot show the effect is not evidence of no effect. Returns (verdict, reasons, signal)."""
    sig = task_signal(per_task, a, b)
    reasons.append(signal_line(sig))
    n = len(per_task)
    if v.startswith("REGRESSES"):
        return v, reasons, sig
    if len(sig["floor"]) == n:  # `run` keeps its own name for "no measured gain"; an ablation must not say PRUNABLE
        return "NO-SIGNAL" if mode == "ablate" else "INCONCLUSIVE", reasons + ["each run of each task failed in the two variants: these tasks cannot show a "
                                       "difference. Use tasks that the agent can do"], sig
    if len(sig["ceiling"]) == n:
        if mode == "ablate":  # true for these tasks, and no more than that
            reasons.append("each run of each task passed with and without the skill: these tasks do not need the skill. "
                           "The result is for these tasks only; a task that the agent fails without the skill would show its value")
        else:
            v = "INCONCLUSIVE"
            reasons.append("the baseline passed each run of each task: this task set cannot show a gain. Add tasks that "
                           "the baseline fails in a part of its runs")
    return v, reasons, sig


def provenance(repo: Path) -> dict:
    """The commit that the runs used. The worktree of a run is HEAD plus the skills folder as it is on disk, so
    uncommitted changes outside the skills folder are not in the measurement."""
    head = git("rev-parse", "--short=12", "HEAD", cwd=repo)
    if head.returncode != 0 or not head.stdout.strip():
        die("cannot read the commit of this repository: a report without it cannot be compared with another")
    status = git("status", "--porcelain", "--untracked-files=no", cwd=repo)
    return {"commit": head.stdout.strip(), "dirty": bool(status.stdout.strip()),
            "python": "%d.%d" % sys.version_info[:2], "platform": sys.platform}


def verdict(s: dict, noise: float, mode: str) -> tuple:
    ev = s.get("evolve") or s.get("holdout")
    reasons = []
    # non-compensatory guards: block regardless of headline gain
    for split, v in s.items():
        if v["hard_losses"]:
            reasons.append(f"{split}: candidate failed task(s) the baseline always passed: {', '.join(v['hard_losses'])}")
        if v["tampered"]:
            reasons.append(f"{split}: candidate tampered with protected files in {', '.join(v['tampered'])}")
    ho = s.get("holdout")
    if ho and ho["delta"] < -noise:
        reasons.append(f"holdout dropped by {ho['delta']:+.0%} (beyond noise ±{noise:.0%})")
    if reasons:
        return "REGRESSES", reasons
    if mode == "ablate":  # candidate = without the skill
        if ev["delta"] >= -noise:
            return "PRUNABLE", [f"removing the skill changed pass rate by {ev['delta']:+.0%} (within noise ±{noise:.0%})"]
        return "KEEP", [f"removing the skill dropped pass rate by {ev['delta']:+.0%}"]
    if ev["delta"] <= noise:
        return "INCONCLUSIVE", [f"gain {ev['delta']:+.0%} is within the noise band ±{noise:.0%}"]
    if ev["cost_ratio"] > COST_TOLERANCE and ev["delta"] < 2 * noise:
        return "INCONCLUSIVE", [f"gain {ev['delta']:+.0%} does not justify {ev['cost_ratio']}× cost ({ev['cost_basis']})"]
    strength = "" if ev["sign_test_p"] <= 0.1 else " (weak evidence)"
    return "IMPROVES" + strength, [f"gain {ev['delta']:+.0%} > noise ±{noise:.0%}; sign test p={ev['sign_test_p']}"]


def noise_band(default: float) -> float:
    if NOISE.exists():
        try:
            return max(default, float(json.loads(NOISE.read_text(encoding="utf-8")).get("band", default)))
        except (ValueError, json.JSONDecodeError):
            print(f"warn: {NOISE} unreadable; using default band", file=sys.stderr)
    return default


def append_history(rec: dict) -> None:
    MEM.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def common_setup(a):
    repo = repo_root()
    agent_cmd = a.agent_cmd or os.environ.get("SKILL_EVAL_AGENT_CMD")
    if not agent_cmd:
        die("set --agent-cmd or SKILL_EVAL_AGENT_CMD, e.g. 'claude -p {prompt}'")
    skills = (repo / a.skills).resolve()
    if not skills.is_dir():
        die(f"skills dir {skills} not found")
    tasks = load_tasks(Path(a.tasks))
    runs = 2 * a.repeats * len(tasks)
    if runs > a.max_runs and not a.yes:
        die(f"{runs} agent runs planned (> --max-runs {a.max_runs}); this costs tokens. Re-run with --yes to confirm.")
    return repo, agent_cmd, skills, tasks, runs


def report(kind, label, s, v, reasons, noise, per_task, a, agent_cmd, extra=None) -> Path:
    rec = {"kind": kind, "subject": label, "date": dt.datetime.now().isoformat(timespec="seconds"),
           "agent_cmd": agent_cmd, "repeats": a.repeats, "noise_band": noise, "verdict": v, "reasons": reasons,
           "summary": s, "per_task": per_task, **provenance(repo_root()), **(extra or {})}
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{kind}-{re.sub(r'[^A-Za-z0-9_.-]', '_', Path(label).stem)}.json"
    out.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    for split, x in s.items():
        names = [k for k in x if isinstance(x[k], dict)]
        b, c = x[names[0]], x[names[1]]
        print(f"\n[{split}] {names[0]} {b['passed']}/{b['runs']} ({b['rate']:.0%}, CI {b['ci95']}) → "
              f"{names[1]} {c['passed']}/{c['runs']} ({c['rate']:.0%}, CI {c['ci95']}); Δ {x['delta']:+.0%}"
              + (f" (95% CI {x['delta_ci95'][0]:+.0%} to {x['delta_ci95'][1]:+.0%}, {x['tasks']} tasks, paired)" if x.get("delta_ci95") else "")
              + f"; every run passed: {b['pass_all']:.0%} → {c['pass_all']:.0%} of tasks; "
              f"tasks +{x['tasks_better']}/-{x['tasks_worse']}; p={x['sign_test_p']}; cost ×{x['cost_ratio']} ({x['cost_basis']})")
        for name in names[:2]:
            print(f"  reliability at cost, {reliability_line(name, x[name], x['cost_basis'], a.repeats)}")
    if rec["dirty"]:
        print(f"\nnote: commit {rec['commit']} has uncommitted changes. A run uses the commit and the skills folder on disk; "
              "other uncommitted changes are not in this measurement")
    print(f"\nVERDICT: {v}\n  - " + "\n  - ".join(reasons) + f"\nreport: {out.as_posix()}"
          + (f"\ntranscripts: {extra['transcripts']}" if extra and extra.get("transcripts") else ""))
    return out


# ---------------------------------------------------------------- commands
def cmd_init(a) -> None:
    EVALS.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(exist_ok=True)
    if TASKS.exists():
        print(f"exists: {TASKS}")
    else:
        TASKS.write_text(json.dumps(EXAMPLE) + "\n", encoding="utf-8")
        print(f"created {TASKS} — replace the example with 3–10 real tasks (mark ~1/3 as \"split\": \"holdout\")")


def cmd_calibrate(a) -> None:
    """A/A run: baseline vs baseline. The disagreement rate estimates evaluation noise."""
    repo, agent_cmd, skills, tasks, _ = common_setup(a)
    logdir = new_logdir("calibrate")
    per_task = measure(repo, skills, tasks, agent_cmd, a.repeats, a.timeout, [("baseline", None), ("replica", None)], logdir)
    deltas = [abs(rate(v["baseline"]) - rate(v["replica"])) for v in per_task.values()]
    band = round(max(a.min_band, sum(deltas) / len(deltas)), 3)
    sig = task_signal(per_task, "baseline", "replica")
    EVALS.mkdir(parents=True, exist_ok=True)
    NOISE.write_text(json.dumps({"band": band, "date": dt.datetime.now().isoformat(timespec="seconds"),
                                 "repeats": a.repeats, "tasks": len(tasks), "agent_cmd": agent_cmd,
                                 "task_signal": sig, **provenance(repo)}, indent=2), encoding="utf-8")
    print(f"noise band = ±{band:.0%} (mean A/A disagreement per task, floor {a.min_band:.0%}) → {NOISE}")
    print(signal_line(sig))
    if len(sig["ceiling"]) == len(per_task):
        print("warn: each run of each task passed. A change of a skill cannot show a gain on these tasks: add tasks "
              "that the agent fails in a part of its runs")
    elif len(sig["floor"]) == len(per_task):
        print("warn: each run of each task failed. These tasks cannot show a difference: use tasks that the agent can do")


def cmd_run(a) -> None:
    proposal = Path(a.proposal)
    diff = extract_diff(proposal)
    repo, agent_cmd, skills, tasks, runs = common_setup(a)
    leaks = leakage(diff, tasks)
    if leaks and not a.allow_leak:
        die("leakage critic: the proposal mentions task-specific material (overfitting risk):\n  " + "\n  ".join(leaks) +
            "\nRewrite the skill change in general terms, or pass --allow-leak if this is intended.", 6)
    noise = noise_band(a.min_band)
    print(f"measuring {proposal.name}: {len(tasks)} tasks × {a.repeats} repeats × 2 = {runs} runs; noise band ±{noise:.0%}"
          + ("" if NOISE.exists() else " (default — run `calibrate` for a measured band)"))
    logdir = new_logdir("proposal")
    per_task = measure(repo, skills, tasks, agent_cmd, a.repeats, a.timeout, [("baseline", None), ("candidate", apply_diff(diff))], logdir)
    s = summarise(per_task, "baseline", "candidate")
    v, reasons = verdict(s, noise, "run")
    v, reasons, sig = signal_guard(per_task, "baseline", "candidate", v, reasons, "run")
    m = re.search(r"\.agents/skills/([\w-]+)/", diff)
    extra = {"transcripts": logdir.as_posix(), "task_signal": sig}
    if a.max_cost_per_pass is not None and v.startswith("IMPROVES"):  # a limit that a person set: a gain above it is not a gain
        ev = s.get("evolve") or s.get("holdout")
        per = ev["candidate"]["per_pass"]
        if ev["cost_basis"] != "cost_usd":
            v = "INCONCLUSIVE"
            reasons.append("--max-cost-per-pass could not be checked: the agent command did not report a cost for each run")
        elif per is None or per > a.max_cost_per_pass:
            v = "INCONCLUSIVE"
            reasons.append(f"the candidate costs ${per:.4f} for each passed run, above the limit of ${a.max_cost_per_pass:.4f}")
    if m:  # a change of a skill that the agent did not use cannot be the cause of the result
        note, never = activation_note(per_task, "candidate", m.group(1))
        extra["activation"] = note
        reasons.append(note)
        if never and not v.startswith("REGRESSES"):
            v = "INCONCLUSIVE"
            reasons.append("the agent never used the skill in the candidate runs: the difference is not an effect of the change")
    out = report("proposal", str(proposal), s, v, reasons, noise, per_task, a, agent_cmd, extra)
    hyp = re.search(r"^Change:\s*(.+)$", proposal.read_text(encoding="utf-8"), re.M)
    append_history({"date": dt.date.today().isoformat(), "skill": m.group(1) if m else "", "proposal": proposal.name,
                    "hypothesis": hyp.group(1).strip() if hyp else "", "verdict": v,
                    "delta": (s.get("evolve") or s.get("holdout"))["delta"],
                    "cost_ratio": (s.get("evolve") or s.get("holdout"))["cost_ratio"], "report": out.as_posix(),
                    "decision": "pending-user"})
    if a.annotate:
        with proposal.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## Measurement ({dt.date.today()})\nVerdict: **{v}** — " + "; ".join(reasons) + f"\nReport: `{out.as_posix()}`\n")
    sys.exit(0 if v.startswith("IMPROVES") else 1)


def cmd_ablate(a) -> None:
    repo, agent_cmd, skills, tasks, runs = common_setup(a)
    if (skills / a.skill / ".upstream").exists():
        print("note: upstream skill — pruning means uninstalling it, not editing it")
    noise = noise_band(a.min_band)
    print(f"ablating {a.skill}: {len(tasks)} tasks × {a.repeats} repeats × 2 = {runs} runs; noise band ±{noise:.0%}")
    logdir = new_logdir("ablation")
    per_task = measure(repo, skills, tasks, agent_cmd, a.repeats, a.timeout, [("with", None), ("without", remove_skill(a.skill))], logdir)
    s = summarise(per_task, "with", "without")
    v, reasons = verdict(s, noise, "ablate")
    v, reasons, sig = signal_guard(per_task, "with", "without", v, reasons, "ablate")
    note, never = activation_note(per_task, "with", a.skill)
    reasons.append(note)
    if never:  # not "prunable because it has no effect": it never ran. The description may be the problem
        v = "NOT-USED"
        reasons.append("the agent never used the skill in the runs that had it: the comparison says nothing about what the skill "
                       "does. The agent chooses a skill from its description: improve the description, or remove the skill")
    out = report("ablation", a.skill, s, v, reasons, noise, per_task, a, agent_cmd, {"transcripts": logdir.as_posix(), "activation": note, "task_signal": sig})
    append_history({"date": dt.date.today().isoformat(), "skill": a.skill, "proposal": "ablation", "hypothesis": "skill still adds value",
                    "verdict": v, "delta": (s.get("evolve") or s.get("holdout"))["delta"], "report": out.as_posix(),
                    "decision": "pending-user"})
    sys.exit(0)


def cmd_history(a) -> None:
    if not HISTORY.exists():
        print("no skill history yet")
        return
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if a.skill and r.get("skill") != a.skill:
            continue
        print(f"{r['date']} {r.get('skill',''):<20} {r['verdict']:<26} Δ{r.get('delta',0):+.0%}  {r.get('decision','')}  — {r.get('hypothesis','')}")


VERDICT_RE = re.compile(r"VERDICT:\s*(PASS|FAIL|UNKNOWN)\b", re.I)


def mcc(tp: int, tn: int, fp: int, fn: int) -> Optional[float]:
    """Matthews correlation: one number for a judge that must both catch wrong work and accept correct work."""
    d = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return round((tp * tn - fp * fn) / d, 2) if d else None


def aggregate_case_verdicts(verdicts: List[str], rule: str = "asymmetric") -> str:
    """Combine repeat judge verdicts for one case. Under `asymmetric`, PASS requires all runs to agree."""
    k = len(verdicts)
    if k == 0:
        return "UNKNOWN"
    if k == 1:
        return verdicts[0] if verdicts[0] in ("PASS", "FAIL") else "UNKNOWN"
    n_pass = sum(1 for v in verdicts if v == "PASS")
    n_fail = sum(1 for v in verdicts if v == "FAIL")
    if rule == "majority":
        if n_pass > k / 2:
            return "PASS"
        if n_fail > k / 2:
            return "FAIL"
        return "UNKNOWN"
    if rule == "strict-fail":
        if n_fail >= 1:
            return "FAIL"
        return "PASS" if n_pass == k else "UNKNOWN"
    if n_pass == k:
        return "PASS"
    if n_fail >= (k // 2) + 1:
        return "FAIL"
    return "UNKNOWN"


def judge_agreement(per_case: List[dict]) -> Tuple[Optional[float], Optional[float]]:
    """Return (case_unanimity_rate, pairwise_fleiss_kappa) across multi-run cases."""
    multi = [c["verdicts"] for c in per_case if len(c.get("verdicts", [])) >= 2]
    if not multi:
        return None, None
    unanimity = round(sum(1 for vs in multi if len(set(vs)) == 1) / len(multi), 4)
    labels = ("PASS", "FAIL", "UNKNOWN")
    counts_global = {l: 0 for l in labels}
    total_ratings, total_pairs, agree_pairs = 0, 0, 0
    for vs in multi:
        k = len(vs)
        total_ratings += k
        total_pairs += k * (k - 1)
        by_lbl = {l: 0 for l in labels}
        for raw in vs:
            lbl = raw if raw in ("PASS", "FAIL") else "UNKNOWN"
            by_lbl[lbl] += 1
            counts_global[lbl] += 1
        agree_pairs += sum(c * (c - 1) for c in by_lbl.values())
    if total_pairs == 0 or total_ratings == 0:
        return unanimity, None
    p_o = agree_pairs / total_pairs
    p_e = sum((n / total_ratings) ** 2 for n in counts_global.values())
    kappa = (1.0 if p_o == 1.0 else 0.0) if (1.0 - p_e) <= 1e-12 else round((p_o - p_e) / (1.0 - p_e), 3)
    return unanimity, kappa


def judge_summary(rows: List[dict]) -> dict:
    """rows: {"label": "correct"|"wrong", "verdict": "PASS"|"FAIL"|"UNKNOWN"}. A wrong case is the positive."""
    n = lambda label, verdict: sum(r["label"] == label and r["verdict"] == verdict for r in rows)
    tp, fn, tn, fp = n("wrong", "FAIL"), n("wrong", "PASS"), n("correct", "PASS"), n("correct", "FAIL")
    wrong, correct = [r for r in rows if r["label"] == "wrong"], [r for r in rows if r["label"] == "correct"]
    unknown = sum(r["verdict"] == "UNKNOWN" for r in rows)
    wrong_rejected = len(wrong) - fn  # matches docs/RESULTS.md: FAIL or UNKNOWN counts as not accepted
    bal_acc = round(((tn / len(correct)) + (wrong_rejected / len(wrong))) / 2, 3) if wrong and correct else None
    return {
        "runs": len(rows), "wrong": len(wrong), "correct": len(correct),
        # the number that matters most: wrong work that the judge let pass
        "wrong_approved": fn, "wrong_approved_rate": round(fn / len(wrong), 3) if wrong else None,
        "wrong_approved_ci95": wilson(fn, len(wrong)) if wrong else None,
        "correct_rejected": fp, "correct_rejected_rate": round(fp / len(correct), 3) if correct else None,
        "correct_rejected_ci95": wilson(fp, len(correct)) if correct else None,
        "unknown": unknown, "unknown_rate": round(unknown / len(rows), 3) if rows else None,
        "balanced_accuracy": bal_acc,
        "mcc_decided": mcc(tp, tn, fp, fn),
    }


DIFF_LIMIT = 60_000
CONTEXT_LIMIT = 40_000
REQ_TAG_RE = re.compile(r"<requirement>\s*(.*?)\s*</requirement>", re.S)
REQ_PATH_RE = re.compile(r"[\w./-]+\.(?:md|txt|py|ts|js|go|rs|json|toml|yaml|yml)")
TEST_FILE_RE = re.compile(r"(?:^|/)(?:tests?|__tests__)/|(?:^|/)test_[^/]+\.py$|_test\.(?:py|go|rs)$")


def extract_requirement(prompt: str) -> str:
    m = REQ_TAG_RE.search(prompt)
    return m.group(1).strip() if m else prompt.strip()


def collect_base_context(wt: Path, req: str, max_chars: int = CONTEXT_LIMIT) -> str:
    """Read referenced spec files and modified non-test files from HEAD (tamper-safe base context)."""
    req_paths = REQ_PATH_RE.findall(req)
    diff_files = [l.strip() for l in git("diff", "--name-only", "HEAD", cwd=wt).stdout.splitlines() if l.strip()]
    candidates: List[str] = []
    seen = set()
    for p in req_paths:
        if p not in seen:
            seen.add(p)
            candidates.append(p)
    for p in diff_files:
        if p not in seen and not (TEST_FILE_RE.search(p) and p not in req_paths):
            seen.add(p)
            candidates.append(p)
    blocks: List[str] = []
    used = 0
    for p in candidates:
        r = git("show", f"HEAD:{p}", cwd=wt)
        if r.returncode != 0 or not r.stdout:
            continue
        header = f"### {p} (base)\n"
        chunk = header + r.stdout.rstrip() + "\n"
        if used + len(chunk) > max_chars:
            rem = max_chars - used
            if rem > len(header) + 100:
                blocks.append(chunk[:rem] + "\n... [context truncated]\n")
            break
        blocks.append(chunk)
        used += len(chunk)
    return "\n".join(blocks)


def clean_diff_for_review(wt: Path) -> str:
    mem_script = wt / ".agents" / "skills" / "long-horizon" / "scripts" / "memory.py"
    text = ""
    if mem_script.is_file():
        r = subprocess.run([sys.executable, str(mem_script), "diff-view", "--base", "HEAD"],
                           cwd=str(wt), capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            text = r.stdout
    if not text:
        r = git("diff", "HEAD", cwd=wt)
        text = r.stdout if r.returncode == 0 else ""
    if not text.strip():
        st = git("status", "--short", cwd=wt).stdout.strip()
        text = f"(empty git diff HEAD; working tree status:\n{st})" if st else "(empty diff)"
    if len(text) > DIFF_LIMIT:
        text = text[:DIFF_LIMIT] + "\n... [diff truncated]\n"
    return text


def build_plain_prompt(req: str, diff_text: str, two_stage: bool, context_text: str = "") -> str:
    ctx_block = f"<context>\n{context_text.rstrip()}\n</context>\n\n" if context_text.strip() else ""
    base = (
        "You are an independent code reviewer. Read only the requirement, base context (if given), and diff below.\n"
        "Do NOT run commands, edit files, or use tools. Decide whether the diff solves the requirement "
        "correctly without breaking existing behaviour.\n"
        "For any suspected defect, quote the exact sentence of the requirement it violates.\n"
        "List at most 3 ambiguities if the requirement leaves behaviour undecided.\n\n"
        f"<requirement>\n{req}\n</requirement>\n\n"
        f"{ctx_block}"
        f"<diff>\n{diff_text.rstrip()}\n</diff>\n\n"
    )
    if two_stage:
        return base + (
            "Output a fenced JSON block with keys:\n"
            '  "decision": "APPROVE" | "SUSPECT"\n'
            '  "hypotheses": up to 3 objects {"requirement_quote": "...", "suspected_defect": "...", "repro_idea": "..."}\n'
            '  "ambiguities": up to 3 short strings\n'
            "Then end with one final line:\n"
            "VERDICT: PASS   (when decision is APPROVE)\n"
            "VERDICT: FAIL   (when decision is SUSPECT)\n"
        )
    return base + (
        "State concise findings (if any) and end with one final line, nothing after it:\n"
        "VERDICT: PASS | VERDICT: FAIL | VERDICT: UNKNOWN\n"
    )


def _extract_result_text(stdout: str) -> str:
    s = stdout.strip()
    if s.startswith(("{", "[")):
        try:
            d = json.loads(s)
            if isinstance(d, list):
                d = next((e for e in reversed(d) if isinstance(e, dict) and isinstance(e.get("result") or e.get("response"), str)), None)
            if isinstance(d, dict):
                txt = d.get("result") if isinstance(d.get("result"), str) else d.get("response")
                if isinstance(txt, str):
                    return txt
        except ValueError:
            pass
    return stdout


def parse_stage1(stdout: str) -> Tuple[str, List[dict], List[str]]:
    text = _extract_result_text(stdout)
    candidates: List[dict] = []
    for m in re.finditer(r"```(?:json)?\s*\n(.*?)```", text, re.S):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "decision" in obj:
                candidates.append(obj)
        except ValueError:
            pass
    if not candidates:
        dec = json.JSONDecoder()
        for i, ch in enumerate(text):
            if ch == "{":
                try:
                    obj, _ = dec.raw_decode(text[i:])
                    if isinstance(obj, dict) and "decision" in obj:
                        candidates.append(obj)
                except ValueError:
                    pass
    for obj in reversed(candidates):
        decision = str(obj.get("decision") or "").strip().upper()
        if decision in ("APPROVE", "SUSPECT"):
            hyps = [h for h in (obj.get("hypotheses") or []) if isinstance(h, dict)][:3]
            ambs = [str(x) for x in (obj.get("ambiguities") or []) if x][:3]
            return decision, hyps, ambs
    found = VERDICT_RE.findall(text)
    if found:
        v = found[-1].upper()
        return ("APPROVE" if v == "PASS" else ("SUSPECT" if v == "FAIL" else "UNKNOWN")), [], []
    return "UNKNOWN", [], []


def build_verify_prompt(req: str, hypotheses: List[dict], stage1_stdout: str) -> str:
    if hypotheses:
        lines = []
        for idx, h in enumerate(hypotheses, 1):
            q_txt = str(h.get("requirement_quote") or "").strip()
            d_txt = str(h.get("suspected_defect") or "").strip()
            r_txt = str(h.get("repro_idea") or "").strip()
            lines.append(f"{idx}. Defect: {d_txt}\n   Requirement: {q_txt}\n   Check idea: {r_txt}")
        suspect_block = "\n".join(lines)
    else:
        suspect_block = _extract_result_text(stage1_stdout).strip()[-3000:]
    return (
        "You are a targeted verifier. A plain diff review flagged concrete suspected defects in the uncommitted change.\n"
        "Test ONLY the suspected defects below against the actual code (e.g. run a minimal probe or `memory.py counterexample`).\n"
        "Do NOT edit source files.\n\n"
        f"<requirement>\n{req}\n</requirement>\n\n"
        f"<suspected_defects>\n{suspect_block}\n</suspected_defects>\n\n"
        "End your answer with one final line, and nothing after it:\n"
        "VERDICT: FAIL      (at least one suspected defect is confirmed by a command)\n"
        "VERDICT: PASS      (the suspected defects were refuted by running checks)\n"
        "VERDICT: UNKNOWN   (could not confirm or refute the suspected defects)\n"
    )


def merge_usage(u1: dict, u2: dict) -> dict:
    out: dict = {}
    if "cost_usd" in u1 or "cost_usd" in u2:
        out["cost_usd"] = round(float(u1.get("cost_usd", 0.0)) + float(u2.get("cost_usd", 0.0)), 4)
    for k in ("tokens", "turns"):
        if k in u1 or k in u2:
            out[k] = int(u1.get(k, 0)) + int(u2.get(k, 0))
    return out


def prepare_case_repo(base: Path, case: dict, skills_src: Path, agents_src: Optional[Path]) -> Path:
    """A fresh repository for one judge case: the case's own code, committed, with its patch applied and not committed.

    The judge works there, and nowhere near the case list: the labels and the other cases are not in its reach.
    """
    ws = Path(tempfile.mkdtemp(prefix="skill-eval-case-"))
    try:
        shutil.copytree(base / case["repo"], ws, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        for args in (("init", "-q"), ("add", "-A"), ("-c", "user.email=case@localhost", "-c", "user.name=case", "commit", "-q", "-m", "base")):
            r = git(*args, cwd=ws)
            if r.returncode != 0:
                die(f"case {case['id']}: git {args[0]} failed: {r.stderr.strip()[-200:]}")
        if case.get("patch"):
            r = git("apply", "--whitespace=nowarn", str((base / case["patch"]).resolve()), cwd=ws)
            if r.returncode != 0:
                die(f"case {case['id']}: the patch does not apply: {r.stderr.strip()[-200:]}")
        shutil.copytree(skills_src, ws / ".agents" / "skills", ignore=shutil.ignore_patterns("__pycache__", ".backup"))
        shutil.copytree(skills_src, ws / ".claude" / "skills", ignore=shutil.ignore_patterns("__pycache__", ".backup"))
        if agents_src and agents_src.is_dir():
            shutil.copytree(agents_src, ws / ".claude" / "agents", ignore=shutil.ignore_patterns(".backup"))
        (ws / ".git" / "info" / "exclude").write_text(".agents/\n.claude/\n.skill-eval-prompt.txt\n.skill-eval-verify-prompt.txt\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(ws, ignore_errors=True)
        raise
    return ws


def cmd_judge(a) -> None:
    """Measure an evaluator (a judge) on cases with a known answer: how often does it approve wrong work?

    Each case is a line of JSON: {"id", "label": "correct" | "wrong", "prompt", "setup"?}. `setup` is a shell
    command that puts the work to judge into a fresh checkout (for example `git apply cases/x.diff`).
    A case with "repo" (a folder, relative to the case file) and "patch" (a diff file) brings its own code:
    the judge then works in a new repository with that code and the patch, away from this repository.
    The judge command gets the prompt and must print `VERDICT: PASS`, `VERDICT: FAIL` or `VERDICT: UNKNOWN`.
    Keep the labels out of the prompt and out of the repository that the judge can read.
    """
    repo = repo_root()
    cmd_t = a.judge_cmd or os.environ.get("SKILL_EVAL_JUDGE_CMD")
    if not cmd_t:
        die("set --judge-cmd or SKILL_EVAL_JUDGE_CMD, e.g. 'claude -p {prompt}'")
    skills = (repo / a.skills).resolve()
    if not skills.is_dir():
        die(f"skills dir {skills} not found")
    # subagents for a case with its own repository: this project's, else the pack's root agents/ (or legacy templates)
    agents = next((d for d in (repo / ".claude" / "agents", repo / "agents", repo / "templates" / ".claude" / "agents") if d.is_dir()), None)
    verify_t = a.verify_cmd or cmd_t
    cases = []
    for i, line in enumerate(Path(a.cases).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            c = json.loads(line)
        except ValueError:
            die(f"{a.cases} line {i} is not JSON")
        if not c.get("id") or c.get("label") not in ("correct", "wrong") or not c.get("prompt"):
            die(f"{a.cases} line {i}: a case needs id, label (correct|wrong) and prompt")
        cases.append(c)
    if not cases:
        die(f"{a.cases} has no cases")
    if a.repeats < 1:
        die("--repeats must be at least 1")
    runs = a.repeats * len(cases)
    if runs > a.max_runs and not a.yes:
        die(f"{runs} judge runs planned (> --max-runs {a.max_runs}); this costs tokens. Re-run with --yes to confirm.")
    logdir = new_logdir("judge")
    cases_dir = Path(a.cases).resolve().parent
    git_lock = threading.Lock()
    print_lock = threading.Lock()

    def run_one(idx: int, c: dict, rep: int) -> Tuple[int, dict]:
        own = bool(c.get("repo"))
        if own:
            wt = prepare_case_repo(cases_dir, c, skills, agents)
        else:
            with git_lock:
                wt = prepare_worktree(repo, skills, None)
        t0 = time.time()
        try:
            if c.get("setup"):
                s_cmd = sh(c["setup"], wt, a.timeout)
                if s_cmd.returncode != 0:
                    die(f"case {c['id']}: setup failed: {(s_cmd.stderr or s_cmd.stdout).strip()[-300:]}")
            req = extract_requirement(c["prompt"])
            if a.mode in ("plain", "two-stage"):
                ctx = collect_base_context(wt, req)
                p1_text = build_plain_prompt(req, clean_diff_for_review(wt), two_stage=(a.mode == "two-stage"), context_text=ctx)
            else:
                p1_text = c["prompt"]
            pfile = wt / ".skill-eval-prompt.txt"
            pfile.write_text(p1_text, encoding="utf-8")
            cmd = cmd_t.format(prompt=q(p1_text), prompt_file=q(str(pfile)), workdir=q(str(wt)))
            try:
                r = sh(cmd, wt, a.timeout)
                rc, stdout, stderr = r.returncode, r.stdout or "", r.stderr or ""
            except subprocess.TimeoutExpired as e:
                rc, stdout, stderr = "timeout", _text(e.stdout), _text(e.stderr)
            slug = re.sub(r"[^A-Za-z0-9_.-]", "_", str(c["id"]))
            log = logdir / f"{slug}-{rep + 1}.txt"
            try:
                log.write_text(f"$ {cmd}\nexit: {rc}\n--- stdout ---\n{stdout[-LOG_LIMIT:]}\n--- stderr ---\n{stderr[-LOG_LIMIT:]}\n", encoding="utf-8")
            except OSError:
                pass
            usage = parse_usage(stdout)
            extra: dict = {}
            if a.mode == "two-stage":
                decision, hyps, _ = parse_stage1(stdout)
                extra["stage1_decision"] = decision
                if decision == "SUSPECT":
                    p2_text = build_verify_prompt(req, hyps, stdout)
                    p2_file = wt / ".skill-eval-verify-prompt.txt"
                    p2_file.write_text(p2_text, encoding="utf-8")
                    cmd2 = verify_t.format(prompt=q(p2_text), prompt_file=q(str(p2_file)), workdir=q(str(wt)))
                    try:
                        r2 = sh(cmd2, wt, a.timeout)
                        rc2, out2, err2 = r2.returncode, r2.stdout or "", r2.stderr or ""
                    except subprocess.TimeoutExpired as e:
                        rc2, out2, err2 = "timeout", _text(e.stdout), _text(e.stderr)
                    log2 = logdir / f"{slug}-{rep + 1}-stage2.txt"
                    try:
                        log2.write_text(f"$ {cmd2}\nexit: {rc2}\n--- stdout ---\n{out2[-LOG_LIMIT:]}\n--- stderr ---\n{err2[-LOG_LIMIT:]}\n", encoding="utf-8")
                    except OSError:
                        pass
                    found = VERDICT_RE.findall(_extract_result_text(out2))
                    verdict = found[-1].upper() if found else "UNKNOWN"
                    usage = merge_usage(usage, parse_usage(out2))
                    extra["stage"] = 2
                else:
                    verdict = "PASS" if decision == "APPROVE" else "UNKNOWN"
                    found = [verdict] if verdict == "PASS" else []
                    extra["stage"] = 1
            else:
                found = VERDICT_RE.findall(_extract_result_text(stdout))
                verdict = found[-1].upper() if found else "UNKNOWN"  # no verdict line: the judge did not decide
            row = {"id": c["id"], "label": c["label"], "rep": rep + 1, "verdict": verdict, "stated": bool(found),
                   "seconds": round(time.time() - t0, 1), **extra, **usage}
            stage_note = f" [stage {extra['stage']}]" if "stage" in extra else ""
            with print_lock:
                print(f"{str(c['id']):<28} {c['label']:<8} -> {verdict}{stage_note}" + ("" if found else " (no verdict line)"), flush=True)
            return idx, row
        finally:
            if own:
                shutil.rmtree(wt, ignore_errors=True)
            else:
                with git_lock:
                    cleanup(repo, wt)

    jobs = [(idx, c, rep) for idx, (c, rep) in enumerate((c, rep) for c in cases for rep in range(a.repeats))]
    workers = max(1, a.workers)
    if workers == 1:
        indexed_rows = [run_one(idx, c, rep) for idx, c, rep in jobs]
    else:
        indexed_rows = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(run_one, idx, c, rep) for idx, c, rep in jobs]
            for fut in as_completed(futs):
                indexed_rows.append(fut.result())
    indexed_rows.sort(key=lambda item: item[0])
    rows = [row for _, row in indexed_rows]
    s = judge_summary(rows)
    report: dict = {
        "kind": "judge", "date": dt.datetime.now().isoformat(timespec="seconds"), "mode": a.mode, "judge_cmd": cmd_t,
        "repeats": a.repeats, "rule": a.rule, "summary": s, "rows": rows,
    }
    if a.mode == "two-stage":
        report["verify_cmd"] = verify_t
    agg, ag_rate, kap = None, None, None
    if a.repeats > 1:
        per_case = []
        for c in cases:
            verdicts = [r["verdict"] for r in rows if r["id"] == c["id"]]
            agg_v = aggregate_case_verdicts(verdicts, rule=a.rule)
            per_case.append({
                "id": c["id"], "label": c["label"], "verdict": agg_v, "verdicts": verdicts,
                "unanimous": len(set(verdicts)) == 1 and bool(verdicts), "rule": a.rule,
            })
        agg = judge_summary(per_case)
        ag_rate, kap = judge_agreement(per_case)
        report.update({"per_case": per_case, "aggregated": agg, "agreement_rate": ag_rate, "kappa": kap})
    report.update(provenance(repo_root()))
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{dt.datetime.now():%Y%m%d-%H%M%S}-judge.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"
    bal = lambda v: "n/a" if v is None else f"{v:.1%}"
    print(f"\njudge ({a.mode}) on {s['runs']} runs ({s['wrong']} wrong, {s['correct']} correct)")
    print(f"  wrong work approved:    {s['wrong_approved']}/{s['wrong']} ({pct(s['wrong_approved_rate'])}, 95% CI {s['wrong_approved_ci95']})")
    print(f"  correct work rejected:  {s['correct_rejected']}/{s['correct']} ({pct(s['correct_rejected_rate'])}, 95% CI {s['correct_rejected_ci95']})")
    print(f"  no decision (UNKNOWN):  {s['unknown']}/{s['runs']} ({pct(s['unknown_rate'])})")
    print(f"  balanced accuracy:      {bal(s['balanced_accuracy'])} · MCC on decided: {s['mcc_decided'] if s['mcc_decided'] is not None else 'n/a'}")
    if agg is not None:
        print(f"\naggregated ({a.repeats} runs, {a.rule}) on {agg['runs']} cases ({agg['wrong']} wrong, {agg['correct']} correct)")
        print(f"  wrong work approved:    {agg['wrong_approved']}/{agg['wrong']} ({pct(agg['wrong_approved_rate'])}, 95% CI {agg['wrong_approved_ci95']})")
        print(f"  correct work rejected:  {agg['correct_rejected']}/{agg['correct']} ({pct(agg['correct_rejected_rate'])}, 95% CI {agg['correct_rejected_ci95']})")
        print(f"  no decision / split:    {agg['unknown']}/{agg['runs']} ({pct(agg['unknown_rate'])})")
        print(f"  balanced accuracy:      {bal(agg['balanced_accuracy'])} · unanimous: {pct(ag_rate)} · pairwise kappa: {kap if kap is not None else 'n/a'}")
    costed = [r["cost_usd"] for r in rows if isinstance(r.get("cost_usd"), (int, float))]
    print(f"  cost:                   " + (f"${sum(costed):.2f} for {len(costed)} of {len(rows)} runs" if costed else "not reported by the judge command")
          + f" · {sum(r['seconds'] for r in rows) / 60:.0f} minutes")
    print(f"report: {out.as_posix()}\ntranscripts: {logdir.as_posix()}")


def cmd_power(a) -> None:
    """How many tasks a comparison needs. Normal approximation, one run per task and variant.
    Paired: the same tasks run under both variants (what `run` and `ablate` do); rho is the correlation
    of a task's result between the variants. Miller (2024) reports 0.3 to 0.7 between models."""
    from statistics import NormalDist
    if not 0 < a.base < 1 or a.delta == 0 or not -1 < a.rho < 1:
        die("power needs 0 < --base < 1, --delta not 0, and -1 < --rho < 1")
    z = NormalDist().inv_cdf(1 - a.alpha / 2) + NormalDist().inv_cdf(a.power)
    p2 = min(max(a.base + a.delta, 0.001), 0.999)
    v1, v2 = a.base * (1 - a.base), p2 * (1 - p2)
    var_paired = v1 + v2 - 2 * a.rho * math.sqrt(v1 * v2)
    paired = math.ceil(z * z * var_paired / a.delta ** 2)
    unpaired = math.ceil(z * z * (v1 + v2) / a.delta ** 2)
    print(f"to detect a change of {a.delta:+.0%} from a pass rate of {a.base:.0%} "
          f"(alpha {a.alpha}, power {a.power:.0%}, correlation {a.rho}):")
    print(f"  paired design (same tasks, both variants): {paired} tasks")
    print(f"  independent samples: {unpaired} tasks for each variant")
    if a.tasks:
        mde = z * math.sqrt(var_paired / a.tasks)
        print(f"  with {a.tasks} tasks, paired: the smallest change you can detect is about +/-{mde:.0%}")
        if mde > abs(a.delta):
            print(f"  so {a.tasks} tasks cannot show a change of {a.delta:+.0%}: a result inside +/-{mde:.0%} says nothing")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # a pipe (hook, agent) gets UTF-8; a console never fails on a character
        try:
            stream.reconfigure(errors="replace") if stream.isatty() else stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Measure skill changes on verifiable tasks (A/B, A/A calibration, ablation).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the task file").set_defaults(fn=cmd_init)

    def common(sp):
        sp.add_argument("--tasks", default=str(TASKS))
        sp.add_argument("--skills", default=".agents/skills", help="skills dir relative to the repo root")
        sp.add_argument("--agent-cmd", help="headless agent template, e.g. \"claude -p {prompt}\"")
        sp.add_argument("--repeats", type=int, default=3)
        sp.add_argument("--timeout", type=int, default=900, help="seconds per agent run and per check")
        sp.add_argument("--max-runs", type=int, default=20)
        sp.add_argument("--min-band", type=float, default=0.10, help="minimum noise band (fraction)")
        sp.add_argument("--yes", action="store_true", help="confirm runs above --max-runs")

    c = sub.add_parser("calibrate", help="A/A run to measure evaluation noise")
    common(c)
    c.set_defaults(fn=cmd_calibrate)
    r = sub.add_parser("run", help="measure a proposal (baseline vs candidate)")
    common(r)
    r.add_argument("--proposal", required=True, help="proposal .md with a ```diff block")
    r.add_argument("--annotate", action="store_true", help="append the verdict to the proposal file")
    r.add_argument("--allow-leak", action="store_true", help="skip the leakage critic")
    r.add_argument("--max-cost-per-pass", type=float, metavar="USD",
                   help="no IMPROVES verdict when the candidate costs more than this for each passed run")
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("ablate", help="measure the value of an existing skill by removing it")
    common(b)
    b.add_argument("--skill", required=True)
    b.set_defaults(fn=cmd_ablate)
    h = sub.add_parser("history", help="show past measurements (avoid re-proposing falsified ideas)")
    h.add_argument("--skill")
    h.set_defaults(fn=cmd_history)
    j = sub.add_parser("judge", help="measure an evaluator on cases with a known answer (how often it approves wrong work)")
    j.add_argument("--cases", required=True, help="JSON lines: id, label (correct|wrong), prompt, optional setup")
    j.add_argument("--judge-cmd", help="headless judge template, e.g. \"claude -p {prompt}\"; must print VERDICT: PASS|FAIL|UNKNOWN")
    j.add_argument("--mode", choices=["evaluator", "plain", "two-stage"], default="evaluator",
                   help="judge protocol: evaluator (default), plain (issue + diff only), or two-stage (plain triage then targeted verify)")
    j.add_argument("--verify-cmd", help="Stage 2 command template for --mode two-stage (default: --judge-cmd)")
    j.add_argument("--workers", type=int, default=1, help="parallel judge workers (default 1)")
    j.add_argument("--skills", default=".agents/skills", help="skills dir relative to the repo root")
    j.add_argument("--repeats", "--reps", dest="repeats", type=int, default=1, help="judge runs per case (default 1)")
    j.add_argument("--rule", choices=["asymmetric", "majority", "strict-fail"], default="asymmetric",
                   help="how repeat verdicts per case are combined (default asymmetric: PASS needs unanimity)")
    j.add_argument("--timeout", type=int, default=900)
    j.add_argument("--max-runs", type=int, default=20)
    j.add_argument("--yes", action="store_true", help="confirm runs above --max-runs")
    j.set_defaults(fn=cmd_judge)
    w = sub.add_parser("power", help="how many tasks are needed to detect a given change (run nothing)")
    w.add_argument("--delta", type=float, required=True, help="change in pass rate to detect, e.g. 0.15")
    w.add_argument("--base", type=float, default=0.5, help="pass rate of the baseline (default 0.5, the worst case)")
    w.add_argument("--rho", type=float, default=0.5, help="correlation of a task's result between variants")
    w.add_argument("--alpha", type=float, default=0.05)
    w.add_argument("--power", type=float, default=0.8)
    w.add_argument("--tasks", type=int, help="also print the smallest change that this many tasks can detect")
    w.set_defaults(fn=cmd_power)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
