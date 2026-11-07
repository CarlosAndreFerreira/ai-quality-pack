---
name: security-review
description: Use when a change touches auth, user input, file/network I/O, secrets, serialisation, SQL, shell, dependencies, error handling, or LLM prompts/tools/agents; or when asked for a security audit. Maps findings to OWASP Top 10:2025 and OWASP Top 10 for LLM Applications 2025. Verified findings only.
license: MIT
metadata:
  version: "2.0"
  sources: "OWASP Top 10:2025 (final Jan 2026); OWASP Top 10 for LLM Applications 2025; OWASP ASVS 5"
---
# Security review

## 1. Map the attack surface
List the entry points in scope: HTTP routes, CLI args, queue consumers, uploads, webhooks, scheduled jobs, LLM tool calls, MCP servers. For each, note the caller and its trust level.

## 2. OWASP Top 10:2025 — check what applies
- **A01 Broken Access Control** (now includes SSRF): explicit authz on every route; object-level checks (does the query filter by owner/tenant?); server-side fetch of user URLs blocks private ranges and metadata endpoints.
- **A02 Security Misconfiguration**: debug off, safe defaults, CORS, security headers, no default credentials.
- **A03 Software Supply Chain Failures**: lockfile committed and used in CI (`uv sync --frozen`, `npm ci`); auditor run (`pip-audit` / `npm audit` / `govulncheck`); new deps justified; no `curl | sh`; pinned CI actions; typosquat check on new package names.
- **A04 Cryptographic Failures**: no homemade crypto; argon2/bcrypt for passwords; constant-time token compare; TLS verification never disabled.
- **A05 Injection**: SQL params only; no `shell=True` or string-built commands; template/NoSQL/LDAP injection; output encoding.
- **A06 Insecure Design**: abuse cases for the feature; rate limits; business-logic limits.
- **A07 Authentication Failures**: session expiry/rotation, MFA hooks, brute-force protection, password reset flow.
- **A08 Software or Data Integrity Failures**: unsafe deserialisation (`pickle`, `yaml.load`, `eval`); unsigned updates or artifacts.
- **A09 Logging & Alerting Failures**: security events logged without secrets/PII; failures are alertable.
- **A10 Mishandling of Exceptional Conditions**: no fail-open (an exception must not skip an auth check); no broad `except: pass`; stack traces not returned to clients; resources released on error paths.

## 3. LLM / agent code — OWASP Top 10 for LLM Applications 2025
- **LLM01 Prompt Injection**: untrusted text (web, docs, email, issues, tool output, memory files) must not be able to change instructions or trigger tools.
- **LLM02 Sensitive Information Disclosure / LLM07 System Prompt Leakage**: no secrets in prompts; assume the system prompt can leak.
- **LLM05 Improper Output Handling**: never pass model output to shell, SQL, `eval` or HTML without validation and encoding.
- **LLM06 Excessive Agency**: tools with side effects need allow-lists, least privilege and human approval for irreversible actions; agents run in a sandbox or container, not on the host with full credentials.
- **LLM08 Vector/Embedding Weaknesses**: tenant isolation in vector stores; access checks on retrieved chunks.
- **LLM10 Unbounded Consumption**: token/time/cost limits per request and per user.
- Also check LLM03 Supply Chain (models, adapters, datasets), LLM04 Poisoning and LLM09 Misinformation where relevant.

## 4. Verify
Each finding needs an exploit sketch: attacker input → effect. No sketch → drop it or label it `PLAUSIBLE`. Cheap to confirm → confirm it with a test.

## 5. Output
Same format as `code-review`, tagged with the category (e.g. `A03`, `LLM06`), ranked by impact × likelihood. End with the 1–3 changes that remove the most risk. For a full audit, reference OWASP ASVS 5 levels instead of this checklist.
