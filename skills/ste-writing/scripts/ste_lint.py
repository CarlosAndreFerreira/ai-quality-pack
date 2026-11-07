#!/usr/bin/env python3
"""ste_lint.py — heuristic linter for ~80% ASD-STE100 style prose.

Checks (per sentence, code blocks and inline code ignored):
  LEN    instruction > 20 words / description > 25 words
  PASS   likely passive voice
  FILL   filler / hedging / praise words
  WORD   complex word that has a simple STE-style replacement (en only)
  PARA   paragraph with > 6 sentences (reported per paragraph)

Score = % of sentences with zero violations. Target >= 80.
Exit code: 0 if score >= threshold, 1 otherwise (use in CI / hooks).
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

FILLER = {
    "en": [
        "basically", "simply", "just", "actually", "really", "very", "quite",
        "it's worth noting", "it is worth noting", "note that", "in order to",
        "great question", "of course", "obviously", "clearly", "essentially",
        "a bit", "kind of", "sort of", "leverage", "seamless", "robust",
        "delve", "in today's", "needless to say",
    ],
    "pt": [
        "basicamente", "simplesmente", "apenas", "realmente", "muito", "bastante",
        "vale a pena notar", "é importante notar", "de forma a", "a fim de",
        "ótima pergunta", "obviamente", "claramente", "essencialmente",
        "de certa forma", "robusto", "sem falhas",
    ],
}

SIMPLE_WORDS_EN = {
    "utilize": "use", "utilise": "use", "utilization": "use", "commence": "start",
    "terminate": "stop/end", "facilitate": "help", "endeavor": "try",
    "approximately": "about", "subsequently": "then/after", "prior to": "before",
    "in the event that": "if", "ascertain": "find", "demonstrate": "show",
    "numerous": "many", "sufficient": "enough", "additional": "more",
    "modify": "change", "initiate": "start", "obtain": "get", "require": "need",
    "assist": "help", "regarding": "about", "nevertheless": "but",
    "consequently": "so", "figure out": "find", "get rid of": "remove",
    "set up": "configure/install", "come up with": "make/find", "look into": "examine",
}

# Passive heuristics
BE_EN = r"\b(?:is|are|was|were|be|been|being)\b"
PART_EN = r"\b(?:\w+ed|\w+en|built|done|made|sent|set|run|kept|held|found|shown|known|given|taken|written|read|put|seen|left|lost|paid|sold|told|thrown)\b"
PASSIVE_EN = re.compile(BE_EN + r"(?:\s+\w+ly)?\s+" + PART_EN, re.I)
PASSIVE_PT = re.compile(
    r"\b(?:é|são|foi|foram|será|serão|seja|sejam|era|eram|sido|ser)\b(?:\s+\w+mente)?\s+\w+(?:ado|ada|ados|adas|ido|ida|idos|idas|ito|ita|itos|itas|osto|osta)\b",
    re.I,
)

# Imperative detection: sentence starts with a base-form verb (cheap list + list items)
IMPERATIVE_EN = re.compile(
    r"^(?:do not|don't|never|always|)\s*(?:add|apply|build|call|change|check|close|configure|copy|create|delete|deploy|disable|do|edit|enable|ensure|install|keep|make|merge|move|open|push|put|read|remove|rename|replace|restart|run|select|set|start|stop|test|type|update|upgrade|use|verify|wait|write)\b",
    re.I,
)
IMPERATIVE_PT = re.compile(
    r"^(?:não\s+)?(?:adicione|aplique|chame|altere|verifique|feche|configure|copie|crie|apague|elimine|instale|mantenha|faça|abra|corra|execute|leia|remova|substitua|reinicie|selecione|defina|inicie|pare|teste|escreva|use|atualize|espere|garanta)\b",
    re.I,
)

ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|approx|ex|p\.ex|Dr|Mr|Mrs|Sr|Sra)\.", re.I)


@dataclass
class Sentence:
    text: str
    line: int
    issues: list[str] = field(default_factory=list)


def strip_markdown(src: str) -> list[tuple[int, str]]:
    """Return (line_no, text) for prose lines; drop fenced code, tables, front-matter, html."""
    out: list[tuple[int, str]] = []
    in_fence = False
    in_front = False
    for i, raw in enumerate(src.splitlines(), 1):
        line = raw.rstrip()
        if i == 1 and line.strip() == "---":
            in_front = True
            continue
        if in_front:
            if line.strip() == "---":
                in_front = False
            continue
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or line.lstrip().startswith(("|", "<", "    ")):
            out.append((i, ""))
            continue
        line = re.sub(r"`[^`]*`", "X", line)             # inline code -> token
        line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)  # links
        line = re.sub(r"^\s*(?:#+|[-*+]|\d+[.)])\s*", "", line)  # headings / list markers
        line = re.sub(r"[*_]{1,3}", "", line)
        out.append((i, line))
    return out


def split_paragraphs(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    paras, cur = [], []
    for ln, txt in lines:
        if not txt.strip():
            if cur:
                paras.append(cur)
                cur = []
        else:
            cur.append((ln, txt))
    if cur:
        paras.append(cur)
    return paras


def split_sentences(para: list[tuple[int, str]]) -> list[Sentence]:
    sents: list[Sentence] = []
    for ln, txt in para:
        # each list item / line is its own unit; then split on terminal punctuation
        protected = ABBREV.sub(lambda m: m.group(0).replace(".", "§"), txt)
        for part in re.split(r"(?<=[.!?:;])\s+", protected):
            part = part.replace("§", ".").strip()
            if len(re.findall(r"\w+", part)) >= 3:
                sents.append(Sentence(part, ln))
    return sents


def word_count(s: str) -> int:
    return len(re.findall(r"[\w'’-]+", s))


def check(sent: Sentence, lang: str, max_instr: int, max_desc: int) -> None:
    t = sent.text
    # quoted examples ("use" not "utilize") are mentions, not usage
    low = re.sub(r'"[^"]*"|“[^”]*”|«[^»]*»', "Q", t).lower()
    wc = word_count(t)
    imper = (IMPERATIVE_PT if lang == "pt" else IMPERATIVE_EN).match(low.strip())
    limit = max_instr if imper else max_desc
    if wc > limit:
        sent.issues.append(f"LEN {wc}>{limit} ({'instruction' if imper else 'description'})")
    if (PASSIVE_PT if lang == "pt" else PASSIVE_EN).search(t):
        sent.issues.append("PASS likely passive voice — name the actor")
    for f in FILLER[lang]:
        if re.search(r"(?<!\w)" + re.escape(f) + r"(?!\w)", low):
            sent.issues.append(f"FILL '{f}'")
    if lang == "en":
        for w, rep in SIMPLE_WORDS_EN.items():
            if re.search(r"(?<!\w)" + re.escape(w) + r"\w*", low):
                sent.issues.append(f"WORD '{w}' -> '{rep}'")


def lint(src: str, lang: str, max_instr: int, max_desc: int, max_para: int):
    paras = split_paragraphs(strip_markdown(src))
    all_sents: list[Sentence] = []
    para_issues: list[str] = []
    for p in paras:
        sents = split_sentences(p)
        # list items count as separate paragraphs in practice; only flag real prose blocks
        if len(p) <= 2 and len(sents) > max_para:
            para_issues.append(f"line {p[0][0]}: paragraph has {len(sents)} sentences (> {max_para})")
        for s in sents:
            check(s, lang, max_instr, max_desc)
        all_sents.extend(sents)
    total = len(all_sents)
    clean = sum(1 for s in all_sents if not s.issues)
    score = round(100 * clean / total, 1) if total else 100.0
    return score, all_sents, para_issues


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Heuristic ~80%% ASD-STE100 linter. Prints score and offending sentences."
    )
    ap.add_argument("file", help="Markdown/text file, or '-' for stdin")
    ap.add_argument("--lang", choices=["en", "pt"], default="en")
    ap.add_argument("--max-instruction", type=int, default=20)
    ap.add_argument("--max-description", type=int, default=25)
    ap.add_argument("--max-paragraph", type=int, default=6)
    ap.add_argument("--threshold", type=float, default=80.0, help="exit 1 below this score")
    ap.add_argument("--top", type=int, default=15, help="max offenders to print")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    src = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8", errors="replace").read()
    score, sents, para = lint(src, a.lang, a.max_instruction, a.max_description, a.max_paragraph)
    bad = [s for s in sents if s.issues]

    if a.json:
        print(json.dumps({
            "score": score, "threshold": a.threshold, "sentences": len(sents),
            "violations": [{"line": s.line, "text": s.text, "issues": s.issues} for s in bad],
            "paragraphs": para,
        }, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if score >= a.threshold else "FAIL"
        print(f"STE score: {score}%  ({len(sents) - len(bad)}/{len(sents)} clean)  [{status}, threshold {a.threshold}%]")
        counts: dict[str, int] = {}
        for s in bad:
            for i in s.issues:
                counts[i.split()[0]] = counts.get(i.split()[0], 0) + 1
        if counts:
            print("by rule: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
        for s in sorted(bad, key=lambda s: -len(s.issues))[: a.top]:
            short = s.text if len(s.text) <= 110 else s.text[:107] + "..."
            print(f"\n  L{s.line}: {short}\n    - " + "\n    - ".join(s.issues))
        for p in para:
            print(f"\n  PARA {p}")
    return 0 if score >= a.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
