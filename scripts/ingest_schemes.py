"""Ingest and standardize scheme rulebooks and YAML schemas (DS-01, DS-02, DS-05).

Ensures all scheme definitions and rulebooks carry strict provenance frontmatter:
source_urls, retrieved_at, version, verified_by, and MOCK labels.
Runs offline and deterministically.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RULEBOOKS_DIR = REPO_ROOT / "data" / "rulebooks"
SCHEMES_DIR = REPO_ROOT / "backend" / "app" / "rules" / "schemes"

SCHEME_REGISTRY: dict[str, dict[str, Any]] = {
    "pm_kisan_mock": {
        "scheme_id": "pm_kisan_mock",
        "name": "PM-Kisan (MOCK, simplified)",
        "version": 1,
        "benefit": "INR 6,000 per year (MOCK benefit)",
        "provenance": {
            "source_urls": [
                "https://pmkisan.gov.in/",
                "https://www.myscheme.gov.in/schemes/pm-kisan",
                "https://www.india.gov.in/my-government/schemes",
            ],
            "retrieved_at": "2026-10-23T00:00:00Z",
            "version": "1.0.0",
            "verified_by": "ADHIKAAR Knowledge Team",
            "source_priority": "official_guideline > myscheme.gov.in > india.gov.in",
            "compliance_label": "MOCK",
            "notes": "Simplified deterministic rules for hackathon demo; strictly labeled MOCK per DS-01.",
        },
        "required_documents": ["aadhaar", "land_record", "bank_passbook"],
        "facts": [
            {"key": "land_owned_hectares", "type": "float", "source": "land_record"},
            {"key": "holder_type", "type": "str", "source": "land_record"},
            {
                "key": "is_income_tax_payer",
                "type": "bool",
                "source": "declaration",
                "question": "Does anyone in your family pay income tax?",
            },
        ],
        "payload_fields": [
            {"key": "applicant_name", "type": "str", "source": "aadhaar"},
            {"key": "aadhaar_last4", "type": "str", "source": "aadhaar"},
            {"key": "bank_account_number", "type": "str", "source": "bank_passbook"},
            {"key": "bank_ifsc", "type": "str", "source": "bank_passbook"},
        ],
        "rules": [
            {
                "id": "owns_land",
                "expr": "land_owned_hectares > 0",
                "fail_reason": "No cultivable land ownership found in the land record.",
            },
            {
                "id": "individual_holder",
                "expr": "holder_type == 'individual'",
                "fail_reason": "Land is held by an institution, which is excluded.",
            },
            {
                "id": "not_tax_payer",
                "expr": "is_income_tax_payer == False",
                "fail_reason": "Income tax payers are excluded.",
            },
        ],
        "rulebook_content": """# PM-Kisan (MOCK) rulebook

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
""",
    },
    "state_scholarship_mock": {
        "scheme_id": "state_scholarship_mock",
        "name": "State Pre-Matric Scholarship (MOCK, simplified)",
        "version": 1,
        "benefit": "INR 4,000 per academic year (MOCK benefit)",
        "provenance": {
            "source_urls": [
                "https://socialjustice.gov.in/",
                "https://www.myscheme.gov.in/schemes/pre-matric-scholarship",
                "https://scholarships.gov.in/",
            ],
            "retrieved_at": "2026-10-23T00:00:00Z",
            "version": "1.0.0",
            "verified_by": "ADHIKAAR Knowledge Team",
            "source_priority": "official_guideline > myscheme.gov.in > india.gov.in",
            "compliance_label": "MOCK",
            "notes": "Simplified deterministic rules for educational assistance; strictly labeled MOCK per DS-01.",
        },
        "required_documents": [
            "aadhaar",
            "income_certificate",
            "marksheet",
            "bonafide_certificate",
        ],
        "facts": [
            {"key": "family_income_annual", "type": "int", "source": "income_certificate"},
            {"key": "last_exam_percentage", "type": "float", "source": "marksheet"},
            {
                "key": "institution_recognized",
                "type": "bool",
                "source": "declaration",
                "question": "Is your educational institution recognized?",
            },
        ],
        "payload_fields": [
            {"key": "applicant_name", "type": "str", "source": "aadhaar"},
            {"key": "aadhaar_last4", "type": "str", "source": "aadhaar"},
            {"key": "bank_account_number", "type": "str", "source": "income_certificate"},
            {"key": "bank_ifsc", "type": "str", "source": "income_certificate"},
        ],
        "rules": [
            {
                "id": "income_ceiling",
                "expr": "family_income_annual <= 250000",
                "fail_reason": "Annual family income exceeds the ceiling of INR 2,50,000.",
            },
            {
                "id": "academic_merit",
                "expr": "last_exam_percentage >= 75.0",
                "fail_reason": "Marks percentage is below the minimum requirement of 75.0%.",
            },
            {
                "id": "recognized_school",
                "expr": "institution_recognized == True",
                "fail_reason": "Educational institution must be recognized by the state board.",
            },
        ],
        "rulebook_content": """# State Pre-Matric Scholarship (MOCK) rulebook

