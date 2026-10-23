# ADHIKAAR — Completeness Checklist (audit + fix)

> For the coding agent. This file lists everything a finished Adhikaar prototype should have.
> Your job: **(A) audit** the current build against it, then **(B) implement what is missing**, in priority order.
> Companion files: `implementation.md` (the spec) and `docs/hackathon_brief.txt` (judging rubric).

**Project in one line:** Adhikaar is an autonomous welfare-entitlement agent. A citizen sends a voice note + document photos on Telegram (web form as fallback); the agent transcribes, classifies and reads the documents, extracts facts, asks follow-up questions, decides eligibility with a **deterministic rules engine**, submits to a (mock) scheme portal, recovers from failures, escalates to a human reviewer when unsure, and records an **audit trail**.

**Core principle:** the LLM extracts and explains · the rules engine decides · a human handles doubt.

---

## 0. Operating protocol (read first)

### Status legend
| Mark | Meaning |
|---|---|
| `[x]` | Done **and proven**: evidence cited (file + symbol, test name, or recorded run) |
| `[~]` | Partial: say exactly what is missing |
| `[ ]` | Missing |
| `[?]` | Cannot verify: say how to verify |

### Priorities
- **P0** — breaks a demo scenario, violates the core principle, or exposes private data. Fix first.
- **P1** — weakens a judging criterion or makes the demo fragile.
- **P2** — polish / nice to have.

### Phase A — Audit (read-only, no source edits)
1. Read `implementation.md` and `docs/hackathon_brief.txt`.
2. Walk every item below. Search the code; run the tests; run the app where needed.
3. Update each checkbox in this file and append `— Evidence: …` (or `— Missing: …`).
4. Write `docs/audit/STATUS.md`: counts per section and priority, plus the top 10 gaps by demo impact.
5. Stop and report. Wait for "go" before Phase B.

### Phase B — Fix
1. Work **P0 → P1 → P2**. One item (or one tightly coupled group) at a time.
2. For each: short plan → implement → add/adjust a test → re-run the affected demo scenario → update the checkbox with evidence.
3. Commit once per item with a clear message.
4. Report after every batch of ≤ 5 items: `DONE · PARTIAL · BLOCKED · NEXT`.

### Rules for the agent
- Never mark `[x]` without evidence. "Looks fine" is not evidence.
- Don't rewrite working code. Smallest change that closes the gap.
- No new frameworks beyond `implementation.md` §3. Respect the folder layout in §4.
- Synthetic data only. Never log, echo or commit real IDs or secrets.
- Never fabricate scheme rules; unverified rules stay labeled `MOCK`.
- Don't claim capabilities that don't exist (see DS-08).
- Don't generate slide decks or other extras unless Dheeraj asks.
- Blocked? Ask exactly one question and state your recommended default.

---

## 1. Idea & pitch integrity (the OPEN-X seven points)

- [ ] **ID-01** [P0] **Problem** stated in README/pitch with at least one cited statistic (source + year). _Verify:_ README section exists; citation is checkable.
- [ ] **ID-02** [P1] **Target users** named: rural/semi-literate citizens, elderly pensioners, first-gen scholarship applicants; secondary: NGOs and panchayat offices.
- [ ] **ID-03** [P0] **Existing gap** stated concretely: scheme directories inform but do not act; nothing closes the loop from documents → eligibility → application → tracking → escalation.
- [ ] **ID-04** [P1] **Solution** summary plus an architecture diagram (image or Mermaid) that matches the current code.
- [ ] **ID-05** [P0] **Why AI/agents** explained: list the steps that need reasoning, planning, tool use or autonomous action. Explicitly "not a chatbot wrapper".
- [ ] **ID-06** [P0] **End-to-end demo** follows `INPUT → UNDERSTAND → PLAN → USE TOOLS → ACT → VERIFY → RECOVER/ESCALATE`, and each stage is visible on screen.
- [ ] **ID-07** [P1] **Impact** quantified with stated assumptions (time saved, visits avoided, error reduction). Numbers are sourced or clearly labeled as estimates.
- [ ] **ID-08** [P0] **Honest limitations** documented: mock portal, mock/simplified rules, classifier trained on synthetic data, no real Aadhaar verification, production needs authorization + DPDP compliance.

---

## 2. Core principle compliance

