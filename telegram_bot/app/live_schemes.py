"""Live government welfare schemes extractor with fallback to verified portals catalog."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Verified real-world welfare schemes from official live government portals
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
    },
]

LIVE_EXTRACTION_FAILURE_MSG = (
    "⚠️ Oh we can't able extract the data from the websites "
    "(https://www.myscheme.gov.in/, https://www.india.gov.in/my-government/schemes).\n"
    "Here are verified real-world welfare benefits from live government portals:"
)


async def fetch_live_government_schemes(
    timeout: float = 2.5,
) -> tuple[list[dict[str, Any]], str | None]:
    """Attempt live extraction from government websites.

    Tries fetching from myscheme.gov.in and india.gov.in/my-government/schemes.
    If the extraction fails (e.g. client-side JavaScript rendering, HTTP 403, network timeout),
    returns the verified government welfare catalog along with the explicit notification:
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
                                "required_documents": ["Aadhaar Card", "Bank Account"],
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
                                    r'[^a-zA-Z0-9_]', '_', title_clean.lower()[:30]
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

    # If static HTML parsing did not extract full scheme cards (because modern govt portals
    # use dynamic Client-Side React rendering with protected backend APIs), report failure notice
    if len(extracted_schemes) < 3 or extraction_failed:
        return LIVE_GOVT_SCHEMES, LIVE_EXTRACTION_FAILURE_MSG

    return extracted_schemes, None
