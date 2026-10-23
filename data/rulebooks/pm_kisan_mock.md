---
provenance:
  source_urls:
  - https://pmkisan.gov.in/
  - https://www.myscheme.gov.in/schemes/pm-kisan
  - https://www.india.gov.in/my-government/schemes
  retrieved_at: '2026-10-23T00:00:00Z'
  version: 1.0.0
  verified_by: ADHIKAAR Knowledge Team
  source_priority: official_guideline > myscheme.gov.in > india.gov.in
  compliance_label: MOCK
  notes: Simplified deterministic rules for hackathon demo; strictly labeled MOCK
    per DS-01.
---

# PM-Kisan (MOCK) rulebook

**MOCK guidance only — not an official government rulebook.** This document
contains synthetic demo text for ADHIKAAR retrieval and explanation citations.

## Provenance
- **Official Sources:** [PM-KISAN Portal](https://pmkisan.gov.in/), [myScheme](https://www.myscheme.gov.in/schemes/pm-kisan)
- **Source Priority Policy:** Official Ministry Guidelines > myScheme.gov.in > india.gov.in
- **Verified Date:** 2026-10-23
- **Verification Authority:** ADHIKAAR Domain Policy Auditor
- **Status:** Synthetic MOCK Rulebook (Zero fabricated real-world law)

## Who this MOCK scheme is for

This MOCK scheme is for small and marginal farmers seeking income support for individually held
cultivable agricultural land. A farmer asking about farming, land ownership,
crop support, or PM-Kisan should be matched to this scheme.

## Required documents (MOCK)

Provide an Aadhaar document, a land record (RoR / Patta), and a bank passbook. A clear photo
of each document is needed for this demo. The deterministic rules engine, rather than an LLM,
checks whether the documents and extracted facts satisfy the scheme.

## Eligibility guidance (MOCK)

The simplified demo rules require:
1. Land ownership greater than zero hectares (`land_owned_hectares > 0`).
2. An individual (not institutional) land holder category (`holder_type == 'individual'`).
3. An explicit declaration that nobody in the family pays income tax (`is_income_tax_payer == False`).

The benefit shown by this demo is INR 6,000 per year paid in three installments of INR 2,000.

## Frequently asked questions (MOCK)

- **Q: Can institutions apply?** No, institutional landholders are excluded.
- **Q: What if the land record is blurry?** The case is escalated to a human reviewer for verification.
- **Q: Can the LLM approve an exception?** Never. All eligibility decisions are 100% computed by the deterministic rules engine.