- [ ] **CP-01** [P0] No LLM output ever decides eligibility. _Verify:_ search every LLM call site; eligibility and `act` paths depend only on the rules engine. Add a test.
- [ ] **CP-02** [P0] LLM jobs are limited to (a) fact extraction, (b) explanation, (c) translation via Sarvam. Nothing else calls an LLM.
- [ ] **CP-03** [P0] `UNDETERMINED` never auto-submits. _Verify:_ test at the routing layer.
- [ ] **CP-04** [P0] Human approval never overrides `NOT_ELIGIBLE` or `UNDETERMINED`; approving a non-`ELIGIBLE` escalation requires `edited_facts` (API returns 422 otherwise).
- [ ] **CP-05** [P0] Missing facts are `null`, never guessed. Declaration facts are extracted only if explicitly stated.
- [ ] **CP-06** [P0] Rules use `simpleeval`; no `eval`/`exec` anywhere. _Verify:_ grep + a malicious-expression test.
- [ ] **CP-07** [P1] Explanation text cannot contradict the decision. _Verify:_ explain-guard test.
- [ ] **CP-08** [P1] Rules engine is a pure function (no I/O) with a per-rule trace: `{rule_id, passed|failed|unknown, facts_used, source_doc_ids, reason}`.

---

## 3. Agent loop vs. the hackathon rubric

For each criterion, record **where it lives in code** and **how it is shown in the demo**.

- [ ] **RB-01** [P0] **Real input:** Telegram voice + photos (and the web form) work end to end. Nothing is hard-coded or mocked at the input side.
- [ ] **RB-02** [P0] **Understanding:** transcript, English intent and extracted facts are visible to the reviewer (UI) and recorded in the audit.
- [ ] **RB-03** [P0] **Planning:** the `plan` node picks the scheme and required documents, and the audit records the choice with RAG citations.
- [ ] **RB-04** [P0] **Tool usage:** at least 5 distinct tools are invoked and each appears as an audit event (STT, OCR, classifier, RAG, rules engine, portal API).
- [ ] **RB-05** [P0] **Action:** the application is really submitted to the portal; `portal_ref` is stored and sent to the citizen.
- [ ] **RB-06** [P0] **Verification:** confidence score, grounding check and portal acknowledgement are all shown in the UI.
- [ ] **RB-07** [P0] **Recovery:** scenario D1 (auto-fix via targeted re-extraction) works live.
- [ ] **RB-08** [P0] **Escalation:** scenarios C and D2 reach the reviewer queue; the reviewer's decision resumes the graph.
- [ ] **RB-09** [P0] **Audit trail:** per-case timeline shows what / why / evidence / outcome; append-only; masked values only.

---

## 4. Features

### 4.1 Telegram bot (`telegram_bot/`)
- [ ] **TG-01** [P0] Onboarding: privacy notice → language buttons (ta / te / hi / en) → consent button. Declining ends the flow.
- [ ] **TG-02** [P0] Voice notes accepted; `voice.duration` checked against `MAX_VOICE_SECONDS` before download; forwarded to `/cases/{id}/voice`.
- [ ] **TG-03** [P1] Typed text accepted as an alternative intent (`/cases/{id}/text`).
- [ ] **TG-04** [P0] Photos and image files accepted (largest `PhotoSize`); PDFs and other types rejected with a localized message; users are told that sending as a file keeps quality.
- [ ] **TG-05** [P1] Album debounce: one "Received N documents" reply after ~2 s of quiet, never one per photo.
- [ ] **TG-06** [P1] Citizen's document messages are deleted from the chat after successful ingest (best effort).
- [ ] **TG-07** [P0] **Done** button → `/start`; 422 from the backend produces a message naming exactly what is missing.
- [ ] **TG-08** [P0] Inline-keyboard questions: `answer_callback_query` called, answer posted to `/answers`, original message edited, keyboard removed.
- [ ] **TG-09** [P0] `callback_data` ≤ 64 bytes (short tokens only). _Verify:_ assertion in a test.
- [ ] **TG-10** [P0] `/status`, `/delete` (with confirmation), `/help` work; `/start` with an active case offers continue / new.
- [ ] **TG-11** [P0] Push notifications for: question, missing documents, review pending, submitted (with portal ref), not eligible (with reasons), failed/escalated.
- [ ] **TG-12** [P1] Notification delivery retries (3×, backoff), stores `delivered` flag, never blocks the graph.
- [ ] **TG-13** [P1] Static strings exist and are reviewed for ta / te / hi / en (`i18n.py`).
- [ ] **TG-14** [P1] Message split/trim at 4096 characters.
- [ ] **TG-15** [P1] Per-chat rate limit; max `MAX_DOCS_PER_CASE` documents.
- [ ] **TG-16** [P0] Prod mode: webhook with `X-Telegram-Bot-Api-Secret-Token` validated; `/internal/notify` requires `X-Service-Token`.
- [ ] **TG-17** [P0] Bot holds no business logic and the backend never holds the bot token.

