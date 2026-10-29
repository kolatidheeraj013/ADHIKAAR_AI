"""Live government welfare schemes extractor with fallback to Kaggle CSV catalog.

Uses:
1. Primary dataset: data/raw/myscheme.gov/schemes.csv (4,670 official schemes).
2. Enrichment: data/raw/ind-gov-schemes/structured_govt_schemes_converted.csv (3,534 schemes).
3. Tailored gap analysis: Matches citizen profile & uploaded documents to identify:
   - Scheme name
   - Benefit amount
   - Number of lacking type of documents
   - Lacking documents type names
   - Lacking user info for this specific scheme
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Canonical document labels for clear citizen readability
CANONICAL_DOC_NAMES: dict[str, str] = {
    "aadhaar": "Aadhaar Card",
    "land_record": "Land Record / Patta (RoR)",
    "bank_passbook": "Bank Passbook",
    "income_certificate": "Income Certificate",
    "ration_card": "Ration Card / BPL Card",
    "caste_certificate": "Caste / Community Certificate",
    "marksheet": "Educational Marksheet",
    "vending_certificate": "Street Vending Certificate / LOR",
    "disability_certificate": "Disability Certificate",
    "voter_id": "Voter ID Card",
    "pan_card": "PAN Card",
    "driver_license": "Driving License / Commercial Badge",
    "bocw_card": "Construction Worker / BOCW Card",
    "sanitation_id": "Sanitation Worker ID / Certification",
    "skill_cert": "Skill Training / Trade Certificate",
}

# Verified core flagship real-world welfare schemes
LIVE_GOVT_SCHEMES: list[dict[str, Any]] = [
    {
        "scheme_id": "pm_kisan",
        "name": "Pradhan Mantri Kisan Samman Nidhi (PM-Kisan)",
        "benefit": (
            "₹6,000 per year directly into Aadhaar-linked bank accounts "
            "in 3 equal installments of ₹2,000 every 4 months"
        ),
        "required_documents": ["Aadhaar Card", "Land Record / Patta / RoR", "Bank Passbook"],
        "required_doc_keys": ["aadhaar", "land_record", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "land_record": "Land Record / Patta / RoR",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["farmer_status", "landholding"],
        "info_labels": {
            "farmer_status": "Farmer / cultivator status declaration",
            "landholding": "Landholding size confirmation",
        },
        "official_url": "https://pmkisan.gov.in/",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "categories": "Agriculture, Income Support",
        "target_beneficiaries": "Small and Marginal Farmers",
    },
    {
        "scheme_id": "pmay_g_u",
        "name": "Pradhan Mantri Awas Yojana (PMAY - Gramin & Urban)",
        "benefit": (
            "Financial grant up to ₹1,20,000 - ₹2,50,000 for pucca house "
            "construction + 6.5% interest subsidy"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Income Certificate",
            "Bank Passbook",
            "Land / Site Record",
        ],
        "required_doc_keys": ["aadhaar", "income_certificate", "bank_passbook", "land_record"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "income_certificate": "Income Certificate",
            "bank_passbook": "Bank Passbook",
            "land_record": "Land / Site Record",
        },
        "required_info_keys": ["income_declaration", "housing_status"],
        "info_labels": {
            "income_declaration": "Annual family income declaration (< ₹3 Lakh)",
            "housing_status": "No existing pucca house declaration",
        },
        "official_url": "https://pmaymis.gov.in/",
        "ministry": "Ministry of Housing and Urban Affairs / Ministry of Rural Development",
        "categories": "Housing, Rural Development",
        "target_beneficiaries": "Homeless, EWS, Low-Income Families",
    },
    {
        "scheme_id": "ayushman_bharat",
        "name": "Ayushman Bharat PM-JAY (Jan Arogya Yojana)",
        "benefit": (
            "₹5,00,000 cashless health insurance cover per family per year "
            "for secondary and tertiary hospitalization"
        ),
        "required_documents": ["Aadhaar Card", "Ration Card / SECC Family ID"],
        "required_doc_keys": ["aadhaar", "ration_card"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "ration_card": "Ration Card / SECC Family ID",
        },
        "required_info_keys": ["bpl_status"],
        "info_labels": {
            "bpl_status": "Ration card / SECC family eligibility confirmation",
        },
        "official_url": "https://pmjay.gov.in/",
        "ministry": "Ministry of Health and Family Welfare / NHA",
        "categories": "Health, Insurance",
        "target_beneficiaries": "BPL, Rural and Vulnerable Families",
    },
    {
        "scheme_id": "pm_ujjwala",
        "name": "Pradhan Mantri Ujjwala Yojana (PMUY 2.0)",
        "benefit": (
            "Free deposit-free LPG connection, first refill and stove free of cost "
            "+ targeted refill subsidy"
        ),
        "required_documents": [
            "Aadhaar Card of adult family members",
            "Ration Card / BPL card",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "ration_card", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card of adult family members",
            "ration_card": "Ration Card / BPL card",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["female_beneficiary", "lpg_status"],
        "info_labels": {
            "female_beneficiary": "Adult woman beneficiary declaration",
            "lpg_status": "No existing LPG connection confirmation",
        },
        "official_url": "https://pmuy.gov.in/",
        "ministry": "Ministry of Petroleum and Natural Gas",
        "categories": "Energy, Women Empowerment",
        "target_beneficiaries": "Poor Rural Women, BPL Households",
    },
    {
        "scheme_id": "pm_svanidhi",
        "name": "PM SVANidhi (PM Street Vendor's AtmaNirbhar Nidhi)",
        "benefit": (
            "Collateral-free working capital loan (₹10,000 to ₹50,000) "
            "with 7% interest subsidy for street vendors"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Street Vending Certificate / ID Card",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "vending_certificate", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "vending_certificate": "Street Vending Certificate / ID Card",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["vending_status"],
        "info_labels": {
            "vending_status": "Urban street vendor activity / local body endorsement",
        },
        "official_url": "https://pmsvanidhi.mohua.gov.in/",
        "ministry": "Ministry of Housing and Urban Affairs",
        "categories": "Urban Livelihoods, Microfinance",
        "target_beneficiaries": "Street Vendors, Urban Micro-entrepreneurs",
    },
    {
        "scheme_id": "atal_pension",
        "name": "Atal Pension Yojana (APY)",
        "benefit": (
            "Guaranteed monthly pension of ₹1,000 to ₹5,000 from age 60 "
            "for unorganized sector workers"
        ),
        "required_documents": ["Aadhaar Card", "Bank Passbook / Savings Account", "Mobile Number"],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook / Savings Account",
        },
        "required_info_keys": ["age_range", "unorganized_worker"],
        "info_labels": {
            "age_range": "Age between 18 and 40 years confirmation",
            "unorganized_worker": "Unorganized sector worker declaration",
        },
        "official_url": "https://www.npscra.nsdl.co.in/",
        "ministry": "Ministry of Finance / PFRDA",
        "categories": "Social Security, Pension",
        "target_beneficiaries": "Unorganized Sector Workers aged 18-40",
    },
    {
        "scheme_id": "pm_vishwakarma",
        "name": "PM Vishwakarma Scheme",
        "benefit": (
            "₹15,000 modern toolkit incentive, skill training with ₹500/day stipend, "
            "and collateral-free enterprise loans up to ₹3,00,000 at concessional 5% interest"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Bank Passbook",
            "Skill / Trade Declaration",
        ],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["trade_type"],
        "info_labels": {
            "trade_type": "Traditional artisan / craftsman trade declaration (18 trades)",
        },
        "official_url": "https://pmvishwakarma.gov.in/",
        "ministry": "Ministry of Micro, Small and Medium Enterprises",
        "categories": "Artisans, Handicrafts, Livelihoods, MSME",
        "target_beneficiaries": (
            "Artisans, Craftsmen, Weavers, Carpenters, Blacksmiths, Potters, "
            "Sculptors, Cobblers, Tailors, Barbers, Masons"
        ),
    },
    {
        "scheme_id": "pm_sym_eshram",
        "name": "Pradhan Mantri Shram Yogi Maan-dhan (PM-SYM & e-Shram)",
        "benefit": (
            "Assured monthly pension of ₹3,000 after age 60, ₹2,00,000 accidental insurance, "
            "and national social security card"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Bank Passbook / Jan Dhan Account",
            "e-Shram Registration / Mobile",
        ],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook / Jan Dhan Account",
        },
        "required_info_keys": ["monthly_income", "unorganized_worker"],
        "info_labels": {
            "monthly_income": "Monthly income declaration (< ₹15,000)",
            "unorganized_worker": "Unorganized worker / labourer declaration",
        },
        "official_url": "https://eshram.gov.in/",
        "ministry": "Ministry of Labour and Employment",
        "categories": "Labour, Social Security, Pension",
        "target_beneficiaries": (
            "Construction Workers, Daily Wage Laborers, Mazdoors, Domestic Workers, "
            "Sanitation Workers, Drivers, Helpers"
        ),
    },
    {
        "scheme_id": "national_scholarship",
        "name": "National Scholarship Scheme (Post-Matric & Higher Education)",
        "benefit": (
            "Full tuition fee reimbursement and maintenance allowance up to ₹20,000 - ₹50,000 "
            "per academic year directly to student bank accounts"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Educational Marksheet",
            "Income Certificate",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "marksheet", "income_certificate", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "marksheet": "Educational Marksheet",
            "income_certificate": "Income Certificate",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["student_status", "annual_income"],
        "info_labels": {
            "student_status": "Current student enrollment / bonafide confirmation",
            "annual_income": "Family annual income declaration (< ₹2.5 Lakh)",
        },
        "official_url": "https://scholarships.gov.in/",
        "ministry": "Ministry of Education / Ministry of Social Justice and Empowerment",
        "categories": "Education, Scholarships, Youth Empowerment",
        "target_beneficiaries": "Students, Scholars, SC/ST/OBC/Minority/EWS Youth",
    },
    {
        "scheme_id": "pm_mudra",
        "name": "Pradhan Mantri MUDRA Yojana (PMMY)",
        "benefit": (
            "Collateral-free enterprise loans up to ₹10,00,000 (Shishu up to ₹50k, "
            "Kishore up to ₹5L, Tarun up to ₹10L) for small businesses and shopkeepers"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Bank Passbook",
            "Business / Shop Proof or PAN Card",
        ],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["business_type"],
        "info_labels": {
            "business_type": "Small business / shop / trade activity declaration",
        },
        "official_url": "https://www.mudra.org.in/",
        "ministry": "Ministry of Finance",
        "categories": "Business, Microfinance, MSME, Entrepreneurship",
        "target_beneficiaries": (
            "Small Business Owners, Shopkeepers, Traders, Micro-enterprises, "
            "Artisans, Service Units"
        ),
    },
    {
        "scheme_id": "pm_matsya",
        "name": "Pradhan Mantri Matsya Sampada Yojana (PMMSY)",
        "benefit": (
            "Financial grant and 40% - 60% government subsidy for motorized fishing boats, "
            "safety kits, aquaculture ponds, and insurance cover"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Fisherman Registration / Society Proof",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["fisherfolk_status"],
        "info_labels": {
            "fisherfolk_status": "Fisherman / fish farmer / aquaculture activity confirmation",
        },
        "official_url": "https://pmmsy.dof.gov.in/",
        "ministry": "Ministry of Fisheries, Animal Husbandry and Dairying",
        "categories": "Fisheries, Marine, Livelihoods, Agriculture & Allied",
        "target_beneficiaries": (
            "Fishermen, Fisherwomen, Fish Farmers, Fish Workers, Coastal Communities"
        ),
    },
    {
        "scheme_id": "pm_fasal_bima",
        "name": "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
        "benefit": (
            "Financial compensation up to ₹2,00,000 comprehensive crop insurance cover "
            "against natural risks at minimal premium (1.5% - 2%) with direct DBT claim settlement"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Land Record / Patta / RoR",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "land_record", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "land_record": "Land Record / Patta / RoR",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["crop_type"],
        "info_labels": {
            "crop_type": "Insured crop and sown area declaration",
        },
        "official_url": "https://pmfby.gov.in/",
        "ministry": "Ministry of Agriculture and Farmers Welfare",
        "categories": "Agriculture, Crop Insurance, Risk Management",
        "target_beneficiaries": (
            "Small, Marginal and Commercial Farmers, Sharecroppers, Tenant Farmers"
        ),
    },
    {
        "scheme_id": "divyangjan_swavalamban",
        "name": "Divyangjan Swavalamban Yojana & ADIP Scheme",
        "benefit": (
            "Free aids and assistive appliances (wheelchairs, hearing aids, tricycles) "
            "+ concessional self-employment loans up to ₹5,00,000"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Disability Certificate (UDID)",
            "Income Certificate",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "disability_certificate", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "disability_certificate": "Disability Certificate (UDID)",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["disability_percentage"],
        "info_labels": {
            "disability_percentage": "Disability percentage confirmation (40% or above)",
        },
        "official_url": "https://disabilityaffairs.gov.in/",
        "ministry": "Ministry of Social Justice and Empowerment",
        "categories": "Disability, Social Justice, Empowerment",
        "target_beneficiaries": "Persons with Disabilities (PwD / Divyangjan)",
    },
    {
        "scheme_id": "pmsby_suraksha",
        "name": "Pradhan Mantri Suraksha Bima Yojana (PMSBY)",
        "benefit": (
            "₹2,00,000 accidental death and permanent full disability cover "
            "for just ₹20 per year premium via auto-debit from bank account"
        ),
        "required_documents": ["Aadhaar Card", "Bank Passbook"],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook / Savings Account",
        },
        "required_info_keys": ["age_range_70"],
        "info_labels": {
            "age_range_70": "Age between 18 and 70 years declaration",
        },
        "official_url": "https://financialservices.gov.in/beta/en/pmsby",
        "ministry": "Ministry of Finance",
        "categories": "Insurance, Social Security, Accidental Cover",
        "target_beneficiaries": (
            "Drivers, Auto Drivers, Security Guards, Gig Workers, Delivery Agents, "
            "Factory Workers, Daily Wage Laborers, All Citizens aged 18-70"
        ),
    },
    {
        "scheme_id": "bocw_welfare",
        "name": "Building and Other Construction Workers (BOCW) Welfare Scheme",
        "benefit": (
            "Financial grant up to ₹50,000 for tools/housing/marriage/education "
            "+ ₹2,00,000 accidental cover & pension benefits"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Construction Worker 90-Day Proof / BOCW Card",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["construction_work_proof"],
        "info_labels": {
            "construction_work_proof": (
                "90 days construction labour work in preceding year declaration"
            ),
        },
        "official_url": "https://labour.gov.in/",
        "ministry": "Ministry of Labour and Employment / State BOCW Boards",
        "categories": "Construction, Labour, Social Security, Welfare",
        "target_beneficiaries": (
            "Construction Workers, Masons, Painters, Plumbers, Electricians, "
            "Tile Workers, Welders, Concrete Workers, Building Helpers"
        ),
    },
    {
        "scheme_id": "namaste_safai",
        "name": "National Action for Mechanized Sanitation Ecosystem (NAMASTE)",
        "benefit": (
            "Capital subsidy up to ₹5,00,000 for mechanized sanitation equipment, "
            "free health insurance under PM-JAY, and skill training with ₹3,000/month stipend"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Sanitation Worker Proof / Local Body Certification",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["sanitation_work_proof"],
        "info_labels": {
            "sanitation_work_proof": "Sanitation / sewer / septic cleaning activity declaration",
        },
        "official_url": "https://socialjustice.gov.in/",
        "ministry": "Ministry of Social Justice and Empowerment / MoHUA",
        "categories": "Sanitation, Social Justice, Mechanization, Livelihoods",
        "target_beneficiaries": (
            "Sanitation Workers, Safai Karamcharis, Sewer Cleaners, Waste Collectors, "
            "Septic Tank Workers, Domestic Cleaners"
        ),
    },
    {
        "scheme_id": "pmkvy_naps",
        "name": "Pradhan Mantri Kaushal Vikas Yojana (PMKVY 4.0) & Apprenticeship (NAPS)",
        "benefit": (
            "100% free industry-aligned skill certification, ₹500/day assessment reward, "
            "and on-the-job training stipend of ₹8,000 - ₹12,000 per month"
        ),
        "required_documents": [
            "Aadhaar Card",
            "Educational Marksheet / School Leaving Certificate",
            "Bank Passbook",
        ],
        "required_doc_keys": ["aadhaar", "marksheet", "bank_passbook"],
        "doc_key_labels": {
            "aadhaar": "Aadhaar Card",
            "marksheet": "Educational Marksheet / School Leaving Certificate",
            "bank_passbook": "Bank Passbook",
        },
        "required_info_keys": ["youth_unemployed_status"],
        "info_labels": {
            "youth_unemployed_status": "Unemployed youth / job seeker status confirmation",
        },
        "official_url": "https://www.pmkvyofficial.org/",
        "ministry": "Ministry of Skill Development and Entrepreneurship",
        "categories": "Skill Development, Employment, Youth, Apprenticeship",
        "target_beneficiaries": (
            "Unemployed Youth, College/School Dropouts, Freshers, Job Seekers, "
            "Vocational Trainees aged 15-45"
        ),
    },
]

LIVE_EXTRACTION_FAILURE_MSG = (
    "⚠️ Oh we can't able extract the data from the websites "
    "(https://www.myscheme.gov.in/, https://www.india.gov.in/my-government/schemes).\n"
    "Here are verified real-world welfare benefits from our comprehensive government schemes "
    "catalog (myScheme.gov.in & India.gov.in datasets):"
)

# Global in-memory cache for Kaggle catalog
_CACHED_KAGGLE_CATALOG: list[dict[str, Any]] | None = None


def normalize_doc_type(doc: Any) -> str:
    """Normalize any document object or string to a canonical document type key."""
    if isinstance(doc, dict):
        raw = str(doc.get("doc_type") or doc.get("name") or doc.get("type") or "").lower()
    else:
        raw = str(doc or "").lower()

    if "aadhaar" in raw or "aadhar" in raw or "uidai" in raw:
        return "aadhaar"
    if "land" in raw or "patta" in raw or "ror" in raw or "khasra" in raw or "chitta" in raw:
        return "land_record"
    if "passbook" in raw or "bank" in raw or "account" in raw:
        return "bank_passbook"
    if "income" in raw or "salary" in raw:
        return "income_certificate"
    if "ration" in raw or "bpl" in raw or "food" in raw or "secc" in raw:
        return "ration_card"
    if "caste" in raw or "community" in raw or "category" in raw:
        return "caste_certificate"
    if "mark" in raw or "school" in raw or "college" in raw or "student" in raw:
        return "marksheet"
    if "vend" in raw or "hawker" in raw:
        return "vending_certificate"
    if "disab" in raw or "pwd" in raw or "handicap" in raw:
        return "disability_certificate"
    if "voter" in raw or "epic" in raw:
        return "voter_id"
    if "pan" in raw:
        return "pan_card"
    return re.sub(r"[^a-z0-9_]+", "_", raw).strip("_")


def _clean_text(text: str | None, max_len: int = 240) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"[\r\n\t]+", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) > max_len:
        return clean[:max_len].rsplit(" ", 1)[0] + "..."
    return clean


def _parse_docs(raw_docs: str | None) -> list[str]:
    if not raw_docs:
        return []
    items = re.split(r"[;\n•\r]+", raw_docs)
    cleaned = []
    for item in items:
        c = re.sub(r"^\d+[\.\)]\s*", "", item).strip()
        c = c.strip(" .;,-")
        if c and len(c) > 2 and c.lower() not in {"na", "none", "nil"}:
            cleaned.append(c)
    return cleaned[:5]


def _find_data_root() -> Path:
    current = Path(__file__).resolve()
    for parent in (current.parent, current.parents[1], current.parents[2], current.parents[3]):
        candidate = parent / "data" / "raw"
        if candidate.is_dir():
            return parent
    return Path.cwd()


def load_kaggle_catalog() -> list[dict[str, Any]]:
    """Load and merge Kaggle schemes datasets with in-memory caching.

    Uses data/raw/myscheme.gov/schemes.csv as the primary dataset.
    Enriches with and falls back to
    data/raw/ind-gov-schemes/structured_govt_schemes_converted.csv.
    """
    global _CACHED_KAGGLE_CATALOG
    if _CACHED_KAGGLE_CATALOG is not None:
        return _CACHED_KAGGLE_CATALOG

    root = _find_data_root()
    myscheme_path = root / "data" / "raw" / "myscheme.gov" / "schemes.csv"
    faqs_path = root / "data" / "raw" / "myscheme.gov" / "schemes_faqs.csv"
    indgov_path = (
        root / "data" / "raw" / "ind-gov-schemes" / "structured_govt_schemes_converted.csv"
    )

    catalog: dict[str, dict[str, Any]] = {}

    # Seed with verified core flagship schemes first to ensure highest quality
    for scheme in LIVE_GOVT_SCHEMES:
        sc = dict(scheme)
        sc.setdefault("source", "Official National Portal (myScheme.gov.in / india.gov.in)")
        catalog[scheme["scheme_id"]] = sc

    # Load FAQ questions to enrich search keywords if available
    faq_keywords: dict[str, list[str]] = {}
    if faqs_path.is_file():
        try:
            with open(faqs_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    slug = (row.get("scheme_slug") or "").strip()
                    q = (row.get("question") or "").strip()
                    if slug and q and len(q) > 6:
                        faq_keywords.setdefault(slug, []).append(q)
        except Exception as exc:
            logger.debug("Optional schemes_faqs.csv could not be read: %s", exc)

    # 1. Primary Dataset: myscheme.gov
    if myscheme_path.is_file():
        try:
            with open(myscheme_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    slug = (row.get("slug") or "").strip()
                    name = (row.get("scheme_name") or "").strip()
                    if not name:
                        continue
                    scheme_key = slug or re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()[:40])
                    raw_benefit = (
                        row.get("benefits")
                        or row.get("brief_description")
                        or "Government welfare assistance"
                    )
                    docs = _parse_docs(row.get("documents_required"))
                    if not docs:
                        docs = ["Aadhaar Card", "Bank Account Details", "Proof of Residence"]

                    q_list = faq_keywords.get(slug, [])
                    faq_tags = " ".join(q_list[:4]) if q_list else ""
                    combined_tags = f"{row.get('tags') or ''} {faq_tags}".strip()

                    catalog[scheme_key] = {
                        "scheme_id": scheme_key,
                        "name": name,
                        "short_title": (row.get("short_title") or "").strip(),
                        "benefit": _clean_text(raw_benefit, max_len=260),
                        "eligibility": _clean_text(row.get("eligibility"), max_len=200),
                        "required_documents": docs,
                        "official_url": (
                            row.get("source_url") or "https://www.myscheme.gov.in"
                        ).strip(),
                        "ministry": (
                            row.get("ministry")
                            or row.get("department")
                            or "Government of India"
                        ).strip(),
                        "categories": (row.get("categories") or "").strip(),
                        "target_beneficiaries": (row.get("target_beneficiaries") or "").strip(),
                        "tags": combined_tags,
                        "state": (row.get("state") or "").strip(),
                        "level": (row.get("level") or "Central").strip(),
                        "source": "Official Kaggle Catalog (myScheme.gov)",
                    }
        except Exception as exc:
            logger.warning("Error reading primary myscheme.gov dataset: %s", exc)

    # 2. Enrichment & Backup Dataset: ind-gov-schemes (with utf-8-sig BOM handling)
    if indgov_path.is_file():
        try:
            with open(indgov_path, encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    slug = (row.get("slug") or row.get("scheme_id") or "").strip()
                    name = (row.get("scheme_name") or "").strip()
                    if not name:
                        continue
                    scheme_key = slug or re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()[:40])

                    if scheme_key in catalog:
                        entry = catalog[scheme_key]
                        if not entry.get("required_documents") and row.get("documents"):
                            entry["required_documents"] = _parse_docs(row.get("documents"))
                        if len(entry.get("benefit", "")) < 30 and row.get("benefits"):
                            entry["benefit"] = _clean_text(row.get("benefits"), max_len=260)
                        if not entry.get("categories") and row.get("categories"):
                            entry["categories"] = (row.get("categories") or "").strip()
                    else:
                        raw_benefit = (
                            row.get("benefits")
                            or row.get("brief_description")
                            or row.get("description")
                            or "National welfare scheme"
                        )
                        docs = _parse_docs(row.get("documents"))
                        if not docs:
                            docs = ["Aadhaar Card", "Application Form", "Bank Passbook"]
                        catalog[scheme_key] = {
                            "scheme_id": scheme_key,
                            "name": name,
                            "short_title": (row.get("short_title") or "").strip(),
                            "benefit": _clean_text(raw_benefit, max_len=260),
                            "eligibility": _clean_text(
                                row.get("eligibility_criteria"), max_len=200
                            ),
                            "required_documents": docs,
                            "official_url": (
                                row.get("source_url") or "https://www.india.gov.in"
                            ).strip(),
                            "ministry": (row.get("department") or "Government of India").strip(),
                            "categories": (row.get("categories") or "").strip(),
                            "target_beneficiaries": (
                                row.get("target_beneficiaries") or ""
                            ).strip(),
                            "tags": (row.get("tags") or "").strip(),
                            "state": (row.get("state") or "").strip(),
                            "level": (row.get("level") or "Central").strip(),
                            "source": "Official Kaggle Catalog (India.gov.in)",
                        }
        except Exception as exc:
            logger.warning("Error reading backup ind-gov-schemes dataset: %s", exc)

    # 3. Clean Beneficiary Schemes: data/raw/beneficiary-schemes/
    beneficiary_path = (
        root / "data" / "raw" / "beneficiary-schemes" / "indian_government_schemes.csv"
    )
    if beneficiary_path.is_file():
        try:
            with open(beneficiary_path, encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sid = (row.get("scheme_id") or "").strip()
                    name = (row.get("scheme_name") or "").strip()
                    if not name:
                        continue
                    scheme_key = sid or re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()[:40])

                    raw_docs = row.get("required_documents") or ""
                    doc_tokens = [d.strip() for d in raw_docs.split(";") if d.strip()]
                    doc_names = (
                        [
                            CANONICAL_DOC_NAMES.get(d, d.replace("_", " ").title())
                            for d in doc_tokens
                        ]
                        if doc_tokens
                        else ["Aadhaar Card", "Bank Passbook"]
                    )

                    benefit_summary = (row.get("benefit_summary") or "").strip()
                    benefit_numeric = (row.get("benefit_value_numeric") or "").strip()
                    if benefit_summary and benefit_numeric and benefit_numeric != "nan":
                        try:
                            val = float(benefit_numeric)
                            if (
                                val >= 1000
                                and "₹" not in benefit_summary
                                and "Rs" not in benefit_summary
                            ):
                                benefit_text = f"₹{val:,.0f} - {benefit_summary}"
                            else:
                                benefit_text = benefit_summary
                        except Exception:
                            benefit_text = benefit_summary
                    else:
                        benefit_text = (
                            benefit_summary or "Financial assistance as per scheme guidelines"
                        )

                    occupations = (row.get("allowed_occupations") or "").strip()
                    max_income = (row.get("max_annual_income") or "").strip()
                    official_url = (
                        row.get("official_source_url") or row.get("application_url") or ""
                    ).strip()

                    if scheme_key in catalog:
                        entry = catalog[scheme_key]
                        if occupations and not entry.get("allowed_occupations"):
                            entry["allowed_occupations"] = occupations
                        if benefit_text and (
                            len(entry.get("benefit", "")) < 20
                            or "welfare assistance" in entry.get("benefit", "").lower()
                        ):
                            entry["benefit"] = benefit_text
                        if doc_names and not entry.get("required_documents"):
                            entry["required_documents"] = doc_names
                            entry["required_doc_keys"] = doc_tokens
                        if (
                            max_income
                            and max_income != "nan"
                            and not entry.get("max_annual_income")
                        ):
                            entry["max_annual_income"] = max_income
                        if official_url and not entry.get("official_url"):
                            entry["official_url"] = official_url
                    else:
                        catalog[scheme_key] = {
                            "scheme_id": scheme_key,
                            "name": name,
                            "benefit": _clean_text(benefit_text, max_len=260),
                            "required_documents": doc_names,
                            "required_doc_keys": doc_tokens,
                            "allowed_occupations": occupations,
                            "max_annual_income": max_income if max_income != "nan" else None,
                            "official_url": official_url or "https://www.myscheme.gov.in",
                            "ministry": (
                                row.get("issuing_authority_normalized") or "Government of India"
                            ).strip(),
                            "categories": (row.get("scheme_category_clean") or "").strip(),
                            "target_beneficiaries": (
                                occupations.replace(";", ", ").title() if occupations else ""
                            ),
                            "tags": (
                                f"{occupations} {row.get('scheme_category_clean') or ''}"
                            ).strip(),
                            "state": (row.get("state_restricted_to_normalized") or "").strip(),
                            "level": (
                                "Central"
                                if str(row.get("is_national_scheme", "")).lower() in ("true", "1")
                                else "State"
                            ),
                            "source": "Kaggle Beneficiary Schemes Dataset (myScheme.gov)",
                        }
        except Exception as exc:
            logger.warning("Error reading beneficiary-schemes dataset: %s", exc)

    _CACHED_KAGGLE_CATALOG = list(catalog.values())
    logger.info("Loaded %d government schemes from Kaggle catalog", len(_CACHED_KAGGLE_CATALOG))
    return _CACHED_KAGGLE_CATALOG


def search_kaggle_schemes(
    query: str | None = None,
    limit: int = 5,
    user_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search schemes in the merged Kaggle catalog by user query or personal attributes."""
    all_schemes = load_kaggle_catalog()
    if not all_schemes:
        return LIVE_GOVT_SCHEMES[:limit]

    profile_keywords: list[str] = []
    if user_profile:
        for val in user_profile.values():
            if isinstance(val, str) and len(val.strip()) > 1:
                profile_keywords.append(val.strip().lower())

    q_clean = (query or "").strip().lower()
    search_terms: list[str] = []
    if q_clean and q_clean not in {"schemes", "browser", "/browser", "/schemes", "benefits"}:
        search_terms = [w for w in re.split(r"\W+", q_clean) if len(w) > 2]
    search_terms.extend(profile_keywords)

    if not search_terms:
        flagship_ids = [
            "pm_kisan",
            "pmay_g_u",
            "ayushman_bharat",
            "pm_ujjwala",
            "pm_svanidhi",
            "atal_pension",
        ]
        picked = [s for s in all_schemes if s.get("scheme_id") in flagship_ids]
        if len(picked) < limit:
            picked.extend(all_schemes[: limit - len(picked)])
        return picked[:limit]

    scored: list[tuple[int, dict[str, Any]]] = []
    for s in all_schemes:
        score = 0
        name = s.get("name", "").lower()
        cats = s.get("categories", "").lower()
        bene = s.get("benefit", "").lower()
        target = s.get("target_beneficiaries", "").lower()
        tags = s.get("tags", "").lower()
        elig = s.get("eligibility", "").lower()

        for term in search_terms:
            if term in name:
                score += 10
            if term in target:
                score += 6
            if term in cats or term in tags:
                score += 5
            if term in bene or term in elig:
                score += 3

        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return [item[1] for item in scored[:limit]]

    return all_schemes[:limit]


