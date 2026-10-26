"""Provider-agnostic LLM client for structured fact extraction and explanation."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.interfaces import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_EXTRACTION_PROMPT = (
    "You are ADHIKAAR's structured fact extraction engine for Indian welfare schemes. "
    "Extract ONLY explicitly stated facts from the text into the requested JSON schema. "
    "If a field is not mentioned or cannot be verified, set it to null. "
    "Do NOT guess or infer missing values. Never decide eligibility. "
    "Output strictly valid JSON with no markdown formatting."
)


def mask_identifiers(text: str) -> str:
    """Mask 12-digit Aadhaar or long account numbers to last 4 digits."""

    # Match 12-digit numbers with optional spaces/hyphens: 1234 5678 9012 or 123456789012
    def replace_12_digit(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) == 12:
            return f"XXXX-XXXX-{digits[-4:]}"
        return m.group(0)

    return re.sub(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b", replace_12_digit, text)


class LLMRateLimiter:
    """Thread-safe rate limiter and concurrency controller for LLM endpoints."""

    def __init__(
        self,
        max_concurrency: int = 1,
        rpm_limit: int = 20,
        min_interval_seconds: float = 1.0,
    ) -> None:
        self.max_concurrency = max(1, max_concurrency)
        self.rpm_limit = max(1, rpm_limit)
        self.min_interval = max(0.0, min_interval_seconds)
        self._semaphore = threading.BoundedSemaphore(self.max_concurrency)
        self._lock = threading.Lock()
        self._call_timestamps: list[float] = []

    def acquire(self, timeout: float = 45.0) -> bool:
        """Acquire both concurrency semaphore and rate limit window."""
        acquired = self._semaphore.acquire(timeout=timeout)
        if not acquired:
            return False

        with self._lock:
            now = time.monotonic()
            # Prune timestamps older than 60 seconds
            self._call_timestamps = [t for t in self._call_timestamps if now - t < 60.0]

            # Enforce RPM limit
            if len(self._call_timestamps) >= self.rpm_limit:
                sleep_needed = 60.0 - (now - self._call_timestamps[0]) + 0.1
                if sleep_needed > 0:
                    logger.info(
                        "LLM rate limit reached (%d RPM). Throttling for %.2fs",
                        self.rpm_limit,
                        sleep_needed,
                    )
                    time.sleep(sleep_needed)
                    now = time.monotonic()
                    self._call_timestamps = [t for t in self._call_timestamps if now - t < 60.0]

            # Enforce minimum cooldown between consecutive requests
            if self._call_timestamps and (now - self._call_timestamps[-1]) < self.min_interval:
                cooldown = self.min_interval - (now - self._call_timestamps[-1])
                time.sleep(cooldown)

            self._call_timestamps.append(time.monotonic())
        return True

    def release(self) -> None:
        """Release the concurrency semaphore."""
        try:
            self._semaphore.release()
        except ValueError:
            pass


_RATE_LIMITERS: dict[str, LLMRateLimiter] = {}
_LIMITER_LOCK = threading.Lock()


def get_rate_limiter(
    base_url: str,
    max_concurrency: int,
    rpm_limit: int,
    min_interval: float,
) -> LLMRateLimiter:
    with _LIMITER_LOCK:
        if base_url not in _RATE_LIMITERS:
            _RATE_LIMITERS[base_url] = LLMRateLimiter(
                max_concurrency=max_concurrency,
                rpm_limit=rpm_limit,
                min_interval_seconds=min_interval,
            )
        return _RATE_LIMITERS[base_url]


class ProviderLLMClient(LLMClient):
    """Production LLM client supporting OpenAI, Hugging Face, vLLM, and offline fixtures."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        demo_mode: str | None = None,
        fixtures_path: Path | None = None,
        max_concurrency: int | None = None,
        rpm_limit: int | None = None,
        min_interval_seconds: float | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.provider = provider or settings.llm_provider
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        configured_base_url = base_url if base_url is not None else settings.llm_base_url
        self._endpoint_configured = bool(configured_base_url)
        self.base_url = (configured_base_url or "https://api.openai.com/v1").rstrip("/")
        self.demo_mode = (demo_mode or settings.demo_mode).lower()
        self.fixtures_path = fixtures_path or Path("data/fixtures/llm_facts.json")
        self._fixtures: dict[str, dict[str, Any]] = {}
        self._load_fixtures()

        # Rate limiting and concurrency controls
        self.max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else getattr(settings, "llm_max_concurrency", 1)
        )
        self.rpm_limit = (
            rpm_limit if rpm_limit is not None else getattr(settings, "llm_rpm_limit", 20)
        )
        self.min_interval = (
            min_interval_seconds
            if min_interval_seconds is not None
            else getattr(settings, "llm_min_interval_seconds", 1.0)
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "llm_timeout_seconds", 90.0)
        )

    def _load_fixtures(self) -> None:
        if self.fixtures_path.exists():
            try:
                with open(self.fixtures_path, "r", encoding="utf-8") as f:
                    self._fixtures = json.load(f)
            except Exception as e:
                logger.warning("Failed to load LLM fixtures from %s: %s", self.fixtures_path, e)

    def _call_chat_completion(self, messages: list[dict[str, str]], json_mode: bool = True) -> str:
        """Call standard OpenAI-compatible /chat/completions endpoint with rate limiting."""
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }
        # Local endpoints like LM Studio enforce json format via prompt instruction
        if json_mode and self.provider.lower() not in ("lmstudio", "ollama", "local"):
            payload["response_format"] = {"type": "json_object"}

        limiter = get_rate_limiter(
            self.base_url,
            self.max_concurrency,
            self.rpm_limit,
            self.min_interval,
        )

        if not limiter.acquire(timeout=45.0):
            raise TimeoutError(
                f"LLM concurrency limit ({self.max_concurrency}) queue wait timed out after 45s."
            )

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                for retry in range(2):
                    try:
                        response = client.post(url, headers=headers, json=payload)
                        if response.status_code in (429, 503) and retry == 0:
                            logger.warning(
                                "LLM returned HTTP %d (%s). Throttling 2.0s before retry...",
                                response.status_code,
                                response.text[:100],
                            )
                            time.sleep(2.0)
                            continue
                        response.raise_for_status()
                        break
                    except httpx.HTTPStatusError as err:
                        if err.response.status_code == 400 and "response_format" in payload:
                            payload.pop("response_format", None)
                            response = client.post(url, headers=headers, json=payload)
                            response.raise_for_status()
                            break
                        raise
                data = response.json()
                return str(data["choices"][0]["message"]["content"]).strip()
        finally:
            limiter.release()

    def extract_facts(
        self, text: str, source_type: str, source_doc_id: str | None, target_keys: list[str]
    ) -> dict[str, Any]:
        """Extract requested keys from text into a validated dictionary."""
        if not text or not target_keys:
            return {}

        # 1. Offline fixture replay mode
        # A configured OpenAI-compatible endpoint may be local (for example,
        # LM Studio) and intentionally require no API key.  The service runtime
        # opts into live provider use only when an endpoint is configured; direct
        # clients without either an endpoint or key retain deterministic fallback.
        if self.demo_mode == "offline" or (not self.api_key and not self._endpoint_configured):
            return self._extract_from_fixtures_or_heuristics(text, source_type, target_keys)

        # 2. Live LLM Extraction with 1 retry on JSON failure
        user_prompt = (
            f"Source Type: {source_type}\n"
            f"Target Keys to extract: {json.dumps(target_keys)}\n\n"
            f"Text Content:\n{text}\n\n"
            "Respond with a JSON object mapping only these keys to their values "
            "(or null if absent)."
        )
        messages = [
            {"role": "system", "content": SYSTEM_EXTRACTION_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        for attempt in range(2):
            try:
                raw_response = self._call_chat_completion(messages, json_mode=True)
                # Strip potential markdown fences if returned
                clean_json = raw_response.strip("` \n")
                if clean_json.startswith("json"):
                    clean_json = clean_json[4:].strip()
                data = json.loads(clean_json)
                if isinstance(data, dict):
                    # Filter strictly to target_keys and exclude null values
                    return {k: v for k, v in data.items() if k in target_keys and v is not None}
            except Exception as e:
                logger.warning("LLM extraction attempt %d failed: %s", attempt + 1, e)

        # Fall back to heuristic/fixture extraction if live LLM endpoint is unreachable
        logger.info("Live LLM unavailable; falling back to heuristic/fixture extraction.")
        return self._extract_from_fixtures_or_heuristics(text, source_type, target_keys)

    def extract_field(self, text: str, field: str, source_doc_id: str | None) -> Any:
        """Targeted single-field re-extraction for portal recovery."""
        facts = self.extract_facts(text, "document", source_doc_id, [field])
        return facts.get(field)

    def explain(self, outcome: str, trace: list[dict[str, Any]], language: str) -> str:
        """Generate human-readable explanation respecting decision outcome and PII masking."""
        passed_rules = [t.get("rule_id", "") for t in trace if t.get("passed") is True]
        failed_rules = [t.get("fail_reason", "") for t in trace if t.get("passed") is False]

        # 1. Deterministic base message structure
        if outcome == "ELIGIBLE":
            msg = (
                f"Good news! Your application is eligible. All eligibility rules were satisfied "
                f"({', '.join(passed_rules) if passed_rules else 'verified'})."
            )
        elif outcome == "NOT_ELIGIBLE":
            reasons = "; ".join(failed_rules) if failed_rules else "criteria not satisfied"
            msg = f"Your application is not eligible under scheme rules. Reason: {reasons}."
        elif outcome == "NEEDS_DOCUMENTS":
            msg = (
                "Additional documents are required to complete your application. "
                "Please upload the requested files."
            )
        elif outcome == "NEEDS_INFO":
            msg = "A quick declaration is needed to complete your application."
        else:
            msg = "Your application has been received and routed for human reviewer verification."

        # 2. Mask any raw identifiers (Aadhaar, bank numbers)
        safe_msg = mask_identifiers(msg)

        # 3. Enforce Telegram 4096 character constraint
        if len(safe_msg) > 4096:
            safe_msg = safe_msg[:4090] + "..."

        return safe_msg

    def _extract_from_fixtures_or_heuristics(
        self, text: str, source_type: str, target_keys: list[str]
    ) -> dict[str, Any]:
        """Deterministic heuristic extraction matching fixtures when in offline mode."""
        extracted: dict[str, Any] = {}
        lowered = text.lower()

        # Check matched fixture records
        for scenario_facts in self._fixtures.values():
            for key in target_keys:
                if key in scenario_facts and key not in extracted:
                    extracted[key] = scenario_facts[key]

        # Heuristic fallbacks matching our mock schemes
        if "is_income_tax_payer" in target_keys:
            if "nobody" in lowered and "tax" in lowered:
                extracted["is_income_tax_payer"] = False
            elif "pays annual income tax" in lowered or "we pay income tax" in lowered:
                extracted["is_income_tax_payer"] = True
            elif "not" in lowered and "tax" in lowered:
                extracted["is_income_tax_payer"] = False
            elif any(w in lowered for w in ("farmer", "kisan", "cultivat", "agriculture", "land")):
                extracted["is_income_tax_payer"] = False

        if "institution_recognized" in target_keys:
            if "recognized" in lowered or "approved" in lowered:
                extracted["institution_recognized"] = True
            elif "unapproved" in lowered or "unaccredited" in lowered:
                extracted["institution_recognized"] = False

        if "applicant_name" in target_keys and "name:" in lowered:
            match = re.search(r"name:\s*([^\n\r,]+)", text, re.IGNORECASE)
            if match:
                extracted["applicant_name"] = match.group(1).strip()

        if "aadhaar_last4" in target_keys:
            match = re.search(r"\b(\d{4})\b(?=[^\d]*$)", text) or re.search(
                r"xxxx[ -]?xxxx[ -]?(\d{4})", lowered
            )
            if match:
                extracted["aadhaar_last4"] = match.group(1)

        if "land_owned_hectares" in target_keys:
            match = re.search(r"(\d+(?:\.\d+)?)\s*hectares?", lowered)
            if match:
                extracted["land_owned_hectares"] = float(match.group(1))

        if "holder_type" in target_keys:
            if "individual" in lowered:
                extracted["holder_type"] = "individual"
            elif "institutional" in lowered:
                extracted["holder_type"] = "institutional"

        if "bank_account_number" in target_keys:
            match = re.search(r"account\s*(?:no\.?|number)[:\s]*([0-9]{9,18})", lowered)
            if match:
                extracted["bank_account_number"] = match.group(1)

        if "bank_ifsc" in target_keys:
            match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
            if match:
                extracted["bank_ifsc"] = match.group(1)

        if "family_income_annual" in target_keys:
            match = re.search(r"rs\.?\s*([0-9,]+)", lowered)
            if match:
                val = match.group(1).replace(",", "")
                extracted["family_income_annual"] = float(val)

        if "last_exam_percentage" in target_keys:
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
            if match:
                extracted["last_exam_percentage"] = float(match.group(1))

        return {k: v for k, v in extracted.items() if k in target_keys and v is not None}
