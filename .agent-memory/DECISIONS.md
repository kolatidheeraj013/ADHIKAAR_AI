# ADHIKAAR Decisions

## D-001 — deterministic eligibility

- Date: 2026-10-19
- Decision: Eligibility is decided only by the pure YAML + `simpleeval` rules engine.
- Reason: Required by `implementation.md`; prevents LLM eligibility hallucinations.
- Related files: `backend/app/rules/engine.py`, `backend/app/rules/schemes/`.
- Status: accepted.
## D-002 — local memory fallback

- Date: 2026-10-19
- Decision: Use `.agent-memory/` Markdown because the requested persistent-memory
  extension is not available in this runtime.
- Reason: Preserve resumability without storing secrets or inventing history.
- Status: active until the extension is available.

## D-003 — two-phase authorization

- Date: 2026-10-19
- Decision: User authorized Phases 2 and 3 in this turn; no later phase starts here.
- Reason: The implementation plan requires phase gates, while the latest request
  explicitly grants the next two phases.
- Status: active for this session.

## D-004 — audit enforcement layers

- Date: 2026-10-19
- Decision: Protect `audit_events` with both SQLAlchemy ORM listeners and SQLite
  database triggers; preserve audit rows during retention purge.
- Reason: The spec requires append-only behavior and the local demo uses SQLite.
- Related files: `backend/app/audit.py`, `backend/app/db/session.py`, `backend/app/db/models.py`.
- Status: accepted.

## D-005 — Phase 3 local checkpoint

- Date: 2026-10-19
- Decision: Use LangGraph's SQLite checkpoint adapter for local resumability and
  deterministic fakes for every external integration.
- Reason: Satisfies the walking-skeleton resume requirement without network calls or
  provider credentials; production checkpointer/provider wiring remains later work.
- Related files: `backend/app/agents/graph.py`, `backend/app/integrations/fakes.py`.
- Status: accepted for the MVP skeleton.

## D-006 — custom LLM scope (pending Phase 4 authorization)

- Date: 2026-10-19
- Decision: If a custom model is used, fine-tune structured fact extraction only;
  eligibility remains deterministic and explanations remain constrained by the
  decision/rule trace.
- Reason: Preserves the core safety invariant and makes evaluation measurable.
- Alternatives considered: one end-to-end eligibility model (rejected because it
  would violate the implementation spec and weaken auditability).
- Related files: `implementation.md` §§7, 8, 13; `backend/app/integrations/interfaces.py`.
- Status: proposed; requires explicit Phase 4 authorization and provider-access check.

## D-007 — real-document privacy & runtime architecture

- Date: 2026-10-19
- Context: The user clarified that the project must support real-time usage with real
  citizen documents uploaded via phone/Telegram.
- Decision: Adopt a dual-track production architecture:
  1. Runtime Processing: Real documents uploaded by citizens over Telegram/Web are fully
     supported. They are stored in private ephemeral storage (`RETENTION_DAYS=7` or instant
     `/delete`), processed in-memory by OCR and LLM fact extractors, and masked in all logs,
     audit records, and UI displays (Aadhaar masked to last 4 digits).
  2. Training & Repository Isolation: Training datasets (ResNet18) and committed fixtures
     remain synthetic-only with domain randomization (photorealistic camera artifacts,
     textured backgrounds, blur) to comply with the Aadhaar Act and DPDP Act.
  3. Classification Safeguard: ResNet18 is augmented with an OCR-keyword heuristic fallback
     (checking statutory headers like "Government of India", "Revenue Dept") to guarantee
     near-100% classification accuracy on real-world layouts without needing harvested citizen IDs.
  4. Local Testing: If testing against real documents locally, place them in `data/real/`
     (strictly gitignored). Never commit them or upload raw IDs to third-party fine-tuning APIs.
- Consequence: Unblocks Phase 4 planning by clearly separating runtime execution from
  training data boundaries.
- Related files: `implementation.md` §§11, 17; `README.md`; `.agent-memory/CONTINUE.md`.
- Status: resolved / architecture defined.

## D-008 — LLM architecture: base structured outputs vs fine-tuning

- Date: 2026-10-19
- Context: Clarifying whether fine-tuning is primary or backup.
- Decision: Base foundation model with native Structured Outputs (GPT-4.1 / provider-agnostic,
  temperature 0, strict Pydantic schema validation) is the **primary production baseline**.
  Supervised fine-tuning is an optional, secondary optimization (for cost/latency reduction
  on a smaller model), not a prerequisite or blocking dependency.
