# ADHIKAAR — Implementation Spec

> Single source of truth for the build. Coding agents: read this fully before writing code.
> If something here is wrong or impossible, flag it in one line, propose a fix, and continue with the fix unless told otherwise.

---

## 0. One-paragraph brief

Adhikaar is an autonomous welfare-entitlement agent. A citizen talks to a **Telegram bot** (a web form is the fallback) and sends **document photos + a voice note** (Tamil / Telugu / Hindi). The agent transcribes the request, classifies and reads the documents, extracts facts, asks the citizen a follow-up question when a declaration is missing, checks eligibility with a **deterministic rules engine**, scores its own confidence, **submits the application** to a (mock) scheme portal, verifies the result, **recovers** from failures, and **escalates to a human reviewer** when it is unsure. Every step is written to an **audit trail**.

**Core principle (never violate):**

> The LLM **extracts and explains**. The rules engine **decides**. A human **handles doubt**.
> No model ever decides eligibility.

Agent loop required by the hackathon:
`INPUT → UNDERSTAND → PLAN → USE TOOLS → ACT → VERIFY → RECOVER / ESCALATE → AUDIT`

---

## 1. Scope

### In scope (MVP)
- **Telegram bot** as the primary citizen channel: language choice, consent, voice/text + document photos, status updates, follow-up questions via buttons, delete-my-data (§15).
- **Web form** as a fallback citizen channel, plus the **reviewer dashboard** (§16).
- 2 schemes, defined as YAML rule files (§6). Mock/simplified rules, clearly labeled `MOCK`.
- Voice note → transcript → English intent (Sarvam AI). Typed text is accepted as an alternative to voice.
- Document photo → type + quality classification (fine-tuned ResNet18) → OCR (PaddleOCR).
- LLM fact extraction with a **grounding check** against OCR text.
- **Citizen clarification:** when a declaration fact (e.g. "does your family pay income tax?") is missing, the agent asks the citizen instead of stalling.
- Rules engine with tri-state outcome and per-rule trace.
- Confidence scoring + routing (auto-submit / human review / request documents).
- Mock scheme portal with injectable failures; retry → auto-fix → escalate recovery.
- Append-only audit trail, viewable by reviewers.
- Offline demo mode (recorded fixtures for Sarvam / LLM / OCR) for the web form and `make demo`. **Telegram itself needs internet**, so keep the web form as the demo fallback.

### Non-goals (do NOT build)
- Any citizen channel other than the Telegram bot and the web form.
- PDF uploads (images only: JPEG / PNG / WebP).
- Real government portal automation, real Aadhaar/UIDAI verification.
- Reviewer notifications over Telegram, payments, multi-tenant auth, mobile app, analytics.
- Multiple schemes in one case (MVP processes one scheme per case, see §7.1).
- Any refactor or framework not listed in §3.

---

## 2. Architecture

```
 Citizen ── Telegram app ──► telegram_bot ──┐          (HTTP only)
 Citizen ── web form (fallback) ► frontend ─┤
                                            ▼
                                   backend (FastAPI)
                                            │
                              LangGraph agent graph ───────► mock_portal (FastAPI)
                               │    │    │    │
                               │    │    │    └─ Rules engine (YAML + simpleeval)
                               │    │    └────── RAG (ChromaDB: rulebook text)
                               │    └─────────── Doc classifier (ResNet18) + PaddleOCR
                               └──────────────── Sarvam (STT / translate) + LLM (extract / explain)
                                            │
        Postgres (cases, documents, facts, decisions, messages, audit)  ·  File storage (private)

 Backend ─► Notifier ─► telegram_bot /internal/notify ─► citizen's Telegram chat
 Reviewer dashboard (frontend, web only): queue, evidence, approve / reject / request docs, audit view
```

All external services sit behind **interfaces** (`typing.Protocol`) so tests and offline demo mode use fakes. See §10.

Default ports: frontend 3000, backend 8000, mock_portal 8100, telegram_bot 8200.

---

## 3. Tech stack (fixed — do not add alternatives)

| Area | Choice |
|---|---|
| Citizen channel | Telegram bot via `python-telegram-bot` (v21+, async). Polling in dev, webhook in prod. Bot created with @BotFather. |
| Speech | Sarvam AI (speech-to-text + translate). Check current Sarvam docs for model names, endpoints, language codes (e.g. `ta-IN`) and audio length limits before coding. |
| Audio | `ffmpeg` (installed in the backend image) to normalize Telegram voice notes (OGG/Opus) before STT |
| OCR | PaddleOCR (verify Tamil / Telugu / Hindi models are available; fall back to English + digits if one is missing) |
| Vision ML | PyTorch + torchvision, ResNet18 (ImageNet-pretrained, fine-tuned) |
| Agents | LangGraph (state machine, checkpointer, `interrupt` for human-in-the-loop), LangChain (tool calling) |
| LLM | Provider-agnostic `LLMClient` (env `LLM_PROVIDER`); structured output validated with Pydantic v2; temperature 0 |
| Rules | Python + YAML, expressions via `simpleeval` (**never `eval`**) |
| DB | PostgreSQL (docker-compose locally, Supabase in deploy), SQLAlchemy 2 + Alembic |
| Vector | ChromaDB (embedded persistent client) + sentence-transformers (multilingual MiniLM or similar) |
| Storage | `StorageBackend` interface: local disk (dev), Supabase Storage (prod), private bucket |
| Backend | FastAPI, Pydantic v2, Python 3.11+, `httpx` for service-to-service calls |
| Frontend | Next.js (App Router) + TypeScript + Tailwind CSS |
| Quality | pytest, ruff, mypy (light), GitHub Actions (optional) |
| Deploy | Docker / docker-compose. Vercel for `frontend/`; a container host for `backend/`, `telegram_bot/`, `mock_portal/` (the bot is a long-running process and cannot run on Vercel). |

---

## 4. Repo layout (classified by concern)

One repo, one top-level folder per concern. **Each folder owns its own dependencies, config and Dockerfile.** Never put backend code in `frontend/` or the reverse.

