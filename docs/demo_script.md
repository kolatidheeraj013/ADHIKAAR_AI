# ADHIKAAR — 5-Minute Live Presentation & Demo Script (DC-04, DM-07)

**Presenter:** Dheeraj (ADHIKAAR AI)  
**Target Time:** Exactly 4:30 – 5:00 minutes  
**Display Layout:** Split Screen  
- **Left Window:** Mobile screen mirror or Telegram Web running `@adhikaar013bot`.  
- **Right Window:** Web Browser showing Reviewer Dashboard (`http://localhost:3000/reviewer`) & Audit Timeline.  
- **Backup Path:** Offline Web Form (`http://localhost:3000`) ready with pre-loaded mock fixtures.

---

## Pitch & Demonstration Timeline

### 0:00 – 1:00 | The Problem & Real Multi-Modal Citizen Input (Stage 1: INPUT)
- **Talking Points:**
  - *"Judges, ₹1.5 lakh crore in Indian welfare funds goes unclaimed every year—not because citizens don't qualify, but because rural citizens face a 15-day paper maze of complex forms, long queues at CSCs, and language barriers."*
  - *"Existing platforms like myScheme are static search directories—they tell you a scheme exists, but do not act. ADHIKAAR is an autonomous entitlement agent."*
- **Action on Screen (Telegram Bot):**
  - Type `/start` on Telegram bot `@adhikaar013bot`.
  - Show privacy consent modal -> Tap **Accept & Continue**.
  - Tap **தமிழ் (Tamil)** or **English**.
  - Send sample voice note (`data/samples/voice_sample_ta.wav`): *"நான் ஒரு விவசாயி, எனக்கு PM-Kisan வேண்டும், என் குடும்பத்தில் யாரும் வருமான வரி செலுத்துவதில்லை."*
  - Upload sample documents from `data/samples/`: `aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png`.
  - Tap **Done**.
- **Rubric Stage:** `INPUT` — Real Telegram ingestion, native voice notes, camera document photos, multi-lingual onboarding.

---

### 1:00 – 2:00 | Multi-Modal Tool Loop & Autonomous Action (Stages 2–5: UNDERSTAND -> PLAN -> USE TOOLS -> ACT)
- **Talking Points:**
  - *"Notice what is happening autonomously right now in the background. The agent is executing a 20-node LangGraph state machine."*
  - *"Sarvam AI transcribes Tamil speech. Our transfer-learned ResNet-18 model classifies document types and checks image quality. Multi-lingual PaddleOCR extracts text lines with confidence scores."*
  - *"Here is our core architectural invariant: **The LLM never decides eligibility.** An LLM extracts facts and checks grounding. But eligibility is computed 100% deterministically by `simpleeval` over versioned government rules."*
- **Action on Screen:**
  - Citizen receives immediate Telegram notification:
    - *"Eligibility Confirmed: 1.4 Hectares cultivable land verified · Non-taxpayer declaration recorded · Scheme: PM-Kisan (MOCK)."*
    - *"Application Submitted! Portal Reference: MOCK-PORTAL-0001."*
  - Switch to Right Screen (Reviewer Dashboard): Show the case instantly appear under **Submitted Applications** with full audit events.
- **Rubric Stages:** `UNDERSTAND`, `PLAN`, `USE TOOLS`, `ACT` — ASR, ResNet-18 classifier, PaddleOCR, ChromaDB RAG, simpleeval rules engine, and portal API execution.

---

### 2:00 – 3:00 | Recovery & Clarification (Stages 6–7: VERIFY -> RECOVER)
- **Talking Points:**
  - *"Real welfare systems have messy data. What happens when a field is missing or ambiguous? Chatbots hallucinate or crash. ADHIKAAR has closed-loop recovery."*
- **Demo Scenario D1 (Auto-Recovery):**
  - Upload `passbook_missing_ifsc.png` where primary OCR missed the branch code.
  - Show agent log: Portal returns 422 `missing_field: bank_ifsc`.
  - Agent automatically triggers targeted re-extraction on the passbook image, finds `SBIN0004128`, auto-repairs payload, and re-submits without bothering the citizen.
- **Demo Scenario E (Interactive Clarification):**
  - Show a citizen who didn't state their tax payer status in voice.
  - The agent pauses with `interrupt()`, generating single-tap inline buttons on Telegram:
    - *"Does anyone in your family pay income tax? [Yes] [No]"*
  - Tap **[No]** -> Agent resumes seamlessly, evaluates rule, and submits.
- **Rubric Stages:** `VERIFY`, `RECOVER` — Automated 422 recovery, targeted re-extraction, interactive inline button clarifications.

---

### 3:00 – 4:00 | Human-in-the-Loop Reviewer Queue (Stage 8: ESCALATE)
- **Talking Points:**
  - *"When an autonomous agent is unsure, it must never guess. It must safely escalate to a human reviewer."*
- **Demo Scenario C (Blurry Land Record):**
  - Upload `land_record_blurry.png` (simulating camera glare / low light).
  - ResNet-18 flags quality as `blurry` (confidence < 0.60).
  - Agent halts auto-submission and pushes case to the Reviewer Dashboard.
- **Action on Right Screen (Reviewer Dashboard):**
  - Refresh Reviewer Queue: Case `EVAL-C-01` appears under **Pending Review**.
  - Click into the case: Show side-by-side evidence view:
    - Document image thumbnail with watermark `SAMPLE — NOT A REAL DOCUMENT`.
    - Pydantic extracted facts with **Grounded** badges.
    - Rule trace: `owns_land: unknown (low quality document)`.
  - Reviewer edits extent to `1.4 Hectares`, clicks **Approve & Resume**.
  - Watch Telegram bot immediately deliver approved confirmation and portal reference to the citizen!
- **Rubric Stage:** `ESCALATE` — Human-in-the-loop review, fact editing, secure token access, resumed graph execution.

---

### 4:00 – 4:45 | Post-Submission Tracking, SLA Escalation & Privacy (Audit Trail)
- **Talking Points:**
  - *"Closing the loop doesn't stop at submission. ADHIKAAR tracks the application against the portal SLA."*
- **Action on Screen:**
  - Trigger tracking check: Portal simulated stall (45 days pending).
  - Agent detects SLA breach -> automatically flags application for reviewer follow-up and sends citizen a localized reassuring notification.
  - Show **Audit Timeline**: Append-only log of every node execution, latency in milliseconds, masked PII (XXXX-XXXX-8942), and zero plain-text leaks.
  - Show DPDP Compliance: Citizen sends `/delete` -> all document photos, OCR cache, and facts are purged immediately, keeping only an immutable audit hash.

---

### 4:45 – 5:00 | Conclusion & Impact Summary
- **Talking Points:**
  - *"To summarize: ADHIKAAR bridges the ₹1.5 lakh crore welfare gap by turning passive government websites into an active, multi-lingual autonomous agent."*
  - *"Proven in our evaluation suite with 100% rule accuracy, sub-250ms average latency, and 15 days of citizen paperwork saved per application."*
  - *"Thank you, judges. We are ready for questions!"*

---

## Presenter Checklist & Emergency Backups

| Potential Issue | Immediate Fallback |
|---|---|
| Telegram API delayed or cellular network jitter | Switch immediately to Web Fallback at `http://localhost:3000` (runs fully offline) |
| Audio playback muted on projector | Point to live English transcript shown in the Reviewer Dashboard |
| Mock portal process stopped | Run `uv run uvicorn mock_portal.app.main:app --port 8100` |
| Resetting between judges | Run `uv run python scripts/run_demo.py` or clear chat in Telegram |
