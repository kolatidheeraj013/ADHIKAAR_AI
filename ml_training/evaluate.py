"""Evaluation entry point for a local synthetic classifier checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .synth_data import DOC_TYPE_LABELS, QUALITY_LABELS
except ImportError:
    from synth_data import DOC_TYPE_LABELS, QUALITY_LABELS


def evaluate(
    data_dir: str | Path = "ml_training/data/doc_classifier",
    weights_path: str | Path = "ml_training/weights/doc_classifier.pt",
    report_path: str | Path = "ml_training/reports/doc_classifier_eval.json",
) -> dict[str, Any]:
    """Evaluate a checkpoint when dependencies exist, otherwise report fallback mode."""

    try:
        try:
            from backend.app.ml.classifier import DocumentClassifier
            from backend.app.ml.model import torch_available
        except ModuleNotFoundError:
            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
            from app.ml.classifier import DocumentClassifier
            from app.ml.model import torch_available
    except ImportError as exc:
        result = _fallback(f"optional evaluation dependency unavailable: {exc}")
        _write(result, report_path)
        return result

    try:
        from PIL import Image as _PILImage
    except ImportError:
        _PILImage = None
    if not torch_available() or _PILImage is None:
        result = _fallback("optional evaluation dependency unavailable: install torch and Pillow")
        _write(result, report_path)
        return result

    manifest_path = Path(data_dir) / "manifest.json"
    if not manifest_path.is_file() or not Path(weights_path).is_file():
        result = _fallback("synthetic manifest or local weights are missing")
        _write(result, report_path)
        return result
    try:
        records = json.loads(manifest_path.read_text(encoding="utf-8"))
        test_records = [
            record for record in records if "/test/" in record["path"].replace("\\", "/")
        ]
        classifier = DocumentClassifier(weights_path)
        doc_matrix = [[0 for _ in DOC_TYPE_LABELS] for _ in DOC_TYPE_LABELS]
        quality_matrix = [[0 for _ in QUALITY_LABELS] for _ in QUALITY_LABELS]
        for record in test_records:
            predicted = classifier.classify(record["path"])
            doc_row = DOC_TYPE_LABELS.index(record["doc_type"])
            doc_column = DOC_TYPE_LABELS.index(predicted["doc_type"])
            quality_row = QUALITY_LABELS.index(record["quality"])
            quality_column = QUALITY_LABELS.index(predicted["quality"])
            doc_matrix[doc_row][doc_column] += 1
            quality_matrix[quality_row][quality_column] += 1
        doc_total = sum(map(sum, doc_matrix))
        quality_total = sum(map(sum, quality_matrix))
        result = {
            "status": "evaluated",
            "synthetic_only": True,
            "doc_type_accuracy": _accuracy(doc_matrix, doc_total),
            "quality_accuracy": _accuracy(quality_matrix, quality_total),
            "confusion_matrices": {"doc_type": doc_matrix, "quality": quality_matrix},
            "test_samples": len(test_records),
        }
    except (OSError, ValueError, IndexError, RuntimeError, TypeError) as exc:
        result = _fallback(f"evaluation unavailable: {exc}")
    _write(result, report_path)
    return result


def _accuracy(matrix: list[list[int]], total: int) -> float:
    return sum(matrix[index][index] for index in range(len(matrix))) / total if total else 0.0


def _fallback(reason: str) -> dict[str, Any]:
    return {"status": "fallback", "synthetic_only": True, "reason": reason}


def _write(result: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the synthetic document classifier")
    parser.add_argument("--data-dir", default="ml_training/data/doc_classifier")
    parser.add_argument("--weights", default="ml_training/weights/doc_classifier.pt")
    parser.add_argument("--report", default="ml_training/reports/doc_classifier_eval.json")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.data_dir, args.weights, args.report), indent=2))


if __name__ == "__main__":
    main()