```
adhikaar/
├── implementation.md
├── README.md
├── Makefile                          # make dev | test | demo | train | seed
├── docker-compose.yml                # postgres, backend, mock_portal, telegram_bot, frontend
├── .env.example                      # all variables, grouped by service (§18)
├── .gitignore                        # data/real/, .env, weights, synthetic_docs
│
├── frontend/                         # Next.js + TypeScript + Tailwind (own package.json)
│   ├── app/
│   │   ├── page.tsx                          # citizen intake (web fallback)
│   │   ├── case/[id]/page.tsx                # citizen status, questions, uploads
│   │   ├── reviewer/page.tsx                 # escalation queue
│   │   ├── reviewer/[id]/page.tsx            # evidence view + decision
│   │   └── audit/[id]/page.tsx               # audit timeline (reviewer only)
│   ├── components/                   # Timeline, RuleTrace, FactTable, DocViewer, QuestionCard
│   ├── lib/                          # typed API client, shared types, SSE hook
│   └── public/
│
├── backend/                          # FastAPI service (own pyproject.toml, Dockerfile)
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                     # config, logging, constants
│   │   ├── api/routes/               # cases, reviewer, schemes, dev
│   │   ├── db/                       # models.py, session.py, migrations/
│   │   ├── schemas/                  # Pydantic request/response + domain models
│   │   ├── agents/
│   │   │   ├── state.py
│   │   │   ├── graph.py
│   │   │   └── nodes/                # one file per node (§7.2)
│   │   ├── rules/
│   │   │   ├── engine.py
│   │   │   └── schemes/              # pm_kisan_mock.yaml, state_scholarship_mock.yaml
│   │   ├── integrations/
│   │   │   ├── interfaces.py         # Protocols
│   │   │   ├── sarvam.py  ocr.py  llm.py  storage.py  portal_client.py  notifier.py
│   │   │   └── fakes.py              # tests + offline demo mode
│   │   ├── ml/                       # inference only: model.py (architecture), classifier.py
│   │   ├── rag/                      # ingest.py, retriever.py
│   │   └── audit.py
│   ├── tests/                        # unit, graph e2e (fakes), API tests
│   ├── Dockerfile                    # includes ffmpeg
│   └── pyproject.toml
│
├── telegram_bot/                     # Telegram citizen channel (own pyproject.toml, Dockerfile)
│   ├── app/
│   │   ├── main.py                   # FastAPI (health + /internal/notify) + bot lifecycle
│   │   ├── bot.py                    # Application builder, handler registration
│   │   ├── handlers/                 # start, language, consent, voice, text, documents, answers, commands
│   │   ├── backend_client.py         # the only way the bot reaches the backend (HTTP)
│   │   ├── notify.py                 # renders backend notifications as Telegram messages/buttons
│   │   ├── onboarding.py             # in-memory language/consent state before a case exists
│   │   └── i18n.py                   # static UI strings: ta / te / hi / en
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── mock_portal/                      # separate FastAPI service simulating the scheme portal
│   ├── app/main.py
│   ├── Dockerfile
│   └── pyproject.toml
│
├── ml_training/                      # offline model work; never imported at runtime
│   ├── synth_data.py                 # synthetic mock-document generator
│   ├── train.py                      # imports architecture from backend/app/ml/model.py
│   ├── evaluate.py
│   ├── reports/                      # accuracy + confusion matrices (committed)
│   └── weights/                      # doc_classifier.pt (gitignored or git-lfs)
│
├── data/
│   ├── rulebooks/                    # markdown scheme guidance for RAG (MOCK, labeled)
│   ├── fixtures/                     # recorded Sarvam / LLM / OCR outputs for offline mode
│   └── synthetic_docs/               # generated, gitignored
│
├── scripts/                          # seed.py, run_demo.py (runs scenarios A–E), purge.py
└── docs/                             # architecture notes, demo script, pitch notes, final thresholds
```

**Folder rules**
- `frontend/` and `telegram_bot/` talk to `backend/` over HTTP (and SSE for the web) only.
- `backend/` reaches the bot only through the `Notifier` interface (`integrations/notifier.py`).
- `backend/` talks to `mock_portal/` through `integrations/portal_client.py` only.
- The Telegram bot token lives **only** in `telegram_bot/`. The backend never holds it.
- `ml_training/` produces weights; `backend/app/ml/` loads them via `CLASSIFIER_WEIGHTS_PATH`.
- Paths elsewhere in this document are relative to `backend/app/` unless a top-level folder is named.
- Tests for each service live inside that service (`backend/tests/`, `telegram_bot/tests/`, `frontend/__tests__/` if added).

---

## 5. Data model (Postgres)

Use SQLAlchemy 2 + Alembic. UUID4 primary keys, `created_at` everywhere.

| Table | Key columns |
|---|---|
| `cases` | id, language, channel (`web`\|`telegram`), channel_ref (Telegram chat_id, nullable), status, consent_at, intent_text, created_at, updated_at |
| `documents` | id, case_id, storage_path, doc_type, doc_type_conf, quality, quality_conf, ocr_text, ocr_conf |
| `facts` | id, case_id, key, value_json, source_type (`document`\|`declaration`\|`reviewer`), source_doc_id, grounded (bool, null for non-document), conf |
| `decisions` | id, case_id, scheme_id, outcome (`ELIGIBLE`\|`NOT_ELIGIBLE`\|`UNDETERMINED`), rule_trace (jsonb) |
| `applications` | id, case_id, scheme_id, payload (jsonb), portal_ref, status, attempts |
| `escalations` | id, case_id, reason, evidence (jsonb), status (`OPEN`\|`RESOLVED`), reviewer_id, resolution, resolved_at |
| `messages` | id, case_id, direction (`out`\|`in`), kind (`info`\|`question`\|`result`), language, text, payload (jsonb: question key + options), delivered (bool), created_at |
| `audit_events` | id, case_id, ts, actor, event_type, summary, evidence (jsonb), confidence, rationale |

