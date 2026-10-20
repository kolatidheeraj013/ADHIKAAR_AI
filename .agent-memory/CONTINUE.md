# ADHIKAAR Continuation Checkpoint

- Objective: Advance ADHIKAAR per `implementation.md` into Phase 6 (RAG: rulebook
  ingestion and retriever for scheme discovery and explanation citations).
- Completed: Phases 0, 1, 2, 3, 4, and 5 are implemented, tested, and verified.
- Active phase: Phase 5 complete; Phase 6 ready to begin.
- Files to inspect first: this file, `implementation.md` §§12 and 21,
  `backend/app/rag/ingest.py`, `backend/app/rag/retriever.py`, `backend/app/agents/graph.py`,
  `backend/app/integrations/interfaces.py`, and `data/rulebooks/`.
- Phase 4 outcome:
  - `backend/app/integrations/sarvam.py`: ffmpeg 16 kHz mono WAV normalization, duration validation (<=30s), language mapping (`ta|te|hi|en` -> `ta-IN|te-IN|hi-IN|en-IN`), live translation/STT, and offline fixture fallback.
  - `backend/app/integrations/ocr.py`: PaddleOCR wrapper with angle classification, confidence scoring, and offline fixture fallback.
  - `backend/app/integrations/llm.py`: Provider-agnostic OpenAI-compatible `/chat/completions` client supporting any provider/base URL, Pydantic-validated JSON extraction, single-field targeted re-extraction for portal recovery (`extract_field`), 1-retry on malformed JSON, PII masking (`mask_identifiers`), and explanation generation aligned with decision outcomes.
  - `data/fixtures/`: Recorded voice transcripts, OCR results, and LLM fact extractions for offline demo/test mode.
- Tests verified: 53 passed across services (51 backend, 1 telegram_bot, 1 mock_portal) via isolated `uv run` environments; `ruff check` passed cleanly.
- Phase 5 outcome: synthetic watermarked document generator, quality degradations,
  dual-head ResNet18-style model, training/evaluation entry points, and heuristic/model
  `DocumentClassifier` implementing the existing `DocClassifier` protocol.
- Phase 5 tests: 55 backend tests passed, with 1 optional model-shape test skipped because
  PyTorch is unavailable; `make test` also passed the Telegram and mock-portal tests.
- Hugging Face note: the fine-tuned Llama 3.1 8B model will be imported/deployed later
  through the existing OpenAI-compatible `LLM_BASE_URL` boundary. Do not block Phase 6
  on the model artifact.

## Exact first action for the next coding session

Begin Phase 6 only: read `implementation.md` §12, inspect the current RAG placeholders
and `data/rulebooks/`, then implement rulebook ingestion and a deterministic retriever
with focused tests. Keep RAG limited to scheme discovery and explanation citations; the
rules engine remains the only eligibility authority. Stop after Phase 6 verification.
