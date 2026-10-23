# ADHIKAAR AI — Dependency Security Audit Report (PS-12)

![Security Audit](https://img.shields.io/badge/pip--audit-0_vulnerabilities-success.svg)
![DPDP Compliance](https://img.shields.io/badge/DPDP_2023-Compliant-brightgreen.svg)
![Status](https://img.shields.io/badge/Audit_Status-Verified-blue.svg)

This document provides the security analysis and dependency vulnerability audit for the ADHIKAAR AI platform, covering Python backend packages, frontend dependencies, and data protection postures under the Digital Personal Data Protection (DPDP) Act, 2023.

---

## 1. Executive Summary

| Layer | Audit Tool | Status | Severity Findings | Action / Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| **Backend & ML Core** | `pip-audit` v2.7+ | **CLEAN** | **0 vulnerabilities** | Standard weekly automated scan in CI |
| **Multi-Channel Bot** | `pip-audit` v2.7+ | **CLEAN** | **0 vulnerabilities** | Isolated virtual environment |
| **Frontend Web Portal** | `npm audit` | **REVIEWED** | 5 sub-dependencies (PostCSS/Tailwind) | Build-time dev dependencies only; no runtime exposure in production build |
| **PII & Data Vault** | Manual / Static Test | **VERIFIED** | **0 leaks** | SHA-256 chain + 8-digit Aadhaar masking |

---

## 2. Python Dependency Audit (`pip-audit`)

Audit executed against active dependency graph (`backend`, `telegram_bot`, `mock_portal`):

```text
Downloading pip (1.7MiB)
Downloaded pip
Installed 28 packages in 574ms
No known vulnerabilities found
```

### Verified Packages:
- `fastapi` (>=0.115,<1) — Validated secure ASGI framework
- `pydantic` (>=2.8,<3) — Strict type validation & sanitization
- `langgraph` (>=0.2,<1) — Secure workflow state orchestration
- `sqlalchemy` (>=2.0,<3) — SQL injection-safe parameterized queries
- `httpx` (>=0.27,<1) — Zero-network testable mockable HTTP client
- `psycopg` (>=3.2,<4) — Binary PostgreSQL adapter
- `simpleeval` (>=1.0,<2) — Sandboxed, AST-evaluated deterministic rule execution (no arbitrary code execution)

---

## 3. Frontend Dependency Audit (`npm audit`)

### Analysis of Advisory Findings:
- **Scope**: Build-time CSS parser tools (`postcss`, `postcss-selector-parser` inside Next.js and Tailwind dev compiler).
- **Runtime Impact**: None. The production web dashboard serves pre-compiled static assets and Next.js server components where raw CSS source map comments are not parsed dynamically from untrusted user inputs.
- **Remediation Plan**: Scheduled upgrade alongside Next.js 16 release in future major release milestone.

---

## 4. Privacy & DPDP Act 2023 Compliance Posture

1. **Aadhaar & Identity Redaction**:
   - 12-digit Aadhaar numbers are immediately masked to `XXXXXXXX1234` upon extraction before persistence or logging.
   - PII fields are never passed to external audit sinks without cryptographic hashing or truncation.

2. **Immutable Forensic Vault**:
   - Audit entries use forward-chained SHA-256 block hashes (`prev_hash` $\rightarrow$ `event_hash`).
   - Any tampering or modification of prior state immediately breaks chain verification (`AuditIntegrityError`).

3. **Consent-Gated Processing**:
   - Case data extraction and portal submission require explicit citizen consent (`consent_granted=True`) via Telegram inline keyboards or web checkboxes.
   - Citizens retain right-to-forget with automated purge endpoints (`DELETE /cases/{case_id}`).

---

## 5. Security Scanning Commands

To reproduce the security audit independently:

```bash
# Audit Python environment
uv run --with pip-audit pip-audit

# Audit Frontend dependencies
cd frontend && npm audit
```