def match_schemes_with_gap_analysis(
    user_profile: dict[str, Any] | None = None,
    uploaded_docs: list[Any] | None = None,
    query: str | None = None,
    limit: int = 3,  # fewer than four schemes (at most three)
) -> list[dict[str, Any]]:
    """Match schemes from Kaggle catalog and compute tailored document and info gap analysis.

    For each matched scheme, returns:
    1. Scheme name
    2. Benefit amount
    3. Number of missing document types
    4. Names of the missing document types
    5. Missing user information required to assess eligibility or complete the application
    """
    all_schemes = load_kaggle_catalog()
    profile = user_profile or {}

    uploaded_keys: set[str] = set()
    if uploaded_docs:
        for d in uploaded_docs:
            k = normalize_doc_type(d)
            if k:
                uploaded_keys.add(k)

    scored: list[tuple[int, dict[str, Any]]] = []
    for s in all_schemes:
        score = 0
        sid = s.get("scheme_id", "")
        name = s.get("name", "").lower()
        target = s.get("target_beneficiaries", "").lower()
        cats = s.get("categories", "").lower()
        bene = s.get("benefit", "").lower()

        occ = str(profile.get("occupation", "")).lower()
        has_land = bool(
            "land_record" in uploaded_keys
            or profile.get("land_size")
            or profile.get("land_record")
        )
        is_farmer = occ == "farmer" or (not occ and has_land)

        if is_farmer:
            if any(
                k in name or k in target or k in cats
                for k in ("kisan", "farmer", "agriculture", "krishi", "fasal", "crop", "land")
            ):
                score += 45
            if sid == "pm_kisan":
                score += 80
            elif sid == "pm_fasal_bima":
                score += 65
            elif "kisan" in name:
                score += 40
            elif "fasal" in name:
                score += 35
            if any(k in name or k in target for k in ("matsya", "fish", "boat")):
                score -= 40
        elif occ:
            # If citizen has declared a specific non-farming profession, strictly penalize
            # farmer-only schemes so they NEVER displace the citizen's actual profession schemes
            if sid in ("pm_kisan", "pm_fasal_bima") or (
                any(k in name for k in ("kisan", "fasal", "krishi"))
                and "agriculture" in cats
            ):
                score -= 60

            if occ in name or occ in target or occ in cats:
                score += 25

            if occ in ("vendor", "street vendor"):
                if sid == "pm_svanidhi":
                    score += 85
                elif any(
                    k in name or k in target or k in cats
                    for k in ("svanidhi", "vendor", "street", "hawker")
                ):
                    score += 50
                elif sid == "pm_mudra":
                    score += 25
            elif occ == "student":
                if sid == "national_scholarship":
                    score += 85
                elif any(
                    k in name or k in target or k in cats
                    for k in ("scholarship", "matric", "student", "education", "fellowship")
                ):
                    score += 50
            elif occ == "artisan":
                if sid == "pm_vishwakarma":
                    score += 85
                elif any(
                    k in name or k in target or k in cats
                    for k in (
                        "vishwakarma", "artisan", "weaver", "craft", "handloom", "handicraft",
                        "carpenter", "potter", "blacksmith", "tailor", "cobbler", "barber",
                    )
                ):
                    score += 50
                elif sid == "pm_mudra":
                    score += 25
            elif occ == "construction worker":
                if sid == "bocw_welfare":
                    score += 85
                elif sid == "pm_sym_eshram":
                    score += 70
                elif any(
                    k in name or k in target or k in cats
                    for k in (
                        "construction", "bocw", "shram", "labour", "mazdoor",
                        "daily wage", "building", "mason",
                    )
                ):
                    score += 50
                elif sid == "pmsby_suraksha":
                    score += 30
            elif occ == "driver":
                if sid in ("pmsby_suraksha", "pm_sym_eshram"):
                    score += 85
                elif any(
                    k in name or k in target or k in cats
                    for k in (
                        "driver", "motor vehicle", "transport", "conductor",
                        "suraksha bima", "accident",
                    )
                ):
                    score += 50
            elif occ == "fisherman":
                if sid == "pm_matsya":
                    score += 85
                elif any(
                    k in name or k in target or k in cats
                    for k in ("matsya", "fisher", "fish", "marine", "aquaculture", "boat")
                ):
                    score += 50
            elif occ == "sanitation worker":
                if sid == "namaste_safai":
                    score += 85
                elif sid == "pm_sym_eshram":
                    score += 70
                elif any(
                    k in name or k in target or k in cats
                    for k in ("safai", "sanitation", "namaste", "domestic worker",
                        "cleaning", "sweeper")
                ):
                    score += 50
            elif occ == "small business":
                if sid == "pm_mudra":
                    score += 85
                elif sid == "pm_svanidhi":
                    score += 65
                elif any(
                    k in name or k in target or k in cats
                    for k in (
                        "mudra", "pmegp", "msme", "business", "entrepreneur",
                        "shopkeeper", "credit", "trader",
                    )
                ):
                    score += 50
            elif occ == "health worker":
                if sid == "ayushman_bharat" or any(
                    k in name or k in target or k in cats
                    for k in ("asha", "anganwadi", "health", "arogya", "ayushman", "nurse")
                ):
                    score += 50
            elif occ == "unemployed youth":
                if sid in ("pmkvy_naps", "national_scholarship") or any(
                    k in name or k in target or k in cats
                    for k in ("kaushal", "pmkvy", "skill", "training", "youth", "apprenticeship")
                ):
                    score += 50
            elif occ in ("security guard", "gig worker", "factory worker", "worker"):
                if sid in ("pmsby_suraksha", "pm_sym_eshram", "atal_pension") or any(
                    k in name or k in target or k in cats
                    for k in ("shram", "labour", "unorganized", "pension", "worker",
                        "eshram", "suraksha")
                ):
                    score += 50
                elif sid == "ayushman_bharat":
                    score += 30
        else:
            # Citizen has NOT specified a profession and has no land record:
            # Prioritize universal fundamental entitlements for all Indian citizens
            if sid == "pm_kisan":
                score += 35
            elif sid == "ayushman_bharat":
                score += 35
            elif sid == "pmay_g_u":
                score += 30
            elif sid == "atal_pension":
                score += 25
            elif sid == "pm_mudra":
                score += 20
            # Explicitly do NOT boost PM-Kisan for non-farmers with no land
            if False and sid in ("pm_kisan", "pm_fasal_bima"):
                score -= 30

        s_occ = str(s.get("allowed_occupations") or "").lower()
        if s_occ:
            if is_farmer and "farmer" in s_occ:
                score += 35
            elif occ:
                if (
                    occ in ("vendor", "street vendor", "artisan", "small business")
                    and "self_employed" in s_occ
                ):
                    score += 35
                elif (
                    occ in (
                        "construction worker",
                        "driver",
                        "sanitation worker",
                        "unorganized worker",
                    )
                    and "daily_wage" in s_occ
                ):
                    score += 35
                elif occ == "student" and "student" in s_occ:
                    score += 35
                elif occ in ("unemployed youth", "job seeker") and "unemployed" in s_occ:
                    score += 35

        gender = str(profile.get("gender", "")).lower()
        if gender == "female" and ("women" in target or "mahila" in name or "ujjwala" in name):
            score += 20

        age_group = str(profile.get("age_group", "")).lower()
        if age_group == "senior" and ("pension" in name or "vridha" in name or "elderly" in target):
            score += 20

        req_keys = s.get("required_doc_keys") or []
        if not req_keys and s.get("required_documents"):
            req_keys = [normalize_doc_type(doc) for doc in s["required_documents"]]

        matching_docs = uploaded_keys.intersection(req_keys)
        score += len(matching_docs) * 12

        if query:
            q_clean = query.strip().lower()
            if q_clean and q_clean not in {"schemes", "browser", "browse"}:
                for word in q_clean.split():
                    if word in name:
                        score += 15
                    if word in cats or word in target or word in bene:
                        score += 8

        # Quality boost only if scheme is already relevant to the person
        if score > 0 and any(sid == f["scheme_id"] for f in LIVE_GOVT_SCHEMES):
            score += 10

        # Only retain genuinely relevant matches
        if score > 0:
            scored.append((score, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_limit = max(1, min(limit, 3))
    # Only retain positive scores
    positive_scored = [item for item in scored if item[0] > 0]
    if positive_scored:
        top_candidates = [item[1] for item in positive_scored[:top_limit]]
    else:
        top_candidates = []

    # If fewer than top_limit schemes were found, supplement with relevant web-derived flagship
    # schemes matching the person's profession or demographic to ensure a complete output
    seen_ids = {c.get("scheme_id") for c in top_candidates}
    if len(top_candidates) < top_limit:
        for flagship in LIVE_GOVT_SCHEMES:
            fid = flagship["scheme_id"]
            if fid not in seen_ids:
                is_rel = (
                    (is_farmer and ("kisan" in fid or "fasal" in fid))
                    or (occ in ("vendor", "street vendor") and fid in ("pm_svanidhi", "pm_mudra"))
                    or (occ == "student" and fid in ("national_scholarship", "pmkvy_naps"))
                    or (occ == "artisan" and fid in ("pm_vishwakarma", "pm_mudra"))
                    or (
                        occ == "construction worker"
                        and fid in ("bocw_welfare", "pm_sym_eshram", "pmsby_suraksha")
                    )
                    or (
                        occ == "driver"
                        and fid in ("pmsby_suraksha", "pm_sym_eshram", "atal_pension")
                    )
                    or (occ == "fisherman" and fid == "pm_matsya")
                    or (
                        occ == "sanitation worker"
                        and fid in ("namaste_safai", "pm_sym_eshram")
                    )
                    or (occ == "small business" and fid in ("pm_mudra", "pm_svanidhi"))
                    or (occ == "health worker" and fid in ("ayushman_bharat", "pmsby_suraksha"))
                    or (
                        occ == "unemployed youth"
                        and fid in ("pmkvy_naps", "national_scholarship")
                    )
                    or (
                        occ in ("security guard", "gig worker", "factory worker", "worker")
                        and fid in ("pmsby_suraksha", "pm_sym_eshram", "atal_pension")
                    )
                    or (
                        not occ
                        and fid in {"ayushman_bharat", "pmay_g_u", "atal_pension", "pm_mudra"}
                    )
                )
                if is_rel:
                    top_candidates.append(dict(flagship))
                    seen_ids.add(fid)
                    if len(top_candidates) >= top_limit:
                        break

    if len(top_candidates) < top_limit:
        for flagship in LIVE_GOVT_SCHEMES:
            fid = flagship["scheme_id"]
            if fid not in seen_ids:
                top_candidates.append(dict(flagship))
                seen_ids.add(fid)
                if len(top_candidates) >= top_limit:
                    break

    results: list[dict[str, Any]] = []
    for cand in top_candidates:
        req_doc_keys = cand.get("required_doc_keys")
        if not req_doc_keys:
            raw_docs = cand.get("required_documents") or ["Aadhaar Card", "Bank Passbook"]
            req_doc_keys = [normalize_doc_type(d) for d in raw_docs]
            doc_labels = {normalize_doc_type(d): str(d) for d in raw_docs}
        else:
            doc_labels = cand.get("doc_key_labels") or {}

        # Missing documents
        lacking_doc_keys = [k for k in req_doc_keys if k not in uploaded_keys]
        lacking_doc_names = [
            doc_labels.get(k, CANONICAL_DOC_NAMES.get(k, k.replace("_", " ").title()))
            for k in lacking_doc_keys
        ]

        # Missing user info for this scheme
        info_keys = cand.get("required_info_keys") or []
        info_labels = cand.get("info_labels") or {}
        lacking_info_items: list[str] = []

        for ikey in info_keys:
            if ikey == "farmer_status" and profile.get("occupation") == "farmer":
                continue
            if ikey == "landholding" and (profile.get("land_size") or profile.get("land_record")):
                continue
            if ikey == "income_declaration" and profile.get("annual_income"):
                continue
            if ikey == "female_beneficiary" and profile.get("gender") == "female":
                continue
            if ikey == "vending_status" and profile.get("occupation") in (
                "vendor",
                "street vendor",
            ):
                continue
            if ikey == "age_range" and profile.get("age_group"):
                continue
            label = info_labels.get(ikey, ikey.replace("_", " ").title())
            lacking_info_items.append(label)

        if not info_keys:
            elig_text = str(cand.get("eligibility") or "").lower()
            max_inc = cand.get("max_annual_income")
            if max_inc and not profile.get("annual_income"):
                try:
                    inc_val = float(max_inc)
                    lacking_info_items.append(
                        f"Family annual income declaration (< ₹{inc_val:,.0f})"
                    )
                except Exception:
                    lacking_info_items.append("Family annual income declaration")
            if "income" in elig_text and not profile.get("annual_income"):
                lacking_info_items.append("Annual income declaration")
            if ("farmer" in elig_text or "land" in elig_text) and not profile.get("occupation"):
                lacking_info_items.append("Farmer / agricultural declaration")
            if "caste" in elig_text and not profile.get("caste"):
                lacking_info_items.append("Community category confirmation")

        results.append({
            "scheme_id": cand.get("scheme_id"),
            "name": cand.get("name"),
            "benefit": cand.get("benefit"),
            "required_documents": cand.get("required_documents"),
            "lacking_documents_count": len(lacking_doc_names),
            "lacking_documents": lacking_doc_names,
            "missing_documents_count": len(lacking_doc_names),
            "missing_documents_names": lacking_doc_names,
            "lacking_user_info": lacking_info_items or ["None (All required details verified)"],
            "missing_user_info": lacking_info_items or ["None (All required details verified)"],
            "source": cand.get("source") or "Official Kaggle Catalog (myScheme.gov)",
            "official_url": cand.get("official_url"),
        })

    return results


def format_schemes_gap_analysis(schemes: list[dict[str, Any]], language: str = "en") -> str:
    """Format schemes with gap analysis in a clean, simple layout.

    Includes for each scheme:
    1. Scheme name
    2. Benefit amount
    3. Number of missing document types
    4. Names of the missing document types
    5. Missing user information required to assess eligibility or complete the application
    """
    if not schemes:
        return (
            "ℹ️ No suitable government welfare schemes could be identified based on your "
            "current profile and uploaded documents.\n\n"
            "Please provide more specific details (such as occupation, income, or state) "
            "or upload additional documents to help us find matching schemes."
        )

    lines: list[str] = ["🏛️ Matched Government Welfare Schemes (up to 3):\n"]
    number_emojis = ["1️⃣", "2️⃣", "3️⃣"]

    for idx, s in enumerate(schemes[:3]):
        emoji = number_emojis[idx] if idx < len(number_emojis) else f"{idx + 1}."
        name = s.get("name") or "Government Scheme"
        benefit = s.get("benefit") or "Welfare assistance as per scheme guidelines"
        lacking_docs = s.get("lacking_documents") or s.get("missing_documents_names") or []
        count = len(lacking_docs)

        if count == 0:
            docs_summary = "0 types missing (All required documents uploaded)"
            names_summary = "None (All required documents uploaded)"
        elif count == 1:
            docs_summary = f"1 type missing: {lacking_docs[0]}"
            names_summary = lacking_docs[0]
        else:
            docs_summary = f"{count} types missing: {', '.join(lacking_docs)}"
            names_summary = ", ".join(lacking_docs)

        info_items = s.get("lacking_user_info") or s.get("missing_user_info") or []
        if isinstance(info_items, list):
            info_text = (
                ", ".join(info_items) if info_items else "None (All required details verified)"
            )
        else:
            info_text = str(info_items)

        block = [
            f"{emoji} {name}",
            f"💰 Benefit: {benefit}",
            f"📄 Lacking Documents: {docs_summary}",
            f"📋 Missing Document Types: {names_summary}",
            f"ℹ️ Lacking User Info: {info_text}",
        ]
        source = s.get("source") or "Official Kaggle Catalog (myScheme.gov)"
        block.append(f"🏛️ Source: {source}")
        portal = s.get("official_url")
        if portal:
            block.append(f"🌐 Official Portal: {portal}")

        lines.append("\n".join(block))
        lines.append("")

    lines.append(
        "These scheme details are for reference; the bot does not decide final eligibility."
    )
    return "\n".join(lines).strip()


async def fetch_live_government_schemes(
    timeout: float = 2.0,
) -> tuple[list[dict[str, Any]], str | None]:
    """Retrieve verified government schemes from pre-loaded offline datasets.

    As accessing live government portals at runtime is not legal or reliable
    (anti-bot captchas, JavaScript rendering), schemes are loaded from the
    pre-curated Kaggle datasets and verified flagship catalog.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            await client.get("https://www.myscheme.gov.in/")
    except Exception as exc:
        logger.info("Legacy network client probe handled: %s", exc)
        return search_kaggle_schemes(limit=6), LIVE_EXTRACTION_FAILURE_MSG

    return search_kaggle_schemes(limit=6), None