**Case statuses**
- `COLLECTING` — draft case; inputs still arriving.
- `RECEIVED` — `/start` accepted, queued.
- `PROCESSING` — graph running.
- `NEEDS_INFO` — waiting for the citizen to answer a question.
- `NEEDS_DOCUMENTS` — waiting for the citizen to upload/replace documents.
- `NEEDS_REVIEW` — waiting for a human reviewer.
- `SUBMITTED` — portal acknowledged the application.
- `COMPLETED` — final message delivered to the citizen.
- `NOT_ELIGIBLE` — rules say no; reasons explained.
- `FAILED_ESCALATED` — recovery exhausted and a human could not complete it; terminal.

**`audit_events` is append-only.** No UPDATE/DELETE anywhere in app code. Add a test that asserts this (and a DB-level rule or trigger if time allows). **Audit evidence never contains raw ID numbers or full OCR text** — only document IDs, fact keys, masked values, scores and rule IDs — so the trail survives a citizen's delete request (§17).

---

## 6. Rules engine

### 6.1 Scheme file format (YAML)

```yaml
scheme_id: pm_kisan_mock
name: "PM-Kisan (MOCK, simplified — replace with official guidelines before submission)"
version: 1
benefit: "INR 6,000 per year"
required_documents: [aadhaar, land_record, bank_passbook]
facts:                               # facts used by rules
  - { key: land_owned_hectares, type: float, source: land_record }
  - { key: holder_type,         type: str,   source: land_record }   # individual | institutional
  - { key: is_income_tax_payer, type: bool,  source: declaration,
      question: "Does anyone in your family pay income tax?" }       # asked via ask_info if missing
payload_fields:                      # extra facts sent to the portal; not used by rules
  - { key: applicant_name,      type: str, source: aadhaar }
  - { key: aadhaar_last4,       type: str, source: aadhaar }
  - { key: bank_account_number, type: str, source: bank_passbook }
  - { key: bank_ifsc,           type: str, source: bank_passbook }
rules:
  - id: owns_land
    expr: "land_owned_hectares > 0"
    fail_reason: "No cultivable land ownership found in the land record."
  - id: individual_holder
    expr: "holder_type == 'individual'"
    fail_reason: "Land is held by an institution, which is excluded."
  - id: not_tax_payer
    expr: "is_income_tax_payer == False"
    fail_reason: "Income tax payers are excluded."
```

Second scheme `state_scholarship_mock.yaml` (MOCK):
- required docs: `aadhaar`, `income_certificate`, `marksheet`, `bonafide_certificate`
- facts: `family_income_annual` (from `income_certificate`), `last_exam_percentage` (from `marksheet`), `institution_recognized` (declaration, bool, with a `question`)
- rules: `family_income_annual <= 250000`, `last_exam_percentage >= 75`, `institution_recognized == True`
- payload_fields: `applicant_name`, `aadhaar_last4`, `bank_account_number`, `bank_ifsc`

**Declaration facts must be boolean (or a short enumerated choice) so the bot can render buttons.** Numeric declarations are out of scope for the MVP; numbers must come from documents.

### 6.2 Engine behavior
- Load + validate YAML with Pydantic at startup (fail fast on bad schemes).
- Evaluate with `simpleeval` over a facts dict. No `eval`, no `exec`.
- **Tri-state outcome:**
  - `ELIGIBLE` — all rules pass.
  - `NOT_ELIGIBLE` — at least one rule definitively fails.
  - `UNDETERMINED` — any rule references a missing fact. **Never** treat missing as pass.
- Return a **rule trace**: per rule → `{rule_id, passed|failed|unknown, facts_used, source_doc_ids, reason}`. The routing layer uses the trace plus each missing fact's `source` (`declaration` vs document) to decide what to do next (§7.3).
- Pure function, zero I/O, fully unit-testable.

---

## 7. Agent graph (LangGraph)

### 7.1 State (Pydantic)

Types referenced but not shown (`Decision`, `Escalation`, `ApplicationResult`, `Question`, `CaseStatus`) are defined in `backend/app/schemas/`, matching §5.

```python
class Fact(BaseModel):
    key: str; value: Any
    source_type: Literal["document", "declaration", "reviewer"]
    source_doc_id: str | None
    grounded: bool | None   # document facts: value found in OCR text (fuzzy); None otherwise
    conf: float

class DocumentResult(BaseModel):
    doc_id: str; path: str
    doc_type: str; doc_type_conf: float
    quality: Literal["good", "blurry", "cropped", "too_dark"]; quality_conf: float
    ocr_text: str; ocr_conf: float

class CaseState(BaseModel):
    case_id: str
    language: Literal["ta", "te", "hi", "en"]
    channel: Literal["web", "telegram"]
    channel_ref: str | None = None
    voice_path: str | None = None
    document_paths: list[str] = []
    transcript: str | None = None          # from voice, or the typed text
    transcript_en: str | None = None
    candidate_schemes: list[str] = []      # ranked by `plan`; MVP processes only [0]
    documents: list[DocumentResult] = []
    facts: dict[str, Fact] = {}
    missing_documents: dict[str, list[str]] = {}   # scheme_id -> doc types
    decisions: dict[str, Decision] = {}            # keyed by scheme_id (dict allows multi-scheme later)
    confidence: float | None = None                # for the primary scheme
    pending_question: Question | None = None
    questions_asked: int = 0
    human_approved: bool = False
    status: CaseStatus = "RECEIVED"
    escalation: Escalation | None = None
    applications: dict[str, ApplicationResult] = {}
    retries: dict[str, int] = {}                   # submission retries, per-document re-upload requests
```

**One scheme per case (MVP).** `plan` ranks candidates; the graph processes `candidate_schemes[0]`. If the citizen wants another scheme, they start a new case. Other plausible schemes are mentioned in the explanation only.

### 7.2 Nodes

