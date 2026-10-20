from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from app.ml.classifier import DocumentClassifier
from app.ml.model import (
    DOC_TYPE_LABELS,
    QUALITY_LABELS,
    DualHeadResNet18,
    torch_available,
)


def test_phase5_labels_match_spec() -> None:
    assert DOC_TYPE_LABELS == (
        "aadhaar",
        "land_record",
        "income_certificate",
        "bank_passbook",
        "marksheet",
        "bonafide_certificate",
        "other",
    )
    assert QUALITY_LABELS == ("good", "blurry", "cropped", "too_dark")


def test_synthetic_dataset_has_watermark_and_quality_labels(tmp_path: Path) -> None:
    from ml_training.synth_data import WATERMARK, generate_dataset

    records = generate_dataset(tmp_path / "docs", samples_per_type=4, seed=11)
    assert len(records) == len(DOC_TYPE_LABELS) * 4
    assert {record.quality for record in records} == set(QUALITY_LABELS)
    assert all(record.watermark == WATERMARK for record in records)
    assert all(Path(record.path).is_file() for record in records)
    manifest = (tmp_path / "docs" / "manifest.json").read_text(encoding="utf-8")
    assert WATERMARK in manifest


def test_classifier_uses_deterministic_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "aadhaar_blurry.ppm"
    image_path.write_bytes(b"P6\n1 1\n255\n" + bytes((240, 240, 240)))
    result = DocumentClassifier(weights_path=tmp_path / "missing.pt").classify(str(image_path))
    assert result["doc_type"] == "aadhaar"
    assert result["quality"] == "blurry"
    assert 0.0 <= result["doc_type_conf"] <= 1.0
    assert 0.0 <= result["quality_conf"] <= 1.0


@pytest.mark.skipif(not torch_available(), reason="optional PyTorch dependency is not installed")
def test_dual_head_model_output_shape() -> None:
    torch = pytest.importorskip("torch")
    model = DualHeadResNet18()
    doc_logits, quality_logits = model(torch.randn(2, 3, 224, 224))
    assert tuple(doc_logits.shape) == (2, len(DOC_TYPE_LABELS))
    assert tuple(quality_logits.shape) == (2, len(QUALITY_LABELS))


def test_training_entry_point_reports_safe_fallback_without_heavy_dependencies(
    tmp_path: Path,
) -> None:
    if importlib.util.find_spec("torch") and importlib.util.find_spec("PIL"):
        pytest.skip("fallback-only assertion is for the minimal dependency environment")
    from ml_training.train import train_model

    report = train_model(
        data_dir=tmp_path / "dataset",
        weights_path=tmp_path / "weights.pt",
        report_path=tmp_path / "report.json",
        samples_per_type=1,
        epochs=1,
    )
    assert report["status"] == "fallback"
    assert report["synthetic_only"] is True