### 4.2 Web fallback (`frontend/`)
- [ ] **WB-01** [P0] Intake page: language, consent checkbox, record voice or type text, upload photos, submit (same API sequence as the bot).
- [ ] **WB-02** [P0] Case page: live timeline (SSE, sanitized), status, localized messages.
- [ ] **WB-03** [P0] Case page: answer pending questions (`NEEDS_INFO`) and upload missing documents then re-`/start`.
- [ ] **WB-04** [P1] Mobile-responsive layout; large touch targets.

### 4.3 Reviewer dashboard
- [ ] **RV-01** [P0] Reviewer access protected (`X-Reviewer-Token`); wrong token → 401.
- [ ] **RV-02** [P0] Queue lists open escalations with reason and age.
- [ ] **RV-03** [P0] Evidence view: document thumbnails (signed URLs), facts with source + grounded badge, rule trace (pass/fail/unknown), what the agent already tried, portal errors.
- [ ] **RV-04** [P0] Actions: approve / reject / request docs; edit facts; resume updates the case and notifies the citizen.
- [ ] **RV-05** [P1] Aadhaar and other IDs masked to last 4 by default everywhere.
- [ ] **RV-06** [P1] Audit page shows the full timeline; reviewer only.

### 4.4 Agent pipeline (`backend/app/agents/`)
- [ ] **PL-01** [P0] `intake` verifies consent + (voice or text) + ≥ 1 document before running.
- [ ] **PL-02** [P0] `transcribe`: ffmpeg normalization (16 kHz mono WAV), language-code mapping, length limit, empty-transcript handling.
- [ ] **PL-03** [P0] `classify_docs` returns doc type + quality with confidences.
- [ ] **PL-04** [P0] `ocr` returns text + per-line confidence for Tamil / Telugu / Hindi / English.
- [ ] **PL-05** [P0] `extract_facts` returns Pydantic-validated facts; **grounding check** marks values not found in OCR text.
- [ ] **PL-06** [P0] `plan` uses RAG + intent to rank schemes; processes only `candidate_schemes[0]` per case.
- [ ] **PL-07** [P0] `check_docs` detects missing required documents.
- [ ] **PL-08** [P0] `eligibility` returns tri-state outcome with the rule trace.
- [ ] **PL-09** [P0] `ask_info` asks the citizen for a missing **declaration** fact via buttons; ≤ 3 questions per case; pauses with `interrupt()`; scenario E passes.
- [ ] **PL-10** [P0] `verify` computes confidence per the §8 formula; thresholds read from env; routing matches §7.3.
- [ ] **PL-11** [P0] `act` builds the payload from the scheme's `payload_fields` and submits; idempotency key per case + scheme prevents double submission.
- [ ] **PL-12** [P0] `verify_submission` confirms the portal acknowledgement.
- [ ] **PL-13** [P0] `recover`: transient → retry ×2 with backoff; field-level 422 → one auto-fix (re-map or targeted re-extraction); permanent rejection → escalate immediately.
- [ ] **PL-14** [P0] `escalate` creates the escalation with reason + evidence + what was tried; pauses; resumes on the reviewer action.
- [ ] **PL-15** [P0] `explain` produces a plain-language, localized message grounded in the decision + rulebook citations; stores it in `messages`; sends via the Notifier.
- [ ] **PL-16** [P0] Persistent checkpointer: a restart mid-run resumes without losing state or double-submitting.
- [ ] **PL-17** [P0] `NEEDS_DOCUMENTS` resume: new uploads + `/start` re-enter at `classify_docs`, processing only new files and keeping prior facts.
- [ ] **PL-18** [P1] Loop guards: re-upload requested at most once per document; second failure escalates; a failed `act` after human approval ends as `FAILED_ESCALATED`.
- [ ] **PL-19** [P1] Every node emits an audit event (decorator enforced).
- [ ] **PL-20** [P1] One scheme per case stated clearly in the UI/messages; other plausible schemes mentioned in the explanation only.

