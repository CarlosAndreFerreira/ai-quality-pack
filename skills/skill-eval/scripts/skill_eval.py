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
from __future__ import annotations

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
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

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
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
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
        out[split] = {
            a: {"passed": ap, "runs": n, "rate": round(ap / n, 3), "ci95": wilson(ap, n), **spent[a]},
            b: {"passed": bp, "runs": n, "rate": round(bp / n, 3), "ci95": wilson(bp, n), **spent[b]},
            "delta": round((bp - ap) / n, 3), "tasks_better": wins, "tasks_worse": losses,
            "sign_test_p": round(sign_test(wins, losses), 3), "hard_losses": hard_losses,
            "tampered": tampered, "cost_ratio": round(total(basis, b) / (total(basis, a) or 1e-9), 2), "cost_basis": basis,
        }
    return out


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
           "summary": s, "per_task": per_task, **(extra or {})}
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{kind}-{re.sub(r'[^A-Za-z0-9_.-]', '_', Path(label).stem)}.json"
    out.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    for split, x in s.items():
        names = [k for k in x if isinstance(x[k], dict)]
        b, c = x[names[0]], x[names[1]]
        print(f"\n[{split}] {names[0]} {b['passed']}/{b['runs']} ({b['rate']:.0%}, CI {b['ci95']}) → "
              f"{names[1]} {c['passed']}/{c['runs']} ({c['rate']:.0%}, CI {c['ci95']}); Δ {x['delta']:+.0%}; "
              f"tasks +{x['tasks_better']}/-{x['tasks_worse']}; p={x['sign_test_p']}; cost ×{x['cost_ratio']} ({x['cost_basis']})")
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
    EVALS.mkdir(parents=True, exist_ok=True)
    NOISE.write_text(json.dumps({"band": band, "date": dt.datetime.now().isoformat(timespec="seconds"),
                                 "repeats": a.repeats, "tasks": len(tasks), "agent_cmd": agent_cmd}, indent=2), encoding="utf-8")
    print(f"noise band = ±{band:.0%} (mean A/A disagreement per task, floor {a.min_band:.0%}) → {NOISE}")


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
    out = report("proposal", str(proposal), s, v, reasons, noise, per_task, a, agent_cmd, {"transcripts": logdir.as_posix()})
    m = re.search(r"\.agents/skills/([\w-]+)/", diff)
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
    out = report("ablation", a.skill, s, v, reasons, noise, per_task, a, agent_cmd, {"transcripts": logdir.as_posix()})
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


def main() -> None:
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
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("ablate", help="measure the value of an existing skill by removing it")
    common(b)
    b.add_argument("--skill", required=True)
    b.set_defaults(fn=cmd_ablate)
    h = sub.add_parser("history", help="show past measurements (avoid re-proposing falsified ideas)")
    h.add_argument("--skill")
    h.set_defaults(fn=cmd_history)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
