"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    env: str = field(default_factory=lambda: os.getenv("ENV", "dev"))
    demo_mode: str = field(default_factory=lambda: os.getenv("DEMO_MODE", "offline"))
    service_token: str = field(default_factory=lambda: os.getenv("SERVICE_TOKEN", "change-me"))
    reviewer_password: str = field(
        default_factory=lambda: os.getenv("REVIEWER_PASSWORD", "change-me")
    )
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "sqlite:///./backend/adhikaar.db"
        )
    )

    # Sarvam AI
    sarvam_api_key: str = field(default_factory=lambda: os.getenv("SARVAM_API_KEY", ""))

    # LLM Settings
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai"))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4.1"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))

    # Storage & ML
    storage_backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local"))
    storage_dir: Path = field(default_factory=lambda: Path(os.getenv("STORAGE_DIR", "./storage")))
    classifier_weights_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("CLASSIFIER_WEIGHTS_PATH", "./ml_training/weights/doc_classifier.pt")
        )
    )
    chroma_path: Path = field(default_factory=lambda: Path(os.getenv("CHROMA_PATH", "./.chroma")))
    mock_portal_url: str = field(
        default_factory=lambda: os.getenv("MOCK_PORTAL_URL", "http://localhost:8100")
    )
    mock_portal_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("MOCK_PORTAL_TIMEOUT_SECONDS", "5"))
    )

    # Thresholds & Limits
    auto_submit_threshold: float = field(
        default_factory=lambda: float(os.getenv("AUTO_SUBMIT_THRESHOLD", "0.85"))
    )
    review_threshold: float = field(
        default_factory=lambda: float(os.getenv("REVIEW_THRESHOLD", "0.60"))
    )
    max_voice_seconds: int = field(
        default_factory=lambda: int(os.getenv("MAX_VOICE_SECONDS", "30"))
    )
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "10")))
    max_docs_per_case: int = field(default_factory=lambda: int(os.getenv("MAX_DOCS_PER_CASE", "8")))
    retention_days: int = field(default_factory=lambda: int(os.getenv("RETENTION_DAYS", "7")))


settings = Settings()