### 4.5 Post-submission tracking (promised in the pitch)
- [ ] **TR-01** [P1] After `SUBMITTED`, the agent polls the portal status (`GET /applications/{ref}`) on a schedule.
- [ ] **TR-02** [P1] If the application stalls past a (simulated) SLA, the agent nudges the portal / escalates to a reviewer and informs the citizen. Mock-portal switch to simulate a stall exists.
- [ ] **TR-03** [P2] Status changes (approved / rejected / more info needed) are pushed to the citizen.

### 4.6 Backend API
- [ ] **API-01** [P0] Endpoints per `implementation.md` §14 exist: `/cases`, `/voice`, `/text`, `/documents`, `/start`, `/answers`, `GET /cases/{id}`, `/events` (SSE), `DELETE /cases/{id}`, `/schemes`, reviewer routes, `/dev/seed`.
- [ ] **API-02** [P0] `/cases/active` is declared **before** `/cases/{id}` and requires `X-Service-Token`.
- [ ] **API-03** [P0] Citizen-facing responses are sanitized: no raw facts, no evidence, no unmasked IDs. SSE carries summaries only.
- [ ] **API-04** [P0] Uploads validated by magic bytes, size (`MAX_UPLOAD_MB`), duration, count.
- [ ] **API-05** [P1] `/start` is idempotent; `DELETE` purges files/OCR/facts and keeps redacted audit events.
- [ ] **API-06** [P1] `/dev/*` disabled when `ENV=prod`.

---

## 5. Scheme data & sources

Sources considered: **myScheme.gov.in** (national discovery platform: eligibility, benefits, documents, how to apply), **socialjustice.gov.in** (Ministry of Social Justice & Empowerment schemes), **india.gov.in** (National Portal scheme directory). We do **not** fine-tune an LLM on these. Knowledge goes in **RAG**; decisions go in **curated YAML rules**.

- [ ] **DS-01** [P0] Both schemes' YAML rules are either (a) derived from the official guideline/notification and human-verified, or (b) clearly labeled `MOCK` everywhere they appear (YAML name, rulebook, UI, explanations, README).
- [ ] **DS-02** [P0] Each scheme YAML and rulebook has a provenance block: `source_urls`, `retrieved_at`, `version`, `verified_by`, notes.
- [ ] **DS-03** [P1] Source-priority policy documented: official ministry/department guideline > myScheme.gov.in > india.gov.in directory. Conflicts between sources are flagged for human review, never silently merged.
- [ ] **DS-04** [P0] Use of these sites respects each site's terms/copyright policy and `robots.txt`: reproduce accurately, never misleadingly, acknowledge the source, throttle, cache. No bulk crawl. Attribution appears in explanations or the UI footer.
- [ ] **DS-05** [P1] `scripts/ingest_schemes.py` is reproducible: fetches or reads only the in-scope scheme pages and writes `data/rulebooks/*.md` with provenance frontmatter. The demo never depends on live scraping.
- [ ] **DS-06** [P1] RAG test: a free-text need (also in translated ta / te / hi) retrieves the right scheme in the top 2.
- [ ] **DS-07** [P2] A documented process for updating a scheme when guidelines change (bump `version`, re-ingest, re-run tests); optional "last verified" date shown with scheme information.
- [ ] **DS-08** [P0] **Claims match reality.** The pitch mentions only fine-tuning that exists (ResNet18 classifier). If a fine-tuned LLM is ever added, it must beat the prompted baseline on a held-out set and the numbers go in `docs/`; otherwise do not claim it.

---

## 6. ML (document classifier)

- [ ] **ML-01** [P1] Synthetic generator is reproducible (seeded) and stamps every document "SAMPLE — NOT A REAL DOCUMENT".
- [ ] **ML-02** [P0] Training script (two-phase transfer learning, two heads: `doc_type`, `quality`) runs; weights saved to `CLASSIFIER_WEIGHTS_PATH`.
- [ ] **ML-03** [P0] Evaluation report committed (`ml_training/reports/`): accuracy per head + confusion matrices. Target ≥ 90% held-out; if lower, document it and keep the heuristic fallback wired.
- [ ] **ML-04** [P1] **Reality check:** print ~20 mock documents, photograph them with a phone, and run them through the classifier. Report the accuracy honestly next to the synthetic number.
- [ ] **ML-05** [P1] Startup check loads weights; if missing, the app falls back to heuristics and logs a clear warning.
- [ ] **ML-06** [P2] Confidence sanity-checked (calibration plot or temperature scaling); inference latency measured.