| # | Node | Does | Tools |
|---|---|---|---|
| 1 | `intake` | verify consent, a voice-or-text intent and ≥ 1 document; load files from storage; set `PROCESSING` | storage |
| 2 | `transcribe` | voice → text → English intent (typed text skips STT, still translated) | Sarvam |
| 3 | `classify_docs` | doc type + quality per new file | ResNet18 |
| 4 | `ocr` | text + per-line confidence per new file | PaddleOCR |
| 5 | `extract_facts` | LLM → structured facts from OCR text (document facts) and English transcript (declaration facts, only if explicitly stated); run **grounding check** | LLM |
| 6 | `plan` | RAG + intent → ranked candidate schemes, required docs | ChromaDB |
| 7 | `check_docs` | compare required vs provided/usable docs | — |
| 8 | `eligibility` | run rules engine for the primary scheme | rules |
| 9 | `ask_info` | ask the citizen for a missing declaration fact (buttons); pause with `interrupt()` | Notifier |
| 10 | `verify` | compute confidence (§8), choose route | — |
| 11 | `act` | build payload from `payload_fields`, submit to portal | portal client |
| 12 | `verify_submission` | confirm portal ack / status | portal client |
| 13 | `recover` | retry / auto-fix / escalate (§9) | — |
| 14 | `escalate` | create escalation, `interrupt()` for a human reviewer | — |
| 15 | `explain` | localized plain-language message grounded in decision + rulebook citations; stores it in `messages` and sends via Notifier | LLM, Sarvam translate, Notifier |

**Every node calls `audit.log(...)`** — decorator enforced. No audit event, no merge.

### 7.3 Routing

```
intake → transcribe → classify_docs → ocr → extract_facts → plan → check_docs

check_docs ──required doc missing──► explain (NEEDS_DOCUMENTS) → END   [resumable]
check_docs ──ok──► eligibility

eligibility ──NOT_ELIGIBLE──► explain → END
eligibility ──UNDETERMINED, only declaration facts missing, questions_asked < 3──► ask_info (NEEDS_INFO)
                                                       └─ citizen answers ─► eligibility
eligibility ──UNDETERMINED, document facts missing, first time for that doc──► explain
                                         (ask for a clearer photo of that document, NEEDS_DOCUMENTS) → END
eligibility ──UNDETERMINED, otherwise (repeat failure / questions exhausted)──► escalate
eligibility ──ELIGIBLE──► verify

verify ──human_approved OR conf ≥ AUTO_SUBMIT_THRESHOLD──► act
verify ──REVIEW_THRESHOLD ≤ conf < AUTO_SUBMIT_THRESHOLD──► escalate (NEEDS_REVIEW)
verify ──conf < REVIEW_THRESHOLD, first time for that doc──► explain (clearer docs, NEEDS_DOCUMENTS) → END
verify ──conf < REVIEW_THRESHOLD, repeat──► escalate

escalate ──approve──► act      (for portal-failure escalations: retry submission with reviewer-edited facts)
escalate ──reject──► explain → END
escalate ──request_docs──► explain (NEEDS_DOCUMENTS) → END
reviewer edits facts ──► eligibility → verify (human_approved = True skips only the confidence gate)

act → verify_submission ──ok (SUBMITTED)──► explain → END (COMPLETED)
verify_submission ──fail──► recover ──fixed──► act
                                     └─exhausted──► escalate
act after human approval fails again ──► explain, status FAILED_ESCALATED → END   (terminal; no loops)
```

**Hard rules**
- `act` runs only when the latest decision is `ELIGIBLE`. Human approval **never** overrides `UNDETERMINED` or `NOT_ELIGIBLE`. An `approve` on an escalation whose latest decision is not `ELIGIBLE` must include `edited_facts` (which re-runs `eligibility`); otherwise the API returns 422.
- A re-upload request is made **at most once per document**; a second failure escalates to a human.
- `ask_info` asks **at most 3 questions per case**.

**Execution and resumability**
- `POST /cases/{id}/start` runs the graph in a background task with `thread_id = case_id` and a persistent checkpointer (Postgres, or SQLite in dev), so a pause survives restarts.
- `NEEDS_INFO` / `NEEDS_REVIEW` resume via `Command(resume=...)` (citizen answer / reviewer decision).
- `NEEDS_DOCUMENTS` cases resume when new documents arrive and `/start` is called again: update state and re-enter at `classify_docs`, processing only the new files and keeping prior facts.
- `/start` is idempotent: if the case is already `PROCESSING`, it returns the current status.

---

## 8. Confidence scoring

Computed for the primary scheme only.

```
doc_conf       = min over the scheme's required docs of ( doc_type_conf × quality_factor )
                 quality_factor: good = 1.0, otherwise 0.6

ocr_conf       = mean OCR confidence over the text spans that support the rule facts

grounding_conf = min over the rule facts of:
                   document fact, grounded in OCR text   → 1.0
                   document fact, NOT grounded           → 0.5
                   declaration fact (citizen's answer)   → 0.8
                   reviewer-verified fact                → 1.0

confidence = 0.4·doc_conf + 0.3·ocr_conf + 0.3·grounding_conf
```

Thresholds from env (defaults): `AUTO_SUBMIT_THRESHOLD=0.85`, `REVIEW_THRESHOLD=0.60`. Pick final values so scenario A lands above the auto-submit threshold and scenario C inside the review band; record them in `docs/`.

**Grounding check:** every document fact the LLM extracts must have its value found (fuzzy match, normalized digits/whitespace) in the OCR text of its source document. Ungrounded → `grounded=False`, lowers confidence, and is highlighted for the reviewer. This is the anti-hallucination guard.

**Hard rules, regardless of score:** any `UNDETERMINED` outcome never auto-submits.

---

## 9. Recovery & escalation (must be demoable)

On submission failure (`verify_submission` fails):
1. **Transient error** (timeout / 5xx): retry with exponential backoff, max 2 retries.
2. **Field-level validation rejection** (portal returns `missing_field`, e.g. `bank_ifsc`): attempt **one auto-fix** — re-map the field from existing facts, or re-run a **targeted re-extraction** of that single field from the source document's OCR text; rebuild the payload and resubmit.
3. **Permanent rejection** (portal returns a non-fixable error, e.g. `duplicate_application`): skip auto-fix and escalate immediately.
4. **Still failing after steps 1–2**: `escalate` with a plain-language explanation of what failed, what was tried, and what the human needs to do.

