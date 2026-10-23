# ADHIKAAR — Demo Sample Pack

This directory contains pre-staged, synthetic mock documents and audio voice notes for running the live hackathon pitch and judge demos.

> **CRITICAL PRIVACY RULE:** Every file here is 100% synthetic. Every document image is visibly stamped with `SAMPLE — NOT A REAL DOCUMENT`. No real PII or government credentials exist.

## How Presenters Use These Samples

### For Telegram Bot Demo (@adhikaar013bot):
1. Send `/start` on Telegram and accept the consent disclaimer.
2. Send one audio voice note (e.g. `voice_sample_ta.wav` for Tamil, or `voice_sample_hi.wav` for Hindi).
3. Send the document photos (`aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png`).
4. Click **Done** on Telegram to trigger autonomous multi-agent analysis.

### For Next.js Web Form Demo:
1. Open the web interface (`http://localhost:3000`).
2. Accept the consent checkbox.
3. Upload voice note and document image files.
4. Watch the real-time SSE audit timeline render each stage (`INPUT → UNDERSTAND → PLAN → USE TOOLS → ACT → VERIFY`).

## Scenario File Mapping

| Scenario | Voice File | Document Files | Expected Stage |
|---|---|---|---|
| **Scenario A** (Auto-Submit) | `voice_sample_ta.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png` | Automatic submission with portal ref `PMK-TN-...` |
| **Scenario B** (Missing Doc) | `voice_sample_en.wav` | `aadhaar_sample.png`, `bank_passbook_sample.png` | Pauses with `NEEDS_DOCUMENTS`; asks for land record |
| **Scenario C** (Human Review) | `voice_sample_ta.wav` | `aadhaar_sample.png`, `land_record_blurry.png`, `bank_passbook_sample.png` | Escalates to Reviewer queue with confidence < 0.85 |
| **Scenario D1** (Auto-Recovery) | `voice_sample_hi.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `passbook_missing_ifsc.png` | Auto-recovers missing IFSC via secondary pass |
| **Scenario D2** (Portal Failure) | `voice_sample_te.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png` | Mock portal rejection → Escalated with failure trace |
| **Scenario E** (Clarification) | `voice_sample_ta.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png` | Inline question: "Does anyone pay income tax?" |
| **Scholarship** | `voice_scholarship_en.wav` | `aadhaar_sample.png`, `income_cert_sample.png`, `marksheet_sample.png` | Assesses student entitlement |