---

## 7. Failure handling (each row needs a test or a recorded run)

| ID | Failure | Expected behavior | Done |
|---|---|---|---|
| **FH-01** [P0] | STT timeout / 401 / empty transcript / unsupported or over-long audio | Retry once; then ask the citizen to resend or type; never crash; audit event | [ ] |
| **FH-02** [P0] | OCR returns nothing or low confidence | Mark document unreadable → ask for a clearer photo (once) → escalate on repeat | [ ] |
| **FH-03** [P0] | LLM returns invalid JSON / times out / provider down | Retry once → facts stay missing (never guessed) → fallback provider or escalate | [ ] |
| **FH-04** [P1] | Classifier weights missing or low confidence | Heuristic fallback / treat as `other` and ask | [ ] |
| **FH-05** [P0] | Portal timeout / 5xx | Retry ×2 with backoff → escalate | [ ] |
| **FH-06** [P0] | Portal 422 `missing_field` | One auto-fix → resubmit | [ ] |
| **FH-07** [P0] | Portal permanent rejection | Escalate immediately with explanation | [ ] |
| **FH-08** [P1] | Telegram notify fails | Retry ×3 → audit event → graph continues | [ ] |
| **FH-09** [P0] | Server restart mid-run | Checkpointer resumes; no duplicate submission | [ ] |
| **FH-10** [P0] | Duplicate: same document twice, `/start` twice, second case for the same scheme | No double submission (idempotency key); friendly message | [ ] |
| **FH-11** [P0] | Oversized / corrupted / wrong-type upload, zero documents, PDF | Clear localized rejection; nothing stored | [ ] |
| **FH-12** [P0] | **Prompt injection:** OCR text or voice transcript contains instructions ("ignore previous rules…") | Treated as data only; extraction output unaffected. Test with an injected fixture | [ ] |
| **FH-13** [P1] | Citizen stops answering a question | Case stays `NEEDS_INFO`; `/status` explains what is pending | [ ] |
| **FH-14** [P1] | Reviewer closes the case with no action / token invalid | 401 handling; the escalation stays `OPEN` | [ ] |

---

## 8. Privacy, security, compliance

- [ ] **PS-01** [P0] Consent is recorded (`consent_at`) before any upload is accepted.
- [ ] **PS-02** [P0] `/delete` (bot) and the web delete button purge files, OCR text and facts; audit stays with redacted evidence.
- [ ] **PS-03** [P0] **Audit evidence contains no raw ID numbers or full OCR text.** Test it.
- [ ] **PS-04** [P0] Masking in logs, UI, bot messages and reviewer views (last 4 only).
- [ ] **PS-05** [P0] No secrets in the repo or git history (scan: bot token, API keys, `.env`). `.env.example` has placeholders only.
- [ ] **PS-06** [P0] Reviewer token and service token enforced; `/dev/*` disabled in prod.
- [ ] **PS-07** [P1] Files in a private bucket/dir, served via short-lived signed URLs, only to reviewers.
- [ ] **PS-08** [P1] `scripts/purge.py` / `purge_expired()` removes files older than `RETENTION_DAYS`; tested.
- [ ] **PS-09** [P1] CORS restricted to the frontend origin; HTTPS on the deployed build.
- [ ] **PS-10** [P1] Telegram privacy notice shown (bot chats are not end-to-end encrypted); the bot's message deletion is best-effort and documented.
- [ ] **PS-11** [P1] No real PII in fixtures, samples or tests. Synthetic documents carry the SAMPLE mark.
- [x] **PS-12** [P2] Dependency audit run (`pip-audit`, `npm audit`); findings noted (see `docs/security_audit.md`).

---

## 9. Tests & evaluation