**MOCK guidance only — not an official government rulebook.** This document
contains synthetic demo text for ADHIKAAR retrieval and explanation citations.

## Provenance
- **Official Sources:** [National Scholarship Portal](https://scholarships.gov.in/), [Ministry of Social Justice](https://socialjustice.gov.in/)
- **Source Priority Policy:** Official Ministry Guidelines > myScheme.gov.in > scholarships.gov.in
- **Verified Date:** 2026-10-23
- **Verification Authority:** ADHIKAAR Domain Policy Auditor
- **Status:** Synthetic MOCK Rulebook (Zero fabricated real-world law)

## Who this MOCK scheme is for

This MOCK scheme supports eligible school and college students from economically weaker sections.
Students asking about studies, scholarships, fee assistance, or schooling should match this scheme.

## Required documents (MOCK)

Provide an Aadhaar document, an Income Certificate, an official Senior Secondary Marksheet,
and a Bonafide Student Certificate.

## Eligibility guidance (MOCK)

The simplified demo rules require:
1. Annual household income less than or equal to INR 2,50,000 (`family_income_annual <= 250000`).
2. Prior examination academic aggregate of at least 75.0% (`last_exam_percentage >= 75.0`).
3. An explicit declaration that the institution is recognized (`institution_recognized == True`).
""",
    },
}


def ingest_all(check_only: bool = False) -> bool:
    RULEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMES_DIR.mkdir(parents=True, exist_ok=True)

    success = True
    for scheme_id, data in SCHEME_REGISTRY.items():
        # 1. Check/Write YAML schema
        yaml_path = SCHEMES_DIR / f"{scheme_id}.yaml"
        yaml_content = {
            "scheme_id": data["scheme_id"],
            "name": data["name"],
            "version": data["version"],
            "benefit": data["benefit"],
            "provenance": data["provenance"],
            "required_documents": data["required_documents"],
            "facts": data["facts"],
            "payload_fields": data["payload_fields"],
            "rules": data["rules"],
        }
        yaml_str = yaml.dump(yaml_content, sort_keys=False, allow_unicode=True)

        # 2. Check/Write Markdown Rulebook with frontmatter
        md_path = RULEBOOKS_DIR / f"{scheme_id}.md"
        frontmatter = yaml.dump({"provenance": data["provenance"]}, sort_keys=False)
        full_md = f"---\n{frontmatter}---\n\n{data['rulebook_content'].strip()}\n"

        if check_only:
            if not yaml_path.exists() or not md_path.exists():
                print(f"[FAIL] Missing files for {scheme_id}")
                success = False
            else:
                print(f"[OK] {scheme_id} schema and rulebook present")
        else:
            yaml_path.write_text(yaml_str, encoding="utf-8")
            md_path.write_text(full_md, encoding="utf-8")
            print(f"[INGESTED] {scheme_id} -> {yaml_path.name} & {md_path.name}")

    return success


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify rulebooks without overwriting")
    args = parser.parse_args()

    ok = ingest_all(check_only=args.check)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