Every attempt is an audit event. The escalation payload must include: reason, evidence (document IDs, masked facts, rule trace, portal error), and what the agent already tried.

---

## 10. Integrations behind interfaces

`integrations/interfaces.py` defines Protocols: `SpeechClient`, `OCRClient`, `LLMClient`, `DocClassifier`, `StorageBackend`, `PortalClient`, `Retriever`, `Notifier`.

- Real implementations: `sarvam.py`, `ocr.py`, `llm.py`, `storage.py`, `portal_client.py`, `notifier.py` (`TelegramNotifier` posts to the bot service; `NoopNotifier` for web cases, which read `messages` via the API/SSE).
- `SpeechClient` normalizes audio with ffmpeg (16 kHz mono WAV) before calling Sarvam, maps `ta|te|hi|en` to Sarvam language codes, and rejects audio longer than `MAX_VOICE_SECONDS`.
- `fakes.py`: deterministic fakes used by tests **and** by `DEMO_MODE=offline`, which replays recorded fixtures from `data/fixtures/`. Includes `FakeNotifier`, which records messages in memory.
- Dependency injection at graph build time. No node imports a concrete client directly.

---

## 11. Document classifier (fine-tuned ResNet18)

**Task:** two outputs per image.
- `doc_type`: `aadhaar`, `land_record`, `income_certificate`, `bank_passbook`, `marksheet`, `bonafide_certificate`, `other`
- `quality`: `good`, `blurry`, `cropped`, `too_dark`

**Model:** ImageNet-pretrained ResNet18, shared backbone, **two linear heads**.

**Training recipe (transfer learning):**
1. Freeze backbone, train heads (3–5 epochs, lr ~1e-3).
2. Unfreeze last residual block, fine-tune (3–5 epochs, lr ~1e-4).
3. Loss = CE(doc_type) + CE(quality). Adam. Early stop on val loss.

**Data — synthetic only (no real citizen IDs, ever):**
- `ml_training/synth_data.py`: render mock documents with PIL templates; fake names/numbers via Faker (`en_IN`); mix English + Tamil/Telugu/Hindi text.
- **Every synthetic document carries a visible "SAMPLE — NOT A REAL DOCUMENT" mark.** We generate lookalikes for classifier training only; they must never be mistakable for real IDs.
- Quality labels are produced by **applying the degradation** (Gaussian blur, random crop, darkening) to a clean render.
- Add realism: perspective warp, rotation, shadows, noise, JPEG compression, textured backgrounds.
- ~300 images per doc type; 80/10/10 split.

**Deliverables:** `ml_training/reports/` with accuracy per head + confusion matrices; weights in `ml_training/weights/doc_classifier.pt`; architecture in `backend/app/ml/model.py`; `backend/app/ml/classifier.py` loads weights from `CLASSIFIER_WEIGHTS_PATH` and returns `(label, softmax_conf)` per head. Target ≥ 90% on held-out synthetic data, and **say plainly in the pitch that it is trained on synthetic data.**

Fallback if training slips: OpenCV heuristics for quality (Laplacian variance, mean brightness) and a stub doc-type classifier. Keep the interface identical so the real model drops in.

---

## 12. RAG (ChromaDB)

**What RAG is for here (be honest in the pitch):**
- Scheme discovery: map the citizen's stated need to candidate schemes.
- Grounding explanations with citations to rulebook text.

**What RAG is NOT for:** eligibility decisions (the rules engine does that).

- `data/rulebooks/*.md`: short guidance per scheme (eligibility text, required documents, FAQs). MOCK content, labeled.
- `backend/app/rag/ingest.py`: chunk by heading, embed with sentence-transformers, persist to `CHROMA_PATH`.
- `backend/app/rag/retriever.py`: `retrieve(query, k=4) → [{text, source, score}]`.

---

## 13. LLM usage (only two jobs)

1. **Fact extraction:** input = OCR text (document facts) or the English transcript (declaration facts) + the target fact schema → output = validated Pydantic object. Temperature 0. Declaration facts are extracted **only if explicitly stated**; otherwise null (the agent asks the citizen). On schema failure, retry once, then mark facts missing. Never let the model guess missing values. Supports targeted single-field re-extraction for recovery (§9).
2. **Explanation:** input = structured decision + rule trace + rulebook snippets → plain-language message. The model **cannot** alter the outcome. Add a test: explanation text must not contradict the decision (simple keyword/label check). Translate to the citizen's language via Sarvam. Messages must never echo full ID numbers (mask to last 4) and must fit Telegram's 4096-character limit.

---

## 14. API (`backend/` — FastAPI)

**Citizen-facing** (the unguessable `case_id` UUID4 acts as the access capability in the MVP):

| Method | Path | Purpose |
|---|---|---|
| POST | `/cases` | JSON `{language, consent: true, channel, channel_ref?}` → `{case_id}`; status `COLLECTING`; stores `consent_at` |
| POST | `/cases/{id}/voice` | multipart audio; validates type, size (`MAX_UPLOAD_MB`), duration (`MAX_VOICE_SECONDS`) |
| POST | `/cases/{id}/text` | JSON `{text}`; typed intent as an alternative to voice |
| POST | `/cases/{id}/documents` | multipart image, repeatable (≤ `MAX_DOCS_PER_CASE`); verifies type by magic bytes, not just extension |
| POST | `/cases/{id}/start` | requires consent + (voice or text) + ≥ 1 document, else 422; starts or re-enters the graph in a background task; idempotent |
| POST | `/cases/{id}/answers` | JSON `{message_id, option}`; answers the pending question and resumes the graph |
| GET | `/cases/{id}` | citizen-safe view: status, localized messages, decision summary. No raw facts or evidence |
| GET | `/cases/{id}/events` | SSE of **sanitized** events (summary text only) for the live timeline |
| DELETE | `/cases/{id}` | purge files, OCR text and facts; audit events remain with redacted evidence |
| GET | `/schemes` | list loaded schemes |