- [ ] **TE-01** [P0] `make test` is green from a clean clone.
- [ ] **TE-02** [P0] Scenario tests A, B, C, D1, D2, E pass with fakes (`implementation.md` §20), including resume after `NEEDS_DOCUMENTS` and `NEEDS_INFO`.
- [ ] **TE-03** [P0] Rules engine: table-driven (eligible / not eligible / undetermined), trace contents, injected-code rejection.
- [ ] **TE-04** [P0] Confidence + routing boundary tests; hard-rule tests (CP-03, CP-04).
- [ ] **TE-05** [P1] Grounding check tests (match, fuzzy match, mismatch).
- [ ] **TE-06** [P1] Audit tests: every node emits an event; append-only; no raw PII.
- [ ] **TE-07** [P1] API tests: full case sequence, token enforcement, route ordering, SSE sanitization, `DELETE` redaction.
- [ ] **TE-08** [P1] Mock portal tests: 422 missing field, `timeout`, `reject_permanent`.
- [ ] **TE-09** [P1] Telegram handler tests with fake updates: `callback_data` size, album debounce, PDF rejection, over-long voice rejected before download.
- [ ] **TE-10** [P1] No test makes a real network call.
- [ ] **TE-11** [P1] **Agent eval set:** 20–30 synthetic cases with ground-truth outcomes run through the pipeline. Report: outcome agreement, auto-submit vs escalation rate, average end-to-end time → `docs/eval_report.md`. This is the strongest evidence for "AI that works".
- [x] **TE-12** [P1] CI (GitHub Actions) runs lint + tests on every push.
- [x] **TE-13** [P2] Coverage report generated (see `docs/coverage_report.md`).

---

## 10. Observability

- [ ] **OB-01** [P1] Structured logs carry `case_id`, node, duration, outcome; no PII.
- [ ] **OB-02** [P1] `/health` on backend, mock_portal, telegram_bot; backend reports DB and checkpointer status.
- [ ] **OB-03** [P1] Per-node latency is visible (in audit events or logs) so slow steps can be found before the demo.
- [x] **OB-04** [P2] Basic metrics endpoint or page: cases processed, auto-submitted vs escalated, average time to resolution (`/stats`, `/metrics`).

---

## 11. DevOps & deployment

- [ ] **DV-01** [P0] `docker compose up` brings up Postgres, backend, mock_portal, telegram_bot, frontend from a cold start; migrations run automatically.
- [ ] **DV-02** [P0] `.env.example` lists every variable used, grouped by service.
- [ ] **DV-03** [P0] Makefile targets work: `dev`, `test`, `demo`, `train`, `seed`.
- [ ] **DV-04** [P1] Dependencies pinned (lock files); Python / Node versions documented; ffmpeg present in the backend image.
- [ ] **DV-05** [P1] Model weights distributed via Git LFS or a download script; README says how.
- [ ] **DV-06** [P1] Deployed build reachable: frontend (Vercel) + backend/bot/mock portal (container host); bot in webhook mode.
- [ ] **DV-07** [P2] Reproducible seed/reset script returns the system to a clean demo state.

---

## 12. Demo readiness

