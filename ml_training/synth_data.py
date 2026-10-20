"""Offline-only synthetic document images for Phase 5.

The generator never reads a source document or calls a network service.  PIL
is used when installed; a small PPM renderer keeps dataset generation useful in
the minimal backend environment as well.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
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
WATERMARK = "SAMPLE — NOT A REAL DOCUMENT"

try:  # Optional for the training workstation, not needed by the backend.
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - exercised in minimal installations
    Image = ImageDraw = ImageEnhance = ImageFilter = ImageFont = None  # type: ignore[assignment]


@dataclass(frozen=True)
class DocumentSample:
    path: str
    doc_type: str
    quality: str
    watermark: str = WATERMARK


class _PPMImage:
    """Tiny dependency-free RGB image used only when Pillow is unavailable."""

    def __init__(self, width: int, height: int, pixels: bytearray) -> None:
        self.width, self.height, self.pixels = width, height, pixels

    def save(self, path: str | Path, format: str | None = None) -> None:
        del format
        target = Path(path)
        target.write_bytes(
            f"P6\n# {WATERMARK}\n{self.width} {self.height}\n255\n".encode("utf-8")
            + bytes(self.pixels)
        )


# A compact 5x7 font makes the required watermark visibly present without a
# graphics dependency.  Only characters used by the marker and mock labels are
# needed.
_FONT = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "—": ("00000", "00000", "11111", "00000", "00000", "00000", "00000"),
    " ": ("00000",) * 7,
}


def _ppm_pixel(image: _PPMImage, x: int, y: int, colour: tuple[int, int, int]) -> None:
    if 0 <= x < image.width and 0 <= y < image.height:
        offset = (y * image.width + x) * 3
        image.pixels[offset : offset + 3] = bytes(colour)


def _ppm_rect(
    image: _PPMImage, x: int, y: int, width: int, height: int, colour: tuple[int, int, int]
) -> None:
    for row in range(y, y + height):
        for col in range(x, x + width):
            _ppm_pixel(image, col, row, colour)


def _ppm_text(
    image: _PPMImage, text: str, x: int, y: int, scale: int, colour: tuple[int, int, int]
) -> None:
    cursor = x
    for character in text:
        glyph = _FONT.get(character.upper(), _FONT[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == "1":
                    _ppm_rect(image, cursor + col * scale, y + row * scale, scale, scale, colour)
        cursor += 6 * scale


def _render_ppm(doc_type: str, quality: str, seed: int, size: tuple[int, int]) -> _PPMImage:
    rng = random.Random(seed)
    width, height = size
    base = (245, 245, 238)
    image = _PPMImage(width, height, bytearray(base * (width * height)))
    _ppm_rect(image, 10, 10, width - 20, height - 20, (255, 255, 250))
    _ppm_rect(image, 20, 22, width - 40, 18, (45, 86, 125))
    _ppm_text(image, doc_type.replace("_", " ").upper()[:18], 28, 27, 1, (255, 255, 255))
    for row in range(65, height - 35, 20):
        line_width = rng.randint(max(40, width // 3), max(50, width - 55))
        _ppm_rect(image, 28, row, line_width, 3, (110, 110, 105))
    _ppm_text(image, WATERMARK, 18, height // 2 - 12, 1, (180, 35, 35))
    if quality == "too_dark":
        image.pixels = bytearray(max(0, int(value * 0.35)) for value in image.pixels)
    elif quality == "cropped":
        # Simulate a missing edge while retaining the original canvas size.
        _ppm_rect(image, 0, 0, 18, height, (40, 40, 40))
        _ppm_rect(image, width - 18, 0, 18, height, (40, 40, 40))
    elif quality == "blurry":
        source = bytes(image.pixels)
        for row in range(1, height - 1):
            for col in range(1, width - 1):
                offset = (row * width + col) * 3
                for channel in range(3):
                    neighbours = [
                        source[offset + channel],
                        source[offset - 3 + channel],
                        source[offset + 3 + channel],
                    ]
                    image.pixels[offset + channel] = sum(neighbours) // len(neighbours)
    return image


def _font() -> Any:
    if ImageFont is None:
        return None
    try:
        return ImageFont.truetype("DejaVuSans.ttf", 15)
    except (OSError, IOError):
        return ImageFont.load_default()


def render_document(
    doc_type: str,
    quality: str = "good",
    *,
    seed: int = 0,
    size: tuple[int, int] = (512, 320),
) -> Any:
    """Render one watermarked mock document and apply its quality degradation."""

    if doc_type not in DOC_TYPE_LABELS:
        raise ValueError(f"unknown document type: {doc_type}")
    if quality not in QUALITY_LABELS:
        raise ValueError(f"unknown quality label: {quality}")

    if Image is None:
        return _render_ppm(doc_type, quality, seed, size)

    rng = random.Random(seed)
    image = Image.new("RGB", size, (245, 245, 238))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, size[0] - 16, size[1] - 16), fill=(255, 255, 250), outline=(80, 80, 80))
    draw.rectangle((28, 28, size[0] - 28, 72), fill=(45, 86, 125))
    draw.text((42, 42), doc_type.replace("_", " ").upper(), fill=(255, 255, 255), font=_font())
    for row in range(100, size[1] - 45, 25):
        draw.line(
            (42, row, rng.randint(size[0] // 2, size[0] - 55), row),
            fill=(100, 100, 100),
            width=2,
        )
    draw.rectangle((size[0] - 130, 100, size[0] - 50, 180), outline=(60, 90, 120), width=2)
    draw.text((size[0] // 2 - 125, size[1] // 2 - 10), WATERMARK, fill=(190, 35, 35), font=_font())

    if quality == "blurry":
        image = image.filter(ImageFilter.GaussianBlur(radius=2.0))
    elif quality == "cropped":
        crop = image.crop((24, 12, size[0] - 5, size[1] - 8))
        image = crop.resize(size)
    elif quality == "too_dark":
        image = ImageEnhance.Brightness(image).enhance(0.35)
    return image


def _save_image(image: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if Image is not None:
        from PIL.PngImagePlugin import PngInfo

        metadata = PngInfo()
        metadata.add_text("watermark", WATERMARK)
        image.save(path, format="PNG", pnginfo=metadata)
    else:
        image.save(path, format=None)


def generate_dataset(
    output_dir: str | Path,
    *,
    samples_per_type: int = 30,
    seed: int = 7,
    split: tuple[float, float, float] = (0.8, 0.1, 0.1),
) -> list[DocumentSample]:
    """Generate a deterministic train/validation/test synthetic dataset.

    The returned records and ``manifest.json`` are the sole labels used by the
    training entry point; quality is the degradation applied to the clean
    rendered template, never an annotation inferred from an input image.
    """

    if samples_per_type < 1:
        raise ValueError("samples_per_type must be positive")
    if len(split) != 3 or abs(sum(split) - 1.0) > 1e-6 or any(value < 0 for value in split):
        raise ValueError("split must contain three non-negative fractions summing to 1")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    records: list[DocumentSample] = []
    rng = random.Random(seed)
    split_names = ("train", "val", "test")
    pending: list[tuple[str, str, int, int]] = []
    for doc_index, doc_type in enumerate(DOC_TYPE_LABELS):
        for sample_index in range(samples_per_type):
            quality = QUALITY_LABELS[sample_index % len(QUALITY_LABELS)]
            pending.append((doc_type, quality, doc_index * 10000 + sample_index, sample_index))
    rng.shuffle(pending)
    train_count = int(len(pending) * split[0])
    val_count = int(len(pending) * split[1])
    split_for_index = (
        [split_names[0]] * train_count
        + [split_names[1]] * val_count
        + [split_names[2]] * (len(pending) - train_count - val_count)
    )
    for (doc_type, quality, image_seed, sample_index), split_name in zip(pending, split_for_index):
        path = root / split_name / f"{doc_type}_{sample_index:04d}.{'png' if Image else 'ppm'}"
        image = render_document(doc_type, quality, seed=seed + image_seed)
        _save_image(image, path)
        records.append(DocumentSample(str(path), doc_type, quality))

    manifest = [asdict(record) for record in records]
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for split_name in split_names:
        split_records = [
            record for record in manifest if f"/{split_name}/" in record["path"].replace("\\", "/")
        ]
        (root / f"{split_name}.json").write_text(
            json.dumps(split_records, indent=2), encoding="utf-8"
        )
    return records


__all__ = [
    "DOC_TYPE_LABELS",
    "QUALITY_LABELS",
    "WATERMARK",
    "DocumentSample",
    "generate_dataset",
    "render_document",
]
