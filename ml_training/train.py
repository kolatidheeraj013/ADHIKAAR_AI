"""Offline training entry point for the synthetic dual-head classifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .synth_data import DOC_TYPE_LABELS, QUALITY_LABELS, generate_dataset
except ImportError:  # Running ``python ml_training/train.py`` from the repo root.
    from synth_data import DOC_TYPE_LABELS, QUALITY_LABELS, generate_dataset


def train_model(
    data_dir: str | Path = "ml_training/data/doc_classifier",
    weights_path: str | Path = "ml_training/weights/doc_classifier.pt",
    report_path: str | Path = "ml_training/reports/doc_classifier.json",
    *,
    samples_per_type: int = 30,
    epochs: int = 5,
    seed: int = 7,
) -> dict[str, Any]:
    """Train locally when torch/Pillow are installed, otherwise write a safe report."""

    data_root = Path(data_dir)
    manifest_path = data_root / "manifest.json"
    if not manifest_path.is_file():
        generate_dataset(data_root, samples_per_type=samples_per_type, seed=seed)

    try:
        import torch
        from PIL import Image

        try:
            from backend.app.ml.model import DualHeadResNet18
        except ModuleNotFoundError:
            import sys

            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
            from app.ml.model import DualHeadResNet18
    except ImportError as exc:
        report = _fallback_report(f"optional training dependency unavailable: {exc}")
        _write_report(report, report_path)
        return report

    try:
        records = json.loads(manifest_path.read_text(encoding="utf-8"))
        train_records = [
            record for record in records if "/train/" in record["path"].replace("\\", "/")
        ]
        val_records = [
            record for record in records if "/val/" in record["path"].replace("\\", "/")
        ]
        if not train_records or not val_records:
            raise ValueError("manifest must contain train and val samples")
        torch.manual_seed(seed)
        model = DualHeadResNet18()
        for parameter in model.backbone.parameters():
            parameter.requires_grad = False
        optimizer = torch.optim.Adam(
            [parameter for parameter in model.parameters() if parameter.requires_grad], lr=1e-3
        )
        loss_fn = torch.nn.CrossEntropyLoss()
        best_loss = float("inf")
        best_state = None
        for epoch in range(max(1, epochs)):
            if epoch == 3:
                for parameter in model.backbone[-7:].parameters():
                    parameter.requires_grad = True
                optimizer = torch.optim.Adam(
                    [parameter for parameter in model.parameters() if parameter.requires_grad],
                    lr=1e-4,
                )
            model.train()
            train_loss = _run_epoch(model, train_records, Image, torch, loss_fn, optimizer)
            model.eval()
            with torch.no_grad():
                val_loss = _run_epoch(model, val_records, Image, torch, loss_fn, None)
            if val_loss < best_loss:
                best_loss = val_loss
                best_state = {
                    key: value.detach().cpu() for key, value in model.state_dict().items()
                }
            if epoch == 0 and train_loss < 0:  # pragma: no cover - defensive, never true
                break
        if best_state is None:
            raise RuntimeError("training did not produce a checkpoint")
        weights = Path(weights_path)
        weights.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "model_state_dict": best_state,
                "doc_type_labels": DOC_TYPE_LABELS,
                "quality_labels": QUALITY_LABELS,
            },
            weights,
        )
        report = {
            "status": "trained",
            "synthetic_only": True,
            "epochs": max(1, epochs),
            "best_val_loss": best_loss,
            "doc_type_accuracy": None,
            "quality_accuracy": None,
            "confusion_matrices": {"doc_type": [], "quality": []},
            "weights": str(weights),
        }
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        report = _fallback_report(f"training unavailable: {exc}")
    _write_report(report, report_path)
    return report


def _run_epoch(
    model: Any,
    records: list[dict[str, Any]],
    image_cls: Any,
    torch: Any,
    loss_fn: Any,
    optimizer: Any,
) -> float:
    losses = []
    for record in records:
        image = image_cls.open(record["path"]).convert("RGB").resize((224, 224))
        values = torch.tensor(list(image.getdata()), dtype=torch.float32).reshape(224, 224, 3)
        inputs = values.permute(2, 0, 1).div(255).unsqueeze(0)
        doc_target = torch.tensor([DOC_TYPE_LABELS.index(record["doc_type"])])
        quality_target = torch.tensor([QUALITY_LABELS.index(record["quality"])])
        doc_logits, quality_logits = model(inputs)
        loss = loss_fn(doc_logits, doc_target) + loss_fn(quality_logits, quality_target)
        if optimizer is not None:
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        losses.append(float(loss.detach().item()))
    return sum(losses) / max(1, len(losses))


def _fallback_report(reason: str) -> dict[str, Any]:
    return {
        "status": "fallback",
        "synthetic_only": True,
        "reason": reason,
        "doc_type_accuracy": None,
        "quality_accuracy": None,
        "confusion_matrices": {"doc_type": [], "quality": []},
    }


def _write_report(report: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ADHIKAAR's synthetic document classifier")
    parser.add_argument("--data-dir", default="ml_training/data/doc_classifier")
    parser.add_argument("--weights", default="ml_training/weights/doc_classifier.pt")
    parser.add_argument("--report", default="ml_training/reports/doc_classifier.json")
    parser.add_argument("--samples-per-type", type=int, default=30)
    parser.add_argument("--epochs", type=int, default=5)
    args = parser.parse_args()
    result = train_model(
        args.data_dir,
        args.weights,
        args.report,
        samples_per_type=args.samples_per_type,
        epochs=args.epochs,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
