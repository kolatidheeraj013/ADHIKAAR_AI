"""Document classifier inference with a safe, offline heuristic fallback."""

from __future__ import annotations

import os
import statistics
from pathlib import Path
from typing import Any

from .model import DOC_TYPE_LABELS, QUALITY_LABELS, DualHeadResNet18, torch_available

try:  # Optional at runtime; model inference is disabled without these packages.
    import torch
except ImportError:  # pragma: no cover - depends on deployment extras
    torch = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:  # pragma: no cover - depends on deployment extras
    Image = None  # type: ignore[assignment]


_TYPE_HINTS = (
    ("aadhaar", "aadhaar"),
    ("land", "land_record"),
    ("income", "income_certificate"),
    ("passbook", "bank_passbook"),
    ("marksheet", "marksheet"),
    ("bonafide", "bonafide_certificate"),
)


class DocumentClassifier:
    """Classify documents using a local checkpoint, falling back to heuristics.

    The public ``classify`` method satisfies ``integrations.interfaces.DocClassifier``
    and always returns both heads, even when optional ML dependencies are absent.
    No weights are downloaded and malformed checkpoints simply select fallback mode.
    """

    def __init__(
        self,
        weights_path: str | Path | None = None,
        *,
        device: str = "cpu",
        model: Any | None = None,
    ) -> None:
        configured_path = os.getenv(
            "CLASSIFIER_WEIGHTS_PATH", "./ml_training/weights/doc_classifier.pt"
        )
        self.weights_path = Path(weights_path or configured_path)
        self.device = device
        self.model = model
        self.using_model = model is not None
        if model is None:
            self._load_model()

    def _load_model(self) -> None:
        if not (torch_available() and torch is not None and Image is not None):
            return
        if not self.weights_path.is_file():
            return
        try:
            model = DualHeadResNet18()
            try:
                checkpoint = torch.load(
                    self.weights_path, map_location=self.device, weights_only=False
                )
            except TypeError:  # PyTorch before the weights_only keyword.
                checkpoint = torch.load(self.weights_path, map_location=self.device)
            state_dict = (
                checkpoint.get("model_state_dict", checkpoint)
                if isinstance(checkpoint, dict)
                else checkpoint
            )
            model.load_state_dict(state_dict)
            model.to(self.device)
            model.eval()
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            return
        self.model = model
        self.using_model = True

    def classify(self, path: str) -> dict[str, Any]:
        """Return labels and softmax-like confidence for both classifier heads."""

        if self.model is not None and Image is not None and torch is not None:
            result = self._classify_with_model(path)
            if result is not None:
                return result
        return self._classify_with_heuristics(path)

    def _classify_with_model(self, path: str) -> dict[str, Any] | None:
        try:
            image = Image.open(path).convert("RGB").resize((224, 224))
            values = list(image.getdata())
            tensor = torch.tensor(
                values, dtype=torch.float32, device=self.device
            ).reshape(224, 224, 3)
            tensor = tensor.permute(2, 0, 1).div(255.0).unsqueeze(0)
            mean = torch.tensor([0.485, 0.456, 0.406], device=self.device).reshape(1, 3, 1, 1)
            std = torch.tensor([0.229, 0.224, 0.225], device=self.device).reshape(1, 3, 1, 1)
            with torch.no_grad():
                doc_logits, quality_logits = self.model((tensor - mean) / std)
                doc_probs = torch.softmax(doc_logits, dim=1)[0]
                quality_probs = torch.softmax(quality_logits, dim=1)[0]
            doc_index = int(torch.argmax(doc_probs).item())
            quality_index = int(torch.argmax(quality_probs).item())
            return {
                "doc_type": DOC_TYPE_LABELS[doc_index],
                "doc_type_conf": float(doc_probs[doc_index].item()),
                "quality": QUALITY_LABELS[quality_index],
                "quality_conf": float(quality_probs[quality_index].item()),
            }
        except (OSError, RuntimeError, ValueError, IndexError, TypeError):
            return None

    def _classify_with_heuristics(self, path: str) -> dict[str, Any]:
        lowered = Path(path).name.lower()
        doc_type, doc_conf = "other", 0.35
        for needle, label in _TYPE_HINTS:
            if needle in lowered:
                doc_type, doc_conf = label, 0.90
                break

        quality = "good"
        quality_conf = 0.55
        for label in QUALITY_LABELS[1:]:
            if label in lowered:
                quality, quality_conf = label, 0.92
                break
        pixels = _grayscale_pixels(Path(path))
        if pixels:
            brightness = statistics.fmean(pixels)
            spread = statistics.pvariance(pixels) if len(pixels) > 1 else 0.0
            if brightness < 70:
                quality, quality_conf = "too_dark", 0.90
            elif spread < 120:
                quality, quality_conf = "blurry", 0.72
            elif quality == "good":
                quality, quality_conf = "good", 0.68
        return {
            "doc_type": doc_type,
            "doc_type_conf": doc_conf,
            "quality": quality,
            "quality_conf": quality_conf,
        }


def _grayscale_pixels(path: Path) -> list[float]:
    if not path.is_file():
        return []
    try:
        if Image is not None:
            image = Image.open(path).convert("L")
            # Sampling keeps fallback inference bounded for large uploads.
            image.thumbnail((128, 128))
            return [float(value) for value in image.getdata()]
        data = path.read_bytes()
        if data.startswith(b"P6"):
            header_end = data.find(b"\n255\n")
            if header_end != -1:
                raw = data[header_end + len(b"\n255\n") :]
                return [
                    float((raw[i] + raw[i + 1] + raw[i + 2]) / 3)
                    for i in range(0, len(raw) - 2, 3)
                ]
    except (OSError, ValueError, IndexError):
        pass
    return []


# A short alias is convenient for dependency injection while preserving the
# descriptive class name for callers and documentation.
Classifier = DocumentClassifier
DocClassifier = DocumentClassifier

__all__ = ["Classifier", "DocClassifier", "DocumentClassifier"]
