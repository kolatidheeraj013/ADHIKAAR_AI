# ADHIKAAR Session Log

## 2026-10-19

- Completed Phase 0 scaffold and Phase 1 deterministic MOCK rules engine.
- Verified 19 tests and Ruff; refreshed `graphify-out/` after Phase 1.
- Current user authorization: implement Phases 2 and 3, with testing sub-agent as needed.
- Completed Phase 2: DB models/Alembic, append-only PII-safe audit, local storage, and purge.
- Phase 2 verification: 26 tests passed, Alembic upgrade/check passed, Ruff passed.
- Phase 3 started: typed Pydantic `CaseState` and domain records added.
- Testing sub-agent was unavailable (`omnirush_account_required`); main agent owns tests.
- Completed Phase 3: protocols/fakes, audited LangGraph routing, interrupt/resume,
  SQLite checkpointer, recovery, and all fake-backed acceptance scenarios.
- Phase 3 verification: 34 tests passed, Ruff passed, compileall passed.
- Current state: stop before Phase 4; credentials and provider decisions will be requested then.

## 2026-10-19 — persistent-memory and custom-LLM handoff

- Loaded and followed the `graphify` and `persistent-memory-md` skill instructions.
- Re-read project instructions, implementation spec, existing memory, and the actual
  repository state. Confirmed Phases 0–3 remain represented in the working tree;
  `graphify-out/graph.json` exists; Git shows an unrelated pre-existing `LICENSE`
  modification and the Phase 0–3 commit is present.
- Recorded the current Phase 4 readiness objective: Sarvam is configured locally per
  the user, OpenAI fine-tuning access is unverified, and no Phase 4 code was written.
- Recorded the unresolved conflict between the user’s real-document intent and the
  spec’s synthetic-only privacy rule. No real documents, keys, or private values were
  read or stored.
- Reviewed OpenAI supervised fine-tuning guidance: JSONL chat examples, evals first,
  dated GPT-4.1 snapshots, and platform access limitations for new users.
- Added a reusable ARJUN “SHIPIT” LARP continuation prompt to `CONTINUE.md`.
- Verification after the memory updates: `make test` passed (34 tests, one existing
  LangGraph pending-deprecation warning); `make lint` passed. `git diff --check`
  reports pre-existing CRLF-related trailing whitespace in `LICENSE`; no LICENSE
  change was made.

## 2026-10-19 — verification and Phase 4 gate check

- Resumed from `.agent-memory/CONTINUE.md` and re-read all memory files, `README.md`,
  and `implementation.md` (§§10, 13, 17, 18, 21).
- Executed isolated project checks:
  - `uv run --project backend --extra test pytest backend/tests`: 34 passed (with existing LangGraph deprecation warnings)
  - `uv run --project telegram_bot --extra test pytest telegram_bot/tests`: 1 passed
  - `uv run --project mock_portal --extra test pytest mock_portal/tests`: 1 passed
  - `uv run --project backend ruff check backend telegram_bot mock_portal`: passed
- Preserved invariant: did not initiate Phase 4 without authorization.
- Confirmed blocking policy issue: real-document processing vs synthetic-only requirement
  must be resolved with user before data handling or training pipelines are built.
- Checked OpenAI fine-tuning status: remains unverified; fallback is GPT-4.1 structured outputs.
- Clarified real-time real-document usage with user: established dual-track architecture
  (D-007) separating runtime ingestion (ephemeral, masked, OCR-grounded) from training data
  (synthetic-with-augmentation + OCR keyword heuristics) to satisfy production usability and DPDP Act.

## 2026-10-20 — custom 8B Hugging Face model proposal & dataset generation

- Evaluated user's proposal to train an 8B model in a notebook and host on Hugging Face.
- Formalized [D-009](file:///c:/Users/banks/ADHIKAAR_AI/.agent-memory/DECISIONS.md): supported as an OpenAI-compatible drop-in provider
  behind `LLMClient` via `LLM_BASE_URL`.
- Enforced invariants: fact extraction and explanation only (no eligibility decisions);
  synthetic dataset only; decoupled Phase 4 delivery so progress is not blocked on training.
- Created `ml_training/generate_llm_dataset.py` and generated high-quality ChatML training datasets:
  `ml_training/data/train.jsonl` (1000 examples) and `ml_training/data/val.jsonl` (200 examples),
  covering all scheme fact keys (Aadhaar, Land records, Bank passbooks, Income certificates,
  Marksheets, and voice declarations with explicit nulls across 15 states).
- Refactored `llama_3_8b_instruct_finetune-d13.ipynb` for Colab T4 hardware (Unsloth, 4-bit, fp16).
- Completed Phase 4:
  - Implemented `backend/app/integrations/sarvam.py` (`SarvamSpeechClient`).
  - Implemented `backend/app/integrations/ocr.py` (`PaddleOCRClient`).
  - Implemented `backend/app/integrations/llm.py` (`ProviderLLMClient`).
  - Recorded offline fixtures in `data/fixtures/` (`voice_transcripts.json`, `ocr_results.json`, `llm_facts.json`).
  - Created `backend/tests/test_phase4_integrations.py` with 17 zero-network tests.
  - Ran full test suite: 53 tests passed (51 backend, 1 telegram_bot, 1 mock_portal).
  - Ruff check passed cleanly across all services.

## 2026-10-20 — Phase 4 verification and Phase 5 implementation

- Loaded and followed `graphify` and `persistent-memory-md`; re-read the project
  memory, implementation spec, source changes, and Git status.
- Verified Phase 4 directly: `backend/tests/test_phase4_integrations.py` passed all
  17 tests; the complete backend suite passed 55 tests after Phase 5 was added.
- Implemented Phase 5: synthetic document generation with visible watermark and four
  quality degradations, dual-head ResNet18-style model, local training/evaluation
  entry points, and model/heuristic `DocumentClassifier` inference.
- Fixed a real test-discovery issue by making backend tests import both the backend
  package and repository-level `ml_training` utilities.
- Verified `make test` passed: 55 backend tests (1 optional skip), 1 Telegram test,
  and 1 mock-portal test. Ruff passed. Training/evaluation emitted safe fallback
  reports because PyTorch/Pillow are unavailable in this runner.
- Refreshed graphify with `graphify . --update --no-viz --code-only` and
  `graphify cluster-only . --no-viz`: 653 nodes, 1303 edges, 63 communities.
- Recorded that the fine-tuned Llama 3.1 8B model will be imported later from
  Hugging Face through the existing OpenAI-compatible `LLM_BASE_URL`; Phase 6 does
  not depend on that artifact.
- Next phase is Phase 6 RAG; no Phase 6 code was started in this session.
