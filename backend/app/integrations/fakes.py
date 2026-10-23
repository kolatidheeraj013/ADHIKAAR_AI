"""Deterministic offline fakes for the Phase 3 walking skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class FakeSpeechClient:
    def __init__(self, transcript: str, transcript_en: str | None = None) -> None:
        self.transcript = transcript
        self.transcript_en = transcript_en or transcript

    def transcribe(self, voice_path: str, language: str) -> str:
        return self.transcript_en


class FakeDocClassifier:
    def __init__(self, results: dict[str, dict[str, Any]] | None = None) -> None:
        self.results = results or {}

    def classify(self, path: str) -> dict[str, Any]:
        if path in self.results:
            return dict(self.results[path])
        lowered = path.lower()
        labels = (
            ("land", "land_record"),
            ("aadhaar", "aadhaar"),
            ("passbook", "bank_passbook"),
            ("income", "income_certificate"),
            ("marksheet", "marksheet"),
            ("bonafide", "bonafide_certificate"),
        )
        doc_type = next((label for needle, label in labels if needle in lowered), "other")
        quality = "blurry" if "blurry" in lowered else "good"
        return {
            "doc_type": doc_type,
            "doc_type_conf": 0.98,
            "quality": quality,
            "quality_conf": 0.95,
        }


class FakeOCRClient:
    def __init__(self, texts: dict[str, str] | None = None, confidence: float = 0.95) -> None:
        self.texts = texts or {}
        self.confidence = confidence

    def ocr(self, path: str) -> dict[str, Any]:
        return {
            "text": self.texts.get(path, "SAMPLE — NOT A REAL DOCUMENT"),
            "confidence": self.confidence,
        }


class FakeLLMClient:
    def __init__(
        self,
        document_facts: dict[str, dict[str, Any]] | None = None,
        declaration_facts: dict[str, Any] | None = None,
        targeted_fields: dict[tuple[str, str], Any] | None = None,
    ) -> None:
        self.document_facts = document_facts or {}
        self.declaration_facts = declaration_facts or {}
        self.targeted_fields = targeted_fields or {}

    def extract_facts(
        self, text: str, source_type: str, source_doc_id: str | None, target_keys: list[str]
    ) -> dict[str, Any]:
        if source_type == "declaration":
            extracted = {
                key: self.declaration_facts[key]
                for key in target_keys
                if key in self.declaration_facts
            }
            lowered = text.lower()
            if "is_income_tax_payer" in target_keys and "tax" in lowered:
                extracted.setdefault("is_income_tax_payer", "nobody" not in lowered)
            return extracted
        available = self.document_facts.get(source_doc_id or "", {})
        return {key: available[key] for key in target_keys if key in available}

    def extract_field(self, text: str, field: str, source_doc_id: str | None) -> Any:
        return self.targeted_fields.get((source_doc_id or "", field))

    def explain(self, outcome: str, trace: list[dict[str, Any]], language: str) -> str:
        if outcome == "ELIGIBLE":
            return "Your MOCK scheme application is eligible."
        if outcome == "NOT_ELIGIBLE":
            return "Your MOCK scheme application is not eligible under the recorded rules."
        return "More information is required for this MOCK scheme application."


class FakeRetriever:
    def retrieve(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        scholarship_words = ("scholar", "student", "education")
        scheme_id = (
            "state_scholarship_mock"
            if any(word in query.lower() for word in scholarship_words)
            else "pm_kisan_mock"
        )
        return [
            {
                "scheme_id": scheme_id,
                "text": f"MOCK guidance for {scheme_id}",
                "source": f"{scheme_id}.md",
                "score": 1.0,
            }
        ]


class FakePortalClient:
    def __init__(self, fail_mode: str = "none") -> None:
        self.fail_mode = fail_mode
        self.submit_calls = 0
        self.submissions: list[dict[str, Any]] = []

    def submit(self, scheme_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.submit_calls += 1
        self.submissions.append({"scheme_id": scheme_id, "payload": dict(payload)})
        if self.fail_mode == "timeout":
            return {
                "ok": False,
                "error": {"kind": "timeout", "code": "timeout", "message": "MOCK timeout"},
            }
        if self.fail_mode == "reject_permanent":
            return {
                "ok": False,
                "error": {
                    "kind": "permanent",
                    "code": "duplicate_application",
                    "message": "MOCK duplicate",
                },
            }
        for required in ("applicant_name", "aadhaar_last4", "bank_account_number", "bank_ifsc"):
            if not payload.get(required):
                return {
                    "ok": False,
                    "error": {
                        "kind": "validation",
                        "code": "missing_field",
                        "field": required,
                        "message": f"Missing {required}",
                    },
                }
        portal_ref = f"MOCK-PORTAL-{self.submit_calls:03d}"
        return {"ok": True, "portal_ref": portal_ref}

    def verify(self, portal_ref: str) -> dict[str, Any]:
        if self.fail_mode == "stalled":
            return {"ok": True, "portal_ref": portal_ref, "status": "stalled", "days_stalled": 45}
        return {"ok": True, "portal_ref": portal_ref, "status": "accepted"}


@dataclass
class FakeNotifier:
    messages: list[dict[str, Any]] = field(default_factory=list)

    def notify(
        self,
        case_id: str,
        language: str,
        kind: str,
        text: str,
        options: list[dict[str, Any]] | None = None,
        message_id: str | None = None,
    ) -> bool:
        self.messages.append(
            {
                "case_id": case_id,
                "language": language,
                "kind": kind,
                "text": text,
                "options": options or [],
            }
        )
        return True


class FakeStorageBackend:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def store(self, case_id: str, filename: str, content: bytes) -> str:
        path = f"{case_id}/{filename}"
        self.files[path] = content
        return path

    def retrieve(self, storage_path: str) -> bytes:
        return self.files[storage_path]

    def delete(self, storage_path: str) -> None:
        self.files.pop(storage_path, None)