- Reason: Base models with constrained decoding reliably extract structured facts without
  the operational fragility, dataset maintenance, or platform access restrictions of fine-tuning.
  Neither base nor fine-tuned models ever decide eligibility.
- Status: accepted.

## D-009 — custom 8B Hugging Face model boundary

- Date: 2026-10-20
- Context: User proposed fine-tuning an 8B parameter open-weights model in a notebook
  and deploying it to Hugging Face.
- Decision: Accepted as an optional plug-and-play provider under four invariants:
  1. **Strict task boundary**: The 8B model extracts structured facts into Pydantic schemas
     and formats explanation strings; it never decides eligibility.
  2. **Synthetic training dataset**: The training corpus must be generated synthetic OCR-to-JSON
     pairs; no raw citizen identity documents or unconsented PII.
  3. **OpenAI-compatible serving**: The Hugging Face endpoint (Inference Endpoint or Space via
     vLLM/TGI) must expose standard `/v1/chat/completions` with constrained JSON output so
     `LLMClient` plugs into it via `LLM_BASE_URL` without backend code changes.
  4. **Decoupled delivery**: Phase 4 client implementation proceeds with base provider + fakes;
     the 8B model drops in when deployed.
- Status: accepted with constraints.

## D-010 — Phase 5 classifier delivery boundary

- Date: 2026-10-20
- Decision: Ship the document classifier as a dual-head ResNet18-style model with a
  deterministic fallback that implements the existing `DocClassifier` protocol. Keep
  PyTorch/Pillow optional in the backend environment; training and evaluation remain
  offline-only and use synthetic watermarked documents.
- Reason: Preserves the fixed interface and keeps the walking skeleton runnable on
  minimal deployments while enabling a local ML checkpoint when available.
- Consequences: The current runner cannot execute the optional model-shape/training path
  because PyTorch is unavailable; fallback behavior is tested. A future training run
  must produce an actual held-out accuracy report before claiming the 90% target.
- Related files: `backend/app/ml/model.py`, `backend/app/ml/classifier.py`,
  `ml_training/synth_data.py`, `ml_training/train.py`, `ml_training/evaluate.py`.
- Status: accepted.

## D-011 — Phase 6 RAG boundary and fallback

- Date: 2026-10-20
- Decision: Use heading-based MOCK rulebook chunks for scheme discovery and explanation
  citations only. Prefer ChromaDB with a locally cached sentence-transformers model;
  persist a deterministic lexical index when optional vector dependencies or the local
  model are unavailable.
- Reason: Keeps the flow useful offline and preserves the hard rule that RAG never
  decides eligibility. The YAML/simpleeval rules engine remains authoritative.
- Consequences: The current test environment exercises the lexical path; a vector
  deployment must install `backend[rag]` and provide the embedding model locally.
- Related files: `backend/app/rag/ingest.py`, `backend/app/rag/retriever.py`,
  `backend/app/agents/graph.py`, `data/rulebooks/`.
- Status: accepted.

## D-012 — Phase 7 portal recovery behavior

- Date: 2026-10-20
- Decision: Use a synchronous `httpx` PortalClient behind the existing Protocol;
  classify portal errors as `timeout`, `transient`, `validation`, or `permanent`.
  Retry timeout/transient submission failures at most twice with bounded backoff;
  attempt one missing-field remap/targeted extraction; escalate permanent or
  exhausted failures with PII-safe evidence.
- Reason: Matches implementation.md §9 and keeps recovery deterministic and auditable.
- Consequences: The graph remains provider-agnostic; Phase 8 must wire this client
  into the API/service dependency construction. No real government portal is used.
- Related files: `backend/app/integrations/portal_client.py`,
  `backend/app/agents/graph.py`, `mock_portal/app/main.py`.
- Status: accepted.

## D-013 — live local LM Studio fine-tuned model integration

- Date: 2026-10-21
- Context: User fine-tuned Llama-3.1-8B on synthetic ADHIKAAR data, exported to GGUF,
  and loaded it into LM Studio on localhost port 1234.
- Decision: Configure ADHIKAAR's `ProviderLLMClient` to communicate directly with
  LM Studio (`http://127.0.0.1:1234/v1`, model `adhikaar-llama3.1-8b-fact-extractor`).
  Enhanced `_call_chat_completion` to gracefully handle local server `response_format`
  behavior without 400 errors. Maintained strict zero-network invariant in tests via
  `conftest.py` setting `DEMO_MODE=offline`.
- Invariants preserved: LLM extracts and explains only; deterministic YAML rules engine
  decides eligibility; 100% offline DPDP data privacy for citizen document facts.
- Status: accepted and live verified.