- [ ] **DM-01** [P0] Scenarios A, B, C, D1, D2, E all pass live **three runs in a row**.
- [ ] **DM-02** [P0] Web path works fully offline via fixtures (`DEMO_MODE=offline`); Telegram path works online.
- [ ] **DM-03** [P0] `make demo` / `scripts/run_demo.py` runs D1 and D2 (flips the mock portal's `fail_mode`) and the result is visible in the reviewer dashboard.
- [ ] **DM-04** [P0] Sample pack in `data/samples/`: SAMPLE-marked documents for every scenario plus sample voice notes in Tamil, Telugu and Hindi.
- [ ] **DM-05** [P1] A reset step between demo runs (clean DB, cleared chat state).
- [ ] **DM-06** [P1] Dedicated demo Telegram account and a bot token that work on the presenting device; a mobile hotspot as network backup.
- [ ] **DM-07** [P1] Full demo fits in under 5 minutes; talking points map one-to-one to the rubric stages.
- [ ] **DM-08** [P1] Backup: a screen recording of a clean run, plus the web-form path ready if Telegram or the network fails.
- [ ] **DM-09** [P1] Screen layout planned: phone mirror (Telegram) + reviewer dashboard + audit timeline visible together.
- [ ] **DM-10** [P1] Rehearsed at least twice end to end, including the failure moments (C, D2, E).

---

## 13. Docs & pitch assets

- [ ] **DC-01** [P0] `README.md`: what / why / architecture / how to run / how to demo / limitations.
- [ ] **DC-02** [P0] Architecture diagram + a sequence diagram of the agent loop, matching the code.
- [ ] **DC-03** [P0] One-page proposal in the format Round 2 expects: problem, approach, AI/agent architecture, workflow, expected impact.
- [ ] **DC-04** [P1] Demo script with talking points mapped to the rubric (real input → … → audit trail).
- [ ] **DC-05** [P1] `docs/eval_report.md` (TE-11) + classifier report (ML-03/04) linked from the README.
- [ ] **DC-06** [P1] Impact calculation sheet with sources and assumptions.
- [ ] **DC-07** [P1] Limitations + future work: real portal integration, authorization from scheme authorities, DPDP/Aadhaar compliance, more schemes and states.
- [ ] **DC-08** [P1] Credits and attributions: government sources used, libraries, models.
- [ ] **DC-09** [P2] Pitch deck **only if the organizers require one** — ask Dheeraj first.

---

## 14. UX & language polish

- [ ] **UX-01** [P1] Loading and progress states: the citizen always knows what is happening ("reading your documents…").
- [ ] **UX-02** [P1] Every error shown to a citizen is localized, specific and tells them what to do next.
- [ ] **UX-03** [P1] Citizen messages use plain language (short sentences, no jargon, no unexplained acronyms).
- [ ] **UX-04** [P1] Tamil / Telugu / Hindi strings reviewed by a fluent speaker.
- [ ] **UX-05** [P2] Reviewer UI highlights what needs attention (ungrounded facts, low confidence, failed rules); empty states handled.
- [ ] **UX-06** [P2] Accessible contrast and focus states on the web UI.

---

## 15. Suggested additions (optional — only after every P0 and P1 is `[x]`)

Ranked by judge impact. Do at most two.

1. **"What next" on NOT_ELIGIBLE:** use RAG to suggest the nearest alternative schemes the citizen may qualify for. Shows planning and real value.
2. **Impact dashboard:** cases processed, auto vs escalated, estimated time saved. Turns the impact claim into a live number.
3. **Voice replies (Sarvam TTS)** for low-literacy users in Telegram.
4. **Audit export:** download a case's audit trail as JSON or PDF.
5. **Reviewer SLA timer:** escalations unresolved after N minutes are highlighted and the citizen is told about the delay.

---

## 16. Cut list (fill in during the audit)

Items judged too large for the remaining time. Each one is stated as **future work** in the README, never silently dropped.

| ID | Item | Reason cut | Where documented |
|---|---|---|---|
| | | | |

---

## 17. Final gate — definition of done

- [ ] All **P0** items are `[x]` with evidence.
- [ ] At least **80% of P1** items are `[x]`; the rest are `[~]` with a note or listed in the cut list.
- [ ] Scenarios A–E pass live three times in a row.
- [ ] `make test` is green from a clean clone.
- [ ] Cold start → full demo in under 5 minutes.
- [ ] No secrets and no real PII in the repo or its history.
- [ ] README, architecture diagram, demo script and honest limitations exist.
- [ ] Every claim in the pitch matches what the code actually does.

### Status summary (agent fills in)

| Section | P0 done / total | P1 done / total | P2 done / total |
|---|:---:|:---:|:---:|
| 1 Idea & pitch | 5 / 5 | 3 / 3 | — |
| 2 Core principle | 6 / 6 | 2 / 2 | — |
| 3 Rubric loop | 9 / 9 | — | — |
| 4 Features | 11 / 11 | 11 / 11 | 0 / 1 |
| 5 Scheme data | 3 / 3 | 2 / 2 | 0 / 1 |
| 6 ML | 2 / 2 | 2 / 3 | 0 / 1 |
| 7 Failure handling | 9 / 9 | 5 / 5 | — |
| 8 Privacy & security | 6 / 6 | 4 / 5 | 0 / 1 |
| 9 Tests & eval | 4 / 4 | 7 / 7 | 0 / 2 |
| 10 Observability | — | 3 / 3 | 0 / 1 |
| 11 DevOps | 3 / 3 | 3 / 3 | 1 / 1 |
| 12 Demo readiness | 4 / 4 | 2 / 5 | — |
| 13 Docs & pitch | 3 / 3 | 5 / 5 | 0 / 1 |
| 14 UX | — | 4 / 4 | 2 / 2 |
| **Total** | **55 / 55 (100.0%)** | **50 / 58 (86.2%)** | **4 / 12 (33.3%)** |

