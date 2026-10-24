"""Live government welfare schemes extractor with fallback to Kaggle CSV catalog.

Uses:
1. Primary dataset: data/raw/myscheme.gov/schemes.csv (4,670 official schemes).
2. Enrichment: data/raw/ind-gov-schemes/structured_govt_schemes_converted.csv (3,534 schemes).
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

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
        "required_documents": ["Aadhaar Card", "Savings Bank Account", "Mobile Number"],
        "official_url": "https://www.npscra.nsdl.co.in/",
        "ministry": "Ministry of Finance / PFRDA",
        "categories": "Social Security, Pension",
        "target_beneficiaries": "Unorganized Sector Workers aged 18-40",
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
    indgov_path = (
        root / "data" / "raw" / "ind-gov-schemes" / "structured_govt_schemes_converted.csv"
    )

    catalog: dict[str, dict[str, Any]] = {}

    # Seed with verified core flagship schemes first to ensure highest quality
    for scheme in LIVE_GOVT_SCHEMES:
        catalog[scheme["scheme_id"]] = dict(scheme)

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

                    catalog[scheme_key] = {
                        "scheme_id": scheme_key,
                        "name": name,
                        "short_title": (row.get("short_title") or "").strip(),
                        "benefit": _clean_text(raw_benefit, max_len=260),
                        "eligibility": _clean_text(row.get("eligibility"), max_len=200),
                        "required_documents": docs,
                        "official_url": (row.get("source_url") or "https://www.myscheme.gov.in").strip(),
                        "ministry": (
                            row.get("ministry")
                            or row.get("department")
                            or "Government of India"
                        ).strip(),
                        "categories": (row.get("categories") or "").strip(),
                        "target_beneficiaries": (row.get("target_beneficiaries") or "").strip(),
                        "tags": (row.get("tags") or "").strip(),
                        "state": (row.get("state") or "").strip(),
                        "level": (row.get("level") or "Central").strip(),
                    }
        except Exception as exc:
            logger.warning("Error reading primary myscheme.gov dataset: %s", exc)

    # 2. Enrichment & Backup Dataset: ind-gov-schemes
    if indgov_path.is_file():
        try:
            with open(indgov_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    slug = (row.get("slug") or row.get("scheme_id") or "").strip()
                    name = (row.get("scheme_name") or "").strip()
                    if not name:
                        continue
                    scheme_key = slug or re.sub(r"[^a-zA-Z0-9_]", "_", name.lower()[:40])

                    if scheme_key in catalog:
                        # Enrichment path: supplement missing fields in primary
                        entry = catalog[scheme_key]
                        if not entry.get("required_documents") and row.get("documents"):
                            entry["required_documents"] = _parse_docs(row.get("documents"))
                        if len(entry.get("benefit", "")) < 30 and row.get("benefits"):
                            entry["benefit"] = _clean_text(row.get("benefits"), max_len=260)
                        if not entry.get("categories") and row.get("categories"):
                            entry["categories"] = (row.get("categories") or "").strip()
                    else:
                        # Backup path: add scheme from backup dataset
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
                            "official_url": (row.get("source_url") or "https://www.india.gov.in").strip(),
                            "ministry": (row.get("department") or "Government of India").strip(),
                            "categories": (row.get("categories") or "").strip(),
                            "target_beneficiaries": (row.get("target_beneficiaries") or "").strip(),
                            "tags": (row.get("tags") or "").strip(),
                            "state": (row.get("state") or "").strip(),
                            "level": (row.get("level") or "Central").strip(),
                        }
        except Exception as exc:
            logger.warning("Error reading backup ind-gov-schemes dataset: %s", exc)

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
        # Default flagship overview
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

    # Score schemes by keyword relevance
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


async def fetch_live_government_schemes(
    timeout: float = 2.0,
) -> tuple[list[dict[str, Any]], str | None]:
    """Attempt live extraction from government websites.

    Tries fetching from myscheme.gov.in and india.gov.in/my-government/schemes.
    If extraction fails (client-side JS rendering, HTTP 403, network timeout),
    returns verified real-world welfare schemes from the Kaggle dataset catalog
    along with the explicit notification:
    "Oh we can't able extract the data from the websites".
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    extracted_schemes: list[dict[str, Any]] = []
    extraction_failed = False

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            # 1. Attempt myScheme.gov.in
            try:
                resp1 = await client.get("https://www.myscheme.gov.in/", headers=headers)
                if resp1.status_code == 200:
                    raw_text = resp1.text
                    matches = re.findall(
                        r'<a[^>]+href="(/schemes/[^"]+)"[^>]*>([^<]+)</a>', raw_text
                    )
                    for url, title in matches:
                        title_clean = title.strip()
                        if title_clean and len(title_clean) > 5:
                            extracted_schemes.append({
                                "scheme_id": url.split("/")[-1],
                                "name": title_clean,
                                "benefit": "Government welfare benefit (via myScheme)",
                                "required_documents": ["Aadhaar Card", "Bank Account Details"],
                                "official_url": f"https://www.myscheme.gov.in{url}",
                                "ministry": "Government of India",
                            })
            except Exception as e:
                logger.info("myScheme live fetch failed: %s", e)
                extraction_failed = True

            # 2. Attempt india.gov.in
            try:
                url2 = "https://www.india.gov.in/my-government/schemes"
                resp2 = await client.get(url2, headers=headers)
                if resp2.status_code == 200:
                    raw_text = resp2.text
                    matches = re.findall(
                        r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', raw_text
                    )
                    keywords = [
                        "scheme", "yojana", "kisan", "bima",
                        "pension", "awas", "swachh",
                    ]
                    for url, title in matches:
                        title_clean = " ".join(title.split())
                        if (
                            len(title_clean) > 12
                            and any(k in title_clean.lower() for k in keywords)
                        ):
                            full_url = (
                                url if url.startswith("http")
                                else f"https://www.india.gov.in{url}"
                            )
                            extracted_schemes.append({
                                "scheme_id": re.sub(
                                    r"[^a-zA-Z0-9_]", "_", title_clean.lower()[:30]
                                ),
                                "name": title_clean,
                                "benefit": "National welfare scheme (via india.gov.in)",
                                "required_documents": ["Aadhaar Card", "Supporting Documents"],
                                "official_url": full_url,
                                "ministry": "Government of India",
                            })
            except Exception as e:
                logger.info("india.gov.in live fetch failed: %s", e)
                extraction_failed = True
    except Exception as e:
        logger.info("Live scheme extraction client error: %s", e)
        extraction_failed = True

    # If static HTML parsing did not extract full scheme cards (modern portals use dynamic
    # client rendering or protected backend APIs), return verified Kaggle catalog
    if len(extracted_schemes) < 3 or extraction_failed:
        # Load verified Kaggle dataset schemes
        kaggle_schemes = search_kaggle_schemes(limit=6)
        return kaggle_schemes, LIVE_EXTRACTION_FAILURE_MSG

    return extracted_schemes, None
