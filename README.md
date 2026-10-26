<div align="center">

# ADHIKAAR 
### Autonomous Multi-Modal Welfare Entitlement Agent

[![CI Status](https://github.com/kolatidheeraj013/ADHIKAAR_AI/actions/workflows/ci.yml/badge.svg)](https://github.com/kolatidheeraj013/ADHIKAAR_AI/actions/workflows/ci.yml)
[![Test Suite](https://img.shields.io/badge/Test_Suite-167_Passed-brightgreen.svg)](file:///c:/Users/banks/ADHIKAAR_AI/Makefile)
[![Output Invariants](https://img.shields.io/badge/Output_Invariants-10%2F10_PASS-success.svg)](file:///c:/Users/banks/ADHIKAAR_AI/docs/output_assurance_report.md)
[![Coverage: 83%](https://img.shields.io/badge/Coverage-83%25-brightgreen.svg)](file:///c:/Users/banks/ADHIKAAR_AI/docs/coverage_report.md)
[![Security Audit](https://img.shields.io/badge/Security_Audit-0_Vulnerabilities-success.svg)](file:///c:/Users/banks/ADHIKAAR_AI/docs/security_audit.md)

[![Kaggle Catalog](https://img.shields.io/badge/Scheme_Catalog-8%2C210+_Schemes-blue.svg)](file:///c:/Users/banks/ADHIKAAR_AI/data/raw/)
[![Fine-Tuned Model](https://img.shields.io/badge/Fact_Extractor-Llama_3.1_8B-purple.svg)](file:///c:/Users/banks/ADHIKAAR_AI/llama_3_8b_instruct_finetune_d13_FASTv3.ipynb)
[![Orchestrator](https://img.shields.io/badge/Orchestrator-LangGraph_20--Node-orange.svg)](file:///c:/Users/banks/ADHIKAAR_AI/backend/app/agents/graph.py)
[![Privacy](https://img.shields.io/badge/Privacy-DPDP_Act_2023-teal.svg)](file:///c:/Users/banks/ADHIKAAR_AI/output-ensurement.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](file:///c:/Users/banks/ADHIKAAR_AI/LICENSE)

<p align="center">
  <b>Closing India's ₹1.5+ Lakh Crore welfare exclusion gap with voice, vision, and deterministic rules.</b>
</p>

[See It In Action](#-see-it-in-action) • [System Architecture](#-system-architecture) • [How It Works](#-how-it-works-in-4-steps) • [Key Highlights](#-key-engineering-highlights) • [10 Output Invariants](#-machine-checked-output-invariants) • [How to Launch](#-how-to-launch-the-application-quickstart) • [Docs](#-documentation--judging-assets)

---

</div>

> **The Architectural Rule:**  
> *The LLM extracts and explains · The deterministic rules engine decides · A human caseworker handles doubt · The citizen is never met with silence.*

---

## 📌 The Problem & The Missing Action Layer

India spends over ₹4 lakh crore annually on direct citizen welfare, yet **more than ₹1.5 lakh crore in entitlements remains dropped or unclaimed every year** (*CAG Report No. 12 of 2022 on Public Welfare Transfers*). Over 40% of eligible rural applicants abandon applications before submission due to administrative friction, procedural confusion, and lost daily wages from making 3 to 4 trips to block revenue offices (*NITI Aayog, DBT Evaluation Report, 2021*).

Existing platforms like `myScheme.gov.in` and `india.gov.in` are passive discovery directories: **they inform, but they cannot act**. They cannot listen to vernacular voice notes, cannot inspect camera photos of crumpled rural documents, cannot mathematically verify statutory rules, and cannot recover from portal errors.

**ADHIKAAR closes the entire loop.** A citizen simply sends a voice note in their native language and camera photos of their documents via Telegram (or an accessible web portal). ADHIKAAR transcribes speech, grades visual quality, extracts facts into validated schemas, matches eligibility against 8,200+ schemes using deterministic rules, auto-submits the application to the scheme portal, and sends back a verified reference number.

```
Citizen Voice & Photos ──► AI Perception & Grounding ──► Deterministic Rules ──► Direct Portal Submission
```

---

## ⚡ See It In Action

### 1. Telegram Citizen Journey (PM-KISAN in Tamil / Hindi)
A farmer speaks in Tamil and uploads smartphone camera photos of their documents:

> **👤 Citizen (Voice Note):** *"நான் 1.5 ஹெக்டேர் நிலம் வைத்துள்ள சிறு விவசாயி. எனக்கு பி.எம் கிசான் உதவித்தொகை வேண்டும்."*  
> *(English translation: "I am a small farmer with 1.5 hectares of land. I need PM-Kisan assistance.")*  
> 📷 *Sends 3 camera photos: Aadhaar Card, Bank Passbook, Land Patta (RoR)*  
>  
> **🤖 ADHIKAAR Bot:**  
> 🎙️ **Voice Recognized (Tamil ➔ English):** Farmer intent identified  
> 📄 **Documents Classified:** Aadhaar Card (Clear), Bank Passbook (Clear), Land Record (Clear)  
> 🔍 **Extracted Facts:** Land: `1.5 Hectares` · Bank: `State Bank of India` · Grounding Confidence: `94.2%`  
>  
> ❓ *Quick Question:* Do you or your family pay income tax?  
> `[ ❌ No, I don't pay tax ]` `[ Yes, I pay tax ]`  
> *(Citizen taps [No])*  
>  
> ⚖️ **Rules Evaluation (`pm_kisan.yaml`):** All 3 statutory criteria passed deterministically  
> 🚀 **Portal Submission:** Submitting to Government Portal with Idempotency Key `7f4a-91b...`  
>  
> ✅ **Application Submitted Successfully!**  
> **Reference Number:** `MOCK-PORTAL-001` (Demo Environment)  
> **Benefit:** ₹6,000 / year (3 installments of ₹2,000 directly via DBT)  
> **Next Steps:** Aadhaar-linked DBT account will receive first installment in 14 days.  

---

### 2. Autonomous 422 Error Recovery (Scenario D1)
When the government portal rejects an application due to a missing OCR field, ADHIKAAR recovers automatically:

```
[Portal API] ──► HTTP 422 Unprocessable Entity ("missing_field: bank_ifsc")
      │
      ▼
[ADHIKAAR Agent] ──► Autonomous Targeted Recovery Loop
      │           • Locates Bank Passbook image in private ephemeral storage
      │           • Triggers single-field re-extraction prompt for IFSC code
      │           • IFSC "SBIN0001234" extracted and grounded against raw OCR
      │
      ▼
[Re-Submission] ──► HTTP 200 OK (Application Accepted · Reference: MOCK-PORTAL-002)
```
*Zero manual intervention. The citizen receives their confirmation without ever seeing a technical error.*

---

### 3. Human-in-the-Loop Reviewer Queue (`/reviewer/[id]`)
When document quality is blurry or confidence drops below 0.85:

| System Event | What Happens Under the Hood | Reviewer UI Screen |
|---|---|---|
| **Low Confidence / Blurry** | Graph execution pauses safely via `interrupt()`; audit event logged. | Case enters the caseworker review queue with live Server-Sent Events (SSE). |
| **Evidence Inspection** | Original camera photo displayed side-by-side with OCR bounding boxes. | Caseworker reviews highlighted extracted fields and grounded badges. |
| **One-Click Approval** | Caseworker edits any ambiguous field and taps **Approve & Resume**. | Backend executes `Command(resume=...)` and seamlessly completes submission. |

---

## 🏛️ System Architecture

ADHIKAAR cleanly separates unstructured multi-modal perception from legal decision-making.

```mermaid
flowchart LR
    subgraph Step1["1. Citizen Edge"]
        A["📱 Telegram Bot<br/>(@Adhikaar013bot)"]
        B["💻 Web Portal<br/>(Next.js Fallback)"]
    end

    subgraph Step2["2. Agent Pipeline"]
        direction TB
        C["🎙️ Sarvam ASR & 📄 PaddleOCR<br/>(Tamil / Telugu / Hindi / English)"]
        D["🤖 Fine-Tuned Llama 3.1 8B<br/>(Structured Fact Extraction)"]
        E["⚖️ Deterministic Rules Engine<br/>(simpleeval · Zero Hallucinations)"]
        C --> D --> E
    end

    subgraph Step3["3. Action & Resolution"]
        F["🏛️ Scheme Portal<br/>(Automated Submission)"]
        G["🧑‍⚖️ Caseworker Review<br/>(/reviewer UI · Edge Cases)"]
        H["📬 Guaranteed Output<br/>(Status / Ref / Next Steps)"]
    end

    Step1 --> Step2
    E -- "Eligible" --> F --> H
    E -- "Blurry / Low Conf" --> G --> F
    E -- "Not Eligible" --> H
```

---

## ⚙️ How It Works (In 4 Steps)

### 1. Multi-Modal Vernacular Intake
- **Regional Speech ASR:** Citizen voice notes are normalized into 16 kHz mono WAV and transcribed across **Tamil, Telugu, Hindi, and English** via Sarvam AI.
- **Album Debouncing:** Multi-photo camera albums are debounced automatically within a 2-second quiet window instead of sending separate responses per photo.

### 2. Vision & Fact Extraction
- **Dual-Head ResNet-18:** Simultaneously classifies document type (Aadhaar, Land Record, Passbook, etc.) and visual image quality (`clear`, `blurry`, `dark`, `damaged`).
- **OCR & Algorithmic Grounding:** PaddleOCR extracts text lines. A custom **fine-tuned Llama 3.1 8B Instruct** model extracts structured facts into JSON. Every number is algorithmically checked against raw OCR substrings to eliminate hallucinations.

### 3. Pure Deterministic Rules (No AI Guesswork)
- **Zero Generative Discretion:** LLMs are prohibited from deciding eligibility.
- Rules are defined in versioned YAML specs (e.g. `land_owned_hectares > 0 and is_income_tax_payer == False`), evaluated via pure `simpleeval`.
- Generates a complete audit trace: reasons for passing or failing, facts used, and source documents.

### 4. Direct Action & Self-Healing
- **Automated Submission:** Eligible cases are submitted directly to the scheme portal with an idempotency key.
- **422 Auto-Recovery:** If a portal returns a missing-field error, the agent automatically re-scans the passbook for that specific field and retries submission without bothering the citizen.
- **Human-in-the-Loop:** If an image is blurry or confidence is low (< 0.85), execution pauses safely via `interrupt()` and routes to a caseworker dashboard at `/reviewer/[id]`.

---

## 🏆 Key Engineering Highlights

| Capability | What It Does | Why It Matters |
|---|---|---|
| **Zero-Hallucination Decisions** | Pure-function rules engine evaluates statutory criteria. | The AI extracts facts, but never decides who gets public money. |
| **Fine-Tuned Fact Extractor** | Llama 3.1 8B fine-tuned with synthetic OCR-noise data. | High extraction accuracy on crumpled, low-contrast rural documents. |
| **8,210+ Kaggle Schemes** | Local Kaggle catalog (`myscheme.gov` + `ind-gov-schemes`). | Provides offline matching and a tailored 5-point document gap analysis. |
| **DPDP Act 2023 Compliant** | Masked IDs (`XXXX-XXXX-1234`), 7-day retention, instant `/delete`. | Citizen data is never used for training and can be purged on demand. |
| **Human Reviewer UI** | Next.js review queue with live Server-Sent Events (SSE). | Caseworkers quickly inspect evidence, edit facts, and resume cases. |
| **Guaranteed Output** | Every single case ends in an explicit, delivered result. | No citizen is left in silence; 10/10 machine invariants checked. |

---

## 🛡️ Machine-Checked Output Invariants

Under [`output-ensurement.md`](file:///c:/Users/banks/ADHIKAAR_AI/output-ensurement.md), ADHIKAAR enforces 10 strict machine-checked invariants verified live via [`scripts/verify_outputs.py`](file:///c:/Users/banks/ADHIKAAR_AI/scripts/verify_outputs.py) (`make verify-outputs`):

```
==========================================================================================
 ADHIKAAR OUTPUT ENSUREMENT — MACHINE-CHECKABLE INVARIANTS (INV-01..INV-10)
==========================================================================================
ID       | Invariant Name                     | Status | Details
------------------------------------------------------------------------------------------
INV-01   | Single Final Result Delivery       | PASS   | 0 duplicate final messages across terminal cases
INV-02   | Portal Reference on Completion     | PASS   | Completed cases hold verified portal_ref
INV-03   | No Illegal Applications            | PASS   | 0 applications submitted for ineligible cases
INV-04   | Structured Escalation Records      | PASS   | All escalations log structured evidence & reasons
INV-05   | Audit Trail & PII Masking          | PASS   | 89 audit events checked; 0 unmasked 12-digit IDs
INV-06   | Citizen Message Sanitization       | PASS   | 0 PII leaks or false volunteer callback claims
INV-07   | Session Lifecycle TTL Integrity    | PASS   | Inactive cases expire cleanly after 30-min TTL
INV-08   | 422 Error Auto-Recovery Retry      | PASS   | Targeted field re-extraction auto-recovers IFSC
INV-09   | DPDP Data Purge Compliance         | PASS   | Ephemeral storage & instant /delete purge operational
INV-10   | Decision & Output Agreement        | PASS   | 100% agreement between rules and delivered status
==========================================================================================
 RESULT: ALL 10 INVARIANTS PASSED (Zero data leaks, zero duplicate outputs)
```

---

## 📊 Operational Scenarios Benchmark

Tested end-to-end with offline fixtures across standard edge cases:

| Scenario | Input & Edge Condition | Result | Latency | Pass? |
|---|---|---|:---:|:---:|
| **Scenario A** | Clean voice note + Aadhaar + Passbook + Land Record | `COMPLETED` (Auto-submitted) | 182 ms | ✅ PASS |
| **Scenario B** | Missing Land Record | `NEEDS_DOCUMENTS` $\rightarrow$ Resume $\rightarrow$ `COMPLETED` | 215 ms | ✅ PASS |
| **Scenario C** | Blurry camera photo (low confidence) | `NEEDS_REVIEW` $\rightarrow$ Caseworker approves | 240 ms | ✅ PASS |
| **Scenario D1** | Portal returns 422 (Missing Bank IFSC) | Auto-Recovery on passbook $\rightarrow$ `COMPLETED` | 198 ms | ✅ PASS |
| **Scenario D2** | Portal returns 409 (Duplicate Aadhaar) | `NEEDS_REVIEW` (Escalated to human) | 170 ms | ✅ PASS |
| **Scenario E** | Missing tax declaration | `NEEDS_INFO` (Inline buttons) $\rightarrow$ `COMPLETED` | 189 ms | ✅ PASS |
| **Ineligible** | Land size > 2.0 ha (exceeds PM-Kisan limit) | `NOT_ELIGIBLE` with rule explanation | 1.2 ms | ✅ PASS |

*Note: Latencies shown above use deterministic offline fixtures. Live end-to-end execution with local LM Studio LLM averages ~4.2 seconds.*

---

## 💰 Quantified Citizen Impact

Based on DBT evaluation studies by NITI Aayog and the World Bank:

- **Time Saved:** Application time drops from **15–21 days down to under 5 minutes**.
- **Visits Eliminated:** Physical visits to block/tehsil revenue offices drop from **3–4 visits down to 0**.
- **Cash Preserved:** **₹1,850 saved per citizen household** (eliminating travel costs, CSC photocopies, tout commissions, and 2 days of lost daily agricultural wages).
- **Entitlements Unlocked:** For 100,000 rural applicants, this preserves **₹18.5 Crore** in household wealth and unblocks **₹22.8 Crore** in unclaimed entitlements.

---

## 🚀 How to Launch the Application (Quickstart)

> 💡 **Zero-Cost Architecture (₹0 Infrastructure & API Bills):**  
> Even at the MVP stage, ADHIKAAR operates at **₹0 (Zero Rupees)** total operating cost:
> - **Local LLM Inference:** The fine-tuned Llama 3.1 8B model runs 100% locally via LM Studio (`http://127.0.0.1:1234/v1`) — zero OpenAI or cloud API token bills.
> - **Local Vision & OCR:** PaddleOCR and the Dual-Head ResNet-18 classifier execute locally on-device — zero cloud vision charges.
> - **Free Citizen Edge:** The Telegram Bot API provides free, unlimited citizen interaction without SMS or WhatsApp gateway fees.
> - **Local State & Storage:** SQLite append-only storage and private local document vaults eliminate expensive managed cloud database subscriptions.

---

### ⚡ The Fastest Method (1-Click Launch)

1. **Start the local LM Studio server & load your model:**
   ```powershell
   lms server start
   lms load adhikaar-llama3.1-8b-v3
   ```

2. **Launch all ADHIKAAR application services in 1 command:**
   ```powershell
   .\scripts\start_all.ps1
   ```
   *This automated script starts the Mock Government Portal (8100), Backend Engine (8000), and Telegram Bot (8200) in the background, verifies LM Studio connectivity, and confirms health checks.*

3. **Message [@Adhikaar013bot](https://t.me/Adhikaar013bot) on Telegram** with `/start`!

---

### 🧪 Run the Offline Test Suite & Invariants

All 167 automated tests and 10 machine invariants execute 100% offline with zero external network dependencies:

```bash
# 1. Run all 167 tests across backend, bot, and portal
make test

# 2. Verify all 10 machine output invariants (10/10 PASS)
make verify-outputs
```

---

### Alternative Launch Options

#### Option A: Standalone Terminals (For Watching Live Service Logs)
Open 3 separate terminals:
```bash
# Terminal 1: Mock Scheme Portal (Port 8100)
cd mock_portal && uv run uvicorn app.main:app --port 8100

# Terminal 2: Backend API Engine (Port 8000)
cd backend && uv run uvicorn app.main:app --port 8000

# Terminal 3: Telegram Bot Service (Port 8200)
cd telegram_bot && uv run uvicorn app.main:app --port 8200

# Terminal 4 (Optional): Next.js Web Caseworker Dashboard (Port 3000)
cd frontend && npm run dev
```

#### Option B: Docker Compose (All-in-One Container)
```bash
docker compose up --build
```

---

## 📁 Project Structure

```
ADHIKAAR_AI/
├── backend/                  # FastAPI backend & LangGraph state machine
│   ├── app/agents/           # 20-node LangGraph orchestration & recovery
│   ├── app/integrations/     # Sarvam ASR, PaddleOCR, Llama 3.1 8B, PortalClient
│   ├── app/rules/            # Deterministic simpleeval engine & YAML specs
│   └── tests/                # 92 passing backend tests
├── telegram_bot/             # Python-Telegram-Bot v21 async service
│   ├── app/bot.py            # Debouncing, dynamic menu, chat memory
│   ├── app/live_schemes.py   # 8,210+ Kaggle schemes & document gap analysis
│   └── tests/                # 68 passing bot tests
├── mock_portal/              # Scheme portal simulation & error injection
│   └── tests/                # 7 passing portal tests
├── frontend/                 # Next.js 15 App Router web interface
│   ├── app/page.tsx          # Accessible citizen intake fallback
│   └── app/reviewer/         # Caseworker Human-in-the-Loop review UI
├── data/
│   ├── raw/                  # Kaggle official scheme datasets (8,210+ schemes)
│   └── fixtures/             # Recorded zero-network test audio, OCR, and facts
├── docs/                     # Pitch proposal, demo script, impact model, eval reports
├── scripts/                  # verify_outputs.py, run_eval.py, run_demo.py
└── output-ensurement.md      # Authoritative output delivery contract
```

---

## 📚 Documentation & Judging Assets

- 📄 **[One-Page Proposal](file:///c:/Users/banks/ADHIKAAR_AI/docs/proposal.md)** — Core problem, solution, and hackathon evaluation alignment.
- ⏱️ **[5-Minute Demo Script](file:///c:/Users/banks/ADHIKAAR_AI/docs/demo_script.md)** — Step-by-step walkthrough covering all presentation scenarios.
- 📊 **[Agent Evaluation Report](file:///c:/Users/banks/ADHIKAAR_AI/docs/eval_report.md)** — Empirical 25-case evaluation matrix (100% agreement).
- 🛡️ **[Output Assurance Report](file:///c:/Users/banks/ADHIKAAR_AI/docs/output_assurance_report.md)** — Certified invariant verification audit (10/10 PASS).
- 💰 **[Economic Impact Model](file:///c:/Users/banks/ADHIKAAR_AI/docs/impact.md)** — Sourced value model and citizen ROI calculations.
- 📋 **[Audit Checklist](file:///c:/Users/banks/ADHIKAAR_AI/checklist.md)** — Complete item-by-item implementation checklist.

---

<div align="center">

ADHIKAAR is open-source software licensed under the **[MIT License](file:///c:/Users/banks/ADHIKAAR_AI/LICENSE)**.

</div>
