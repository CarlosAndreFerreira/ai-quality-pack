---
name: ste-writing
description: Use when writing explanations, docs, READMEs, runbooks, ADRs, commit/PR descriptions or step-by-step instructions for humans. Writes ~80% of the way to ASD-STE100 Simplified Technical English and lints the result. Not for code, marketing copy or casual chat.
license: MIT
---
# STE writing (~80% ASD-STE100)

Goal: text a tired engineer can read once, in a second language, and act on correctly.
Target ~80% compliance, not 100%. Full STE is too rigid for general explanations.

## Rules
1. One topic per sentence. One action per instruction.
2. Instructions: max 20 words. Descriptions: max 25 words.
3. Instructions use the imperative: "Run the migration." Not "You should run the migration."
4. Use active voice. Name the actor: "The worker retries the job." Not "The job is retried."
5. One term = one meaning. Pick a term for a concept and keep it. Do not use synonyms for variety.
6. Use common words: "use" not "utilize", "start" not "commence", "help" not "facilitate".
7. No noun clusters longer than 3 words. Rewrite "user session token refresh endpoint" as "the endpoint that refreshes the session token".
8. Avoid phrasal verbs when a single verb exists: "remove" not "get rid of", "find" not "figure out".
9. Keep articles ("the", "a"). Do not write telegraphic text.
10. Max 6 sentences per paragraph. Use numbered lists for sequences, bullets for sets.
11. Put warnings and preconditions BEFORE the step they apply to.
12. No filler, no hedging, no praise: delete "basically", "simply", "just", "it's worth noting", "great question".
13. Technical names (APIs, flags, identifiers) are allowed and stay exact. Put them in `code`.

## When you cannot simplify
If a term or detail cannot be simplified without changing its meaning, keep it and add a short note: `[kept: <term> — <why>]`. Do not silently drop precision.

## Portuguese and other languages
STE is defined for English only. When writing in another language, apply rules 1–4, 5, 10, 11 and 12. There is no approved dictionary. Run the linter with `--lang pt`.

## Verify (required for docs longer than ~10 sentences)
Run the linter on the text you wrote:

```bash
python3 <this-skill-dir>/scripts/ste_lint.py FILE.md            # English
python3 <this-skill-dir>/scripts/ste_lint.py FILE.md --lang pt  # Portuguese
cat draft.txt | python3 <this-skill-dir>/scripts/ste_lint.py -  # stdin
```

Run it with `--help` first. Do not read the source. The linter prints a score (% of sentences without violations) and the top offenders.
- Score ≥ 80%: done.
- Score < 80%: fix the listed sentences and run again. Stop after 2 rounds and report the score.

The linter uses heuristics. It finds candidates, not proof. Ignore a flag if the fix makes the meaning less exact, and say so.
