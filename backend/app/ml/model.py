"""The shared-backbone, dual-head document classifier.

Torch is deliberately an optional runtime dependency.  The backend can still
run in its deterministic heuristic mode on small deployments that do not
install the training stack.
"""

from __future__ import annotations

from typing import Any

DOC_TYPE_LABELS = (
    "aadhaar",
    "land_record",
    "income_certificate",
    "bank_passbook",
    "marksheet",
    "bonafide_certificate",
    "other",
)
QUALITY_LABELS = ("good", "blurry", "cropped", "too_dark")

try:  # pragma: no cover - exercised when the optional ML extra is installed
    import torch
    from torch import Tensor, nn
except ImportError:  # pragma: no cover - the fallback is covered instead
    torch = None  # type: ignore[assignment]
    Tensor = Any  # type: ignore[misc,assignment]
    nn = None  # type: ignore[assignment]


def torch_available() -> bool:
    """Return whether the optional PyTorch inference/training stack is present."""

    return torch is not None


if nn is not None:

    class _BasicBlock(nn.Module):
        expansion = 1

        def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
            super().__init__()
            self.conv1 = nn.Conv2d(
                in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False
            )
            self.bn1 = nn.BatchNorm2d(out_channels)
            self.relu = nn.ReLU(inplace=True)
            self.conv2 = nn.Conv2d(
                out_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False
            )
            self.bn2 = nn.BatchNorm2d(out_channels)
            self.shortcut = (
                nn.Sequential(
                    nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                    nn.BatchNorm2d(out_channels),
                )
                if stride != 1 or in_channels != out_channels
                else nn.Identity()
            )

        def forward(self, x: Tensor) -> Tensor:
            residual = self.shortcut(x)
            x = self.relu(self.bn1(self.conv1(x)))
            x = self.bn2(self.conv2(x))
            return self.relu(x + residual)

    class DualHeadResNet18(nn.Module):
        """ResNet-18-style backbone with document type and quality heads.

        ``pretrained`` is accepted for API compatibility but intentionally does
        not download weights.  A local checkpoint can be loaded by the
        classifier or training script instead.
        """

        def __init__(
            self,
            num_doc_types: int = len(DOC_TYPE_LABELS),
            num_qualities: int = len(QUALITY_LABELS),
            pretrained: bool = False,
        ) -> None:
            del pretrained
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False),
                nn.BatchNorm2d(64),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(kernel_size=3, stride=2, padding=1),
                self._layer(64, 64, 2, 1),
                self._layer(64, 128, 2, 2),
                self._layer(128, 256, 2, 2),
                self._layer(256, 512, 2, 2),
                nn.AdaptiveAvgPool2d((1, 1)),
            )
            self.doc_type_head = nn.Linear(512, num_doc_types)
            self.quality_head = nn.Linear(512, num_qualities)

        @staticmethod
        def _layer(in_channels: int, out_channels: int, blocks: int, stride: int) -> nn.Sequential:
            layers = [_BasicBlock(in_channels, out_channels, stride)]
            layers.extend(_BasicBlock(out_channels, out_channels) for _ in range(blocks - 1))
            return nn.Sequential(*layers)

        def forward(self, x: Tensor) -> tuple[Tensor, Tensor]:
            features = self.backbone(x).flatten(1)
            return self.doc_type_head(features), self.quality_head(features)


else:

    class DualHeadResNet18:  # type: ignore[no-redef]
        """Import-safe placeholder used when PyTorch is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            raise RuntimeError(
                "PyTorch is required for DualHeadResNet18; use the heuristic classifier fallback"
            )


__all__ = ["DOC_TYPE_LABELS", "QUALITY_LABELS", "DualHeadResNet18", "torch_available"]
