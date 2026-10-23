# ADHIKAAR AI — Test Coverage Report (TE-13)

![Coverage](https://img.shields.io/badge/Coverage-83%25-brightgreen.svg)
![Tests](https://img.shields.io/badge/Tests-146%20Passed-success.svg)
![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg)

This document provides the test coverage and audit report for the ADHIKAAR AI codebase, validating deterministic behavior, state machine recovery, audit logging, and portal integration.

---

## 1. Executive Summary

| Component | Tests Passed | Stmts | Miss | Coverage |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Core & Graph Engine** | **92** | 2,729 | 451 | **83%** |
| **Telegram Bot Multi-Channel** | **47** | 1,432 | 594 | **59%** |
| **Mock Scheme Portal** | **7** | 85 | 11 | **87%** |
| **Total Ecosystem** | **146 passed** | **4,246** | **1,056** | **~75% aggregate** |

- **Zero-Network Invariant**: 100% of the unit and integration suite executes without external network access via dependency injection and fakes.
- **Deterministic Evaluation**: Rules engine and state checkpoint transitions achieve **89–100%** coverage.

---

## 2. Backend Module Coverage Breakdown

```
Name                                        Stmts   Miss  Cover   Missing
-------------------------------------------------------------------------
backend/app/__init__.py                         0      0   100%
backend/app/agents/__init__.py                  0      0   100%
backend/app/agents/graph.py                   505     45    91%   107, 199, 201, 203, 312, 330, 358-369...
backend/app/agents/state.py                    81      0   100%
backend/app/api/__init__.py                     0      0   100%
backend/app/audit.py                           80      8    90%   64, 72, 96-97, 131, 152, 162, 168
backend/app/core/config.py                     41      2    95%   18-19
backend/app/db/models.py                       91      0   100%
backend/app/db/session.py                      34     12    65%   20, 22, 35-36, 46-54
backend/app/demo.py                            85      1    99%   202
backend/app/integrations/fakes.py              91     12    87%   24, 87-91, 182, 185-187, 190, 193
backend/app/integrations/interfaces.py         16      0   100%
backend/app/integrations/llm.py               152     55    64%   (Network fallback mocks)
backend/app/integrations/notifier.py           93      5    95%   130-131, 160, 189, 230
backend/app/integrations/ocr.py                69     19    72%   40-41, 45-52, 64-68, 77, 101-108
backend/app/integrations/portal_client.py      60     10    83%   31, 47-48, 56-59, 74-75, 80
backend/app/integrations/sarvam.py            102     17    83%   40-43, 60-61, 71-74, 99-100...
backend/app/integrations/storage.py            53      2    96%   39, 78
backend/app/main.py                           643    112    83%   (API routes, metrics & case flows)
backend/app/ml/classifier.py                  106     45    58%   (Model inference & embeddings)
backend/app/ml/model.py                        42     32    24%   (Training scripts & serialization)
backend/app/rag/ingest.py                      49      2    96%   26, 85
backend/app/rag/retriever.py                  129     50    61%   (Chroma vector store queries)
backend/app/rules/engine.py                   204     22    89%   (Rules evaluation & dependency resolution)
-------------------------------------------------------------------------
TOTAL                                        2729    451    83%
```

---

## 3. High-Value Subsystem Highlights

1. **LangGraph State Orchestrator (`app/agents/graph.py` - 91%)**:
   - Covers full node lifecycle: `intake`, `extract`, `validate`, `rules`, `action_plan`, `simulate`, `submit`, `audit`.
   - Comprehensive edge routing, human-in-the-loop pause, consent gating, and checkpoint resumption verified.

2. **Immutable Audit Vault (`app/audit.py` - 90%)**:
   - SHA-256 forward-chained block verification.
   - PII auto-masking (Aadhaar 8-digit masking, phone masking, sanitized evidence payload).
   - Tamper-detection unit tests verified.

3. **Deterministic Scheme Rules Engine (`app/rules/engine.py` - 89%)**:
   - PM-Kisan, PMAY-G, and NREGA YAML-defined eligibility rule evaluation.
   - Missing fact queries and dynamic branch selection thoroughly tested.

4. **Multi-Channel Telegram Service (`telegram_bot/` - 59%)**:
   - Live scheme directory browsing with fallback mechanism.
   - Consent callbacks, document upload processing, voice memo transcription integration.
   - Case tracking and SLA status polling verified.

---

## 4. How to Run Coverage Locally

```bash
# 1. Backend test suite with coverage
uv run --isolated --project backend --extra test pytest --cov=app --cov-report=term-missing backend/tests

# 2. Telegram Bot test suite with coverage
uv run --isolated --project telegram_bot --extra test pytest --cov=app --cov-report=term-missing telegram_bot/tests

# 3. Mock Portal test suite
uv run --isolated --project mock_portal --extra test pytest mock_portal/tests
```