**Service-to-service** (header `X-Service-Token` = `SERVICE_TOKEN`; used by `telegram_bot/`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/cases/active?channel=telegram&channel_ref=<chat_id>` | the open case for a chat. **Declare this route before `/cases/{id}`** so it is not captured as an ID |

**Reviewer** (header `X-Reviewer-Token` = `REVIEWER_PASSWORD`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/reviewer/queue` | open escalations |
| GET | `/reviewer/{case_id}` | evidence: documents, facts (with grounded flag), rule trace, portal errors |
| POST | `/reviewer/{case_id}/resume` | `{action: approve\|reject\|request_docs, edited_facts?, note}` |
| GET | `/reviewer/{case_id}/audit` | full audit trail |

**Dev only** (disabled when `ENV=prod`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/dev/seed` | load demo scenarios |

**Mock portal** (`mock_portal/`, separate service on port 8100):
- `POST /applications` → validates that every `payload_fields` key for the scheme is present; if not, returns 422 `{errors: [{field: "bank_ifsc", code: "missing_field"}]}`. Otherwise returns `{portal_ref}`.
- `GET /applications/{ref}` → status.
- `POST /dev/config` `{fail_mode: none | timeout | reject_permanent}` → global failure injection for demos and tests (dev only). `timeout` makes `POST /applications` hang past the client timeout; `reject_permanent` returns a non-fixable 4xx (`duplicate_application`).

---

## 15. Telegram bot (`telegram_bot/` — citizen channel)

### 15.1 Role
A **thin client**. It owns all Telegram I/O and holds no business logic: no eligibility, no OCR, no Sarvam, no LLM. It talks to `backend/` over HTTP only (`backend_client.py`) and receives push messages on `POST /internal/notify`.

### 15.2 Conversation flow
1. `/start` → short privacy notice (Telegram bot chats are not end-to-end encrypted; Telegram stores messages; the demo uses sample documents only) → language buttons (தமிழ் · తెలుగు · हिन्दी · English) → consent buttons (**I agree** / **No**). Choosing **No** ends the flow. Language/consent live in memory (`onboarding.py`) until a case exists; if the bot restarts mid-onboarding, the user simply sends `/start` again.
2. On consent → `POST /cases` (`channel=telegram`, `channel_ref=<chat_id>`) → prompt: send a voice note (≤ `MAX_VOICE_SECONDS`) or type what help you need.
3. **Voice** (`message.voice`): check `voice.duration` before downloading; download via `getFile`; forward to `POST /cases/{id}/voice`. **Text** messages go to `POST /cases/{id}/text`.
4. **Documents:** accept photos and image files (`document` with an `image/*` MIME type). Telegram compresses photos, so tell the user that sending as a **file** keeps quality; for photos take the largest `PhotoSize`. Forward each to `POST /cases/{id}/documents`. Reject PDFs and other types with a localized message. Albums arrive as separate updates sharing a `media_group_id`: reply **once** ("Received N documents") after ~2 s of quiet, never per photo.
5. After a document is forwarded successfully, the bot **deletes the citizen's message** containing it (best effort; allowed in private chats) so sensitive images do not linger in the chat.
6. An inline **Done** button → `POST /cases/{id}/start`. If the voice/text or documents are missing, the backend returns 422 and the bot says exactly what is missing. After success the bot sends one short "working on it" message; everything after that is pushed by the backend (§15.4).
7. **Questions:** a notification carrying `options` renders as an inline keyboard. On a button press the bot calls `answer_callback_query`, posts `POST /cases/{id}/answers`, and edits the original message to show the chosen answer without the keyboard.
8. **Missing documents:** when the case is `NEEDS_DOCUMENTS`, the user just sends the new photos, then taps **Done** again (`/start` re-enters the graph, §7.3).
9. **Commands:** `/start` (if an active case exists, offer to continue or begin a new one), `/status` (via `GET /cases/active`), `/delete` (confirm, then `DELETE /cases/{id}`), `/help`.

### 15.3 Mechanics to get right
- `callback_data` is limited to **64 bytes**. Use a short token such as `a:<short_message_id>:<option_idx>`, resolved by the backend from `messages.payload`. Never put case UUIDs or long values in `callback_data`.
- Voice notes arrive as OGG/Opus; the backend converts them (§10).
- Bot API file downloads are limited to 20 MB; also enforce `MAX_UPLOAD_MB`.
- Telegram text limit is 4096 characters: split or trim in `notify.py`.
- Per-chat rate limit (~20 updates/minute) and at most `MAX_DOCS_PER_CASE` documents per case.
- Dev: `TELEGRAM_MODE=polling`. Prod: webhook, and validate the `X-Telegram-Bot-Api-Secret-Token` header on every update against `TELEGRAM_WEBHOOK_SECRET`.
- Never log message text or file contents at INFO level; never echo full ID numbers in a message.

### 15.4 Notifications (backend → bot)
- The backend calls its `Notifier`; `TelegramNotifier` posts to `{BOT_INTERNAL_URL}/internal/notify` with header `X-Service-Token`, body `{chat_id, case_id, kind, language, text, options?: [{label, idx}], message_id}`.
- Called from `explain` and `ask_info`. Every outgoing message is stored in `messages` with a `delivered` flag. Delivery failures retry with backoff (max 3), then produce an audit event; **a delivery failure never blocks the graph.**
- Moments that notify the citizen: a question (`NEEDS_INFO`), missing or unclear documents (`NEEDS_DOCUMENTS`, naming the document), `NEEDS_REVIEW` ("a volunteer is reviewing your case"), `SUBMITTED` (with the portal reference), `NOT_ELIGIBLE` (plain-language reasons), `FAILED_ESCALATED`.

### 15.5 Localization
Static bot strings (prompts, buttons, errors) live in `i18n.py` for `ta`, `te`, `hi`, `en`; have a fluent speaker review them. Dynamic content (explanations, questions) arrives already localized from the backend (§13).

### 15.6 Testing
Handlers are tested with fake `Update` / `Context` objects and a fake backend client; no real Telegram calls. Assert: `callback_data` ≤ 64 bytes, album debounce sends a single reply, PDFs are rejected, voice over `MAX_VOICE_SECONDS` is rejected before download. Before the demo, do a manual live smoke test against a dev bot token.

---

## 16. Frontend (`frontend/` — Next.js + Tailwind, web only)

- **Citizen intake `/` (fallback channel):** language select, consent checkbox, record voice (MediaRecorder) or type text, upload document photos, submit. Uses the same API sequence as the bot: `POST /cases` → `/voice` or `/text` → `/documents` → `/start`.
- **Case status `/case/[id]`:** live timeline (SSE, sanitized events), current status, localized messages, **answer pending questions** (`NEEDS_INFO`), and **upload missing documents** (`POST /documents` then `/start`).
- **Reviewer queue `/reviewer`** and **evidence view `/reviewer/[id]`:** document thumbnails, extracted facts with source + grounded badge, rule trace (pass/fail/unknown), the agent's attempted fixes, approve / reject / request docs, edit-fact field.
- **Audit `/audit/[id]`:** reviewer only. Chronological events: who/what, why, evidence, confidence, outcome.
- Reviewer access: the reviewer enters the demo password, sent as `X-Reviewer-Token`. Supabase Auth only if time remains.
- Mask Aadhaar numbers to the last 4 digits everywhere in the UI by default.

---

## 17. Privacy, consent, safety

- Mock/synthetic data only in the repo, logs, prompts and tests. `data/real/` is gitignored. Synthetic documents carry the visible SAMPLE mark (§11).
- **Consent first:** the Telegram consent button / web checkbox must be accepted before any upload; store `consent_at` on the case. The bot states that Telegram chats are not end-to-end encrypted.
- **Delete my data:** `/delete` in the bot (and a web button) calls `DELETE /cases/{id}`: removes stored files, OCR text and facts. Audit events remain, but their evidence is redacted by design (§5).
- Data minimization: store only the facts rules and the portal payload need; `scripts/purge.py` (also callable as `purge_expired()`) auto-deletes uploaded files after `RETENTION_DAYS` (demo: 7).
- The bot deletes the citizen's document messages from the chat after ingest (best effort).
- Mask identifiers in logs, messages and UI; never log raw OCR text of IDs at INFO level.
- Files live in a private bucket/dir and are served only via short-lived signed URLs, and only to reviewers.
- Secrets (`TELEGRAM_BOT_TOKEN`, API keys, tokens) come from environment variables, are never committed, and never appear in logs or agent memory.
- Pitch note: production use requires authorization from scheme authorities, compliance with the DPDP Act and Aadhaar usage rules, and real portal integrations. State this as future work.

---

## 18. Config (`.env.example`)

```
# --- shared ---
ENV=dev                         # dev | prod  (dev enables /dev/* endpoints)
DEMO_MODE=live                  # live | offline
SERVICE_TOKEN=change-me         # shared secret between telegram_bot and backend

# --- backend ---
DATABASE_URL=postgresql+psycopg://adhikaar:adhikaar@localhost:5432/adhikaar
SARVAM_API_KEY=
LLM_PROVIDER=                   # e.g. sarvam | gemini | openai
LLM_API_KEY=
LLM_MODEL=
STORAGE_BACKEND=local           # local | supabase
SUPABASE_URL=                   # only if STORAGE_BACKEND=supabase
SUPABASE_SERVICE_KEY=
CHROMA_PATH=./.chroma
CLASSIFIER_WEIGHTS_PATH=./ml_training/weights/doc_classifier.pt
MOCK_PORTAL_URL=http://localhost:8100
BOT_INTERNAL_URL=http://localhost:8200
AUTO_SUBMIT_THRESHOLD=0.85
REVIEW_THRESHOLD=0.60
MAX_VOICE_SECONDS=30            # confirm against current Sarvam limits
MAX_UPLOAD_MB=10
MAX_DOCS_PER_CASE=8
RETENTION_DAYS=7
REVIEWER_PASSWORD=change-me

# --- telegram_bot ---
TELEGRAM_BOT_TOKEN=             # from @BotFather; never commit
TELEGRAM_MODE=polling           # polling | webhook
TELEGRAM_WEBHOOK_URL=
TELEGRAM_WEBHOOK_SECRET=
BACKEND_URL=http://localhost:8000

# --- frontend ---
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

---

## 19. Testing (pytest)

- **Rules engine:** table-driven; eligible / not eligible / undetermined; trace contents; malicious expression rejected by `simpleeval`.
- **Grounding check:** matching, fuzzy matching, mismatched fact flagged.
- **Confidence + routing:** boundary values around both thresholds; `UNDETERMINED` never auto-submits; human approval never overrides `NOT_ELIGIBLE`; re-upload requested at most once per document; at most 3 questions.
- **Audit:** every node emits an event; audit table is append-only; audit evidence contains no raw ID numbers.
- **Graph e2e with fakes** — all demo scenarios (§20) as automated tests, including resume after `NEEDS_DOCUMENTS` and `NEEDS_INFO`.
- **Explain guard:** explanation does not contradict the decision; no unmasked IDs.
- **API:** TestClient for the full case sequence (create → voice/text → documents → start → answers), reviewer resume, reviewer/service token enforcement, `/cases/active` route ordering, SSE sanitization, `DELETE` redaction.
- **Mock portal:** missing-field 422, `timeout`, `reject_permanent`.
- **Telegram bot:** see §15.6.
- No real network calls in tests.

---

## 20. Demo scenarios (acceptance targets)

| ID | Scenario | Expected |
|---|---|---|
| **A** | Tamil voice note: "I'm a farmer, I want PM-Kisan, nobody in my family pays income tax" + valid Aadhaar, land record, passbook | Classified, facts grounded, `ELIGIBLE`, confidence ≥ auto-submit threshold, auto-submitted, localized confirmation with portal reference, full audit |
| **B** | Same, but land record missing | `NEEDS_DOCUMENTS`; Tamil message names the missing document; **no submission**. Citizen sends the land record → case resumes → submitted |
| **C** | Land record photo is blurry but legible | Confidence in the review band → escalated; reviewer sees evidence, approves (or edits a fact) → submitted |
| **D1** | Fixture where first-pass extraction omits `bank_ifsc` | Portal rejects with `missing_field` → targeted re-extraction recovers the field → resubmit → success |
| **D2** | Mock portal set to `reject_permanent` (variant: `timeout` until retries are exhausted) | Permanent rejection escalates immediately; timeout variant retries then escalates; both with an explanation of what was tried |
| **E** | Voice note doesn't mention tax status | Agent asks one Yes/No question through inline buttons → citizen taps → case resumes → auto-submitted |

Scenarios **C**, **D2** and **E** are the money shots: C and D2 prove RECOVER / ESCALATE; E proves the agent asks for what it lacks instead of guessing.

**Live demo channel:** A, B, C and E run through the Telegram bot. D1 and D2 run through `scripts/run_demo.py`, which flips the mock portal's `fail_mode` and shows the outcome in the reviewer dashboard. The web form is the fallback if Telegram or the network fails.

---

## 21. Build phases

Build the **walking skeleton first** (Phase 3 with fakes) so something runs end to end early; swap in real integrations after.

Each phase ends with: tests green, short report, stop and wait for "go".

### Phase 0 — Scaffold
- [ ] Create the exact folder layout from §4 (`frontend/`, `backend/`, `telegram_bot/`, `mock_portal/`, `ml_training/`, `data/`, `scripts/`, `docs/`), each with its own deps/Dockerfile; `docker-compose.yml` (Postgres + services), `.env.example` (§18), Makefile, ruff, pytest.
- [ ] FastAPI `/health` (backend, mock_portal, telegram_bot), Next.js skeleton + Tailwind.
- **Accept:** `docker compose up` → all health endpoints OK; frontend loads; `make test` passes; folder tree matches §4.

### Phase 1 — Rules engine
- [ ] YAML loader + Pydantic validation, `simpleeval` evaluation, tri-state, rule trace.
- [ ] Both MOCK scheme files (with `payload_fields` and declaration `question`s).
- **Accept:** table-driven tests pass, including missing-fact → `UNDETERMINED` and injected-code rejection.

### Phase 2 — DB, audit, storage
- [ ] SQLAlchemy models (incl. `messages`, `channel`, `consent_at`) + Alembic migration; `audit.log()` + decorator with PII-safe evidence; storage interface + local backend; `purge_expired()`.
- **Accept:** audit append-only and no-raw-PII tests pass; round-trip file store/retrieve; purge test.

### Phase 3 — Agent graph with fakes (walking skeleton)
- [ ] `CaseState`, all nodes incl. `ask_info`, routing (§7.3), checkpointer, `interrupt` + resume, re-entry after `NEEDS_DOCUMENTS`; fakes for every integration incl. `FakeNotifier`.
- **Accept:** scenarios A, B, C, D1, D2, E pass as automated tests with fakes.

### Phase 4 — Real speech, OCR, LLM
- [ ] Sarvam STT/translate client (ffmpeg normalization, language-code mapping, duration limit), PaddleOCR client, LLM client with Pydantic-validated extraction + targeted re-extraction, grounding check.
- [ ] Record fixtures into `data/fixtures/` for offline mode.
- **Accept:** sample voice + docs produce expected facts live and via fixtures.

### Phase 5 — Document classifier
- [ ] Synthetic data generator (with SAMPLE mark), training script, eval report, `classifier.py`, wire into `classify_docs`.
- **Accept:** report committed; ≥ 90% held-out synthetic accuracy (or heuristic fallback wired with the same interface).

### Phase 6 — RAG
- [ ] Ingest rulebooks, retriever, use in `plan` and `explain` (with citations).
- **Accept:** a free-text need retrieves the right scheme in the top 2; explanation cites rulebook source.

### Phase 7 — Mock portal + recovery
- [ ] Portal with required-field validation and `/dev/config` fail modes; real `portal_client`; retry / auto-fix / permanent-reject / escalate logic (§9).
- **Accept:** D1 and D2 pass against the real mock portal.

### Phase 8 — Backend API + web UI
- [ ] All endpoints in §14 (incremental case API, answers, `DELETE`, reviewer + service token auth, sanitized SSE); `Notifier` interface + `NoopNotifier`.
- [ ] Citizen, reviewer and audit pages (§16).
- **Accept:** scenarios C and E runnable by hand through the web UI; API tests pass.

### Phase 9 — Telegram bot
- [ ] `telegram_bot/` per §15: onboarding, voice/text/photo handlers, album debounce, `/internal/notify`, inline-keyboard questions, `/status`, `/delete`, i18n strings; `TelegramNotifier` in the backend.
- **Accept:** handler tests pass with fakes; scenarios A, B, C, E run end to end through a real dev bot.

### Phase 10 — Demo polish
- [ ] `make seed`, `make demo` / `scripts/run_demo.py` (scenarios A–E), `DEMO_MODE=offline` for the web path, README with run steps, final thresholds recorded in `docs/`, deploy.
- **Accept:** a cold start → full demo in under 5 minutes; web path works offline; Telegram path works online.

---

## 22. Rules for the coding agent

1. Read this file fully before coding. It outranks your instincts.
2. One phase at a time. Finish, run tests, report, stop. Don't start the next phase uninvited.
3. The LLM never decides eligibility. Don't route around the rules engine.
4. Every node emits an audit event.
5. All external calls go through interfaces; tests use fakes; no network in tests.
6. Never fabricate scheme rules. Mock rules are labeled `MOCK`.
7. No real personal data anywhere. Synthetic only. Never log, echo or store secrets or raw ID numbers.
8. No new frameworks or refactors outside the stack in §3. Respect the folder layout in §4: every file goes in its concern's folder; no cross-folder imports except those allowed under "Folder rules".
9. The Telegram bot stays a thin client (§15.1): no business logic in `telegram_bot/`.
10. Type hints, small functions, descriptive names; commit after each logical step with a clear message.
11. If blocked: ask **one** question and state your recommended default.

**Report format after each phase (≤ 10 lines):** DONE · TESTS (what ran, result) · RISKS · NEXT (awaiting go).
