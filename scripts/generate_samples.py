"""Generate ready-to-test sample documents and audio notes for Phase 10 demo.

Implements DM-04:
- Clear, realistic synthetic mock documents stamped "SAMPLE — NOT A REAL DOCUMENT".
- Sample audio voice notes for Tamil, Telugu, Hindi, and English.
- Complete catalog index in data/samples/manifest.json.
- Zero network required; deterministic and offline.
"""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WATERMARK_TEXT = "SAMPLE — NOT A REAL DOCUMENT"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SAMPLES_DIR = DATA_DIR / "samples"


def _draw_watermark(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Draw repeated diagonal watermark across the image."""
    font = ImageFont.load_default()
    # Draw header and footer banner
    draw.rectangle([0, 0, width, 24], fill=(220, 53, 69))
    draw.text((10, 6), f"*** {WATERMARK_TEXT} ***", fill=(255, 255, 255), font=font)
    draw.rectangle([0, height - 24, width, height], fill=(220, 53, 69))
    draw.text((10, height - 18), f"*** {WATERMARK_TEXT} ***", fill=(255, 255, 255), font=font)

    # Diagonal watermark stripes
    for y_offset in range(60, height - 60, 90):
        draw.text((width // 6, y_offset), f"--- {WATERMARK_TEXT} ---", fill=(220, 100, 100, 120), font=font)


def create_aadhaar_sample(out_path: Path) -> None:
    width, height = 640, 400
    img = Image.new("RGB", (width, height), (250, 248, 242))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Tricolor header bar
    draw.rectangle([20, 30, width - 20, 36], fill=(255, 153, 51))
    draw.rectangle([20, 36, width - 20, 42], fill=(255, 255, 255))
    draw.rectangle([20, 42, width - 20, 48], fill=(19, 136, 8))

    draw.text((140, 55), "GOVERNMENT OF INDIA", fill=(20, 20, 20), font=font)
    draw.text((100, 70), "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", fill=(60, 60, 60), font=font)
    draw.line([(20, 90), (width - 20, 90)], fill=(180, 180, 180), width=1)

    # Photo placeholder box
    draw.rectangle([40, 110, 160, 250], outline=(100, 100, 100), width=2, fill=(230, 230, 235))
    draw.text((60, 170), "[PHOTO]", fill=(120, 120, 120), font=font)

    # Details
    draw.text((190, 115), "Name: Murugan K", fill=(10, 10, 10), font=font)
    draw.text((190, 135), "DOB: 14/08/1982", fill=(10, 10, 10), font=font)
    draw.text((190, 155), "Gender: Male", fill=(10, 10, 10), font=font)
    draw.text((190, 185), "Address: S/O Ramasamy, Vill Thanjavur Rural,", fill=(30, 30, 30), font=font)
    draw.text((190, 200), "Taluk Kumbakonam, Dist Thanjavur,", fill=(30, 30, 30), font=font)
    draw.text((190, 215), "Tamil Nadu - 613001", fill=(30, 30, 30), font=font)

    # Masked Aadhaar number
    draw.rectangle([140, 290, width - 140, 330], fill=(240, 240, 240), outline=(200, 200, 200))
    draw.text((210, 305), "XXXX XXXX 8942", fill=(10, 10, 10), font=font)
    draw.text((180, 340), "VID: 9182 3918 2910 2918", fill=(80, 80, 80), font=font)

    _draw_watermark(draw, width, height)
    img.save(out_path, "PNG")


def create_land_record_sample(out_path: Path, blurry: bool = False) -> None:
    width, height = 700, 500
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Border
    draw.rectangle([15, 28, width - 15, height - 28], outline=(40, 60, 40), width=2)

    # Header
    draw.text((150, 40), "REVENUE DEPARTMENT - GOVT OF TAMIL NADU", fill=(20, 60, 20), font=font)
    draw.text((170, 58), "EXTRACT OF REGISTER OF RIGHTS (ROR-1B / PATTA)", fill=(10, 10, 10), font=font)
    draw.line([(30, 78), (width - 30, 78)], fill=(100, 120, 100), width=2)

    # Location
    draw.text((40, 95), "District: Thanjavur", fill=(10, 10, 10), font=font)
    draw.text((260, 95), "Taluk: Kumbakonam Rural", fill=(10, 10, 10), font=font)
    draw.text((500, 95), "Village: Melacauvery", fill=(10, 10, 10), font=font)

    draw.line([(30, 115), (width - 30, 115)], fill=(200, 200, 200), width=1)

    # Table layout
    headers = ["Khata No", "Survey / Subdiv", "Pattadar Name", "Classification", "Total Extent"]
    col_x = [40, 140, 280, 430, 560]
    for x, h in zip(col_x, headers):
        draw.text((x, 130), h, fill=(50, 50, 50), font=font)
    draw.line([(30, 150), (width - 30, 150)], fill=(120, 120, 120), width=1)

    values = ["418", "184/2B", "Murugan K", "Agri Wet Land", "1.40 Hectares"]
    for x, v in zip(col_x, values):
        draw.text((x, 165), v, fill=(10, 10, 10), font=font)
    draw.line([(30, 190), (width - 30, 190)], fill=(200, 200, 200), width=1)

    # Additional legal notes
    draw.text((40, 220), "Holder Category: Individual Cultivator / Owner", fill=(30, 30, 30), font=font)
    draw.text((40, 240), "Status: Clear Title, Mutation Completed (Ref: MUT/TN/2022/8192)", fill=(30, 30, 30), font=font)
    draw.text((40, 260), "Encumbrance: NIL (Certified up to current fasli year)", fill=(30, 30, 30), font=font)

    # Seal and authority
    draw.rectangle([width - 220, 320, width - 40, 420], outline=(0, 50, 120), width=2)
    draw.text((width - 200, 340), "TAHSILDAR SEAL", fill=(0, 50, 120), font=font)
    draw.text((width - 210, 370), "Kumbakonam Taluk", fill=(0, 50, 120), font=font)
    draw.text((width - 200, 395), "Digitally Verified", fill=(0, 120, 0), font=font)

    _draw_watermark(draw, width, height)

    if blurry:
        img = img.filter(ImageFilter.GaussianBlur(radius=2.5))
        # Re-apply header watermark clearly so judges still see SAMPLE
        draw_blur = ImageDraw.Draw(img)
        draw_blur.rectangle([0, 0, width, 24], fill=(220, 53, 69))
        draw_blur.text((10, 6), f"*** {WATERMARK_TEXT} (SIMULATED BLURRY FOR SCENARIO C) ***", fill=(255, 255, 255), font=font)

    img.save(out_path, "PNG")


def create_bank_passbook_sample(out_path: Path, missing_ifsc: bool = False) -> None:
    width, height = 660, 420
    img = Image.new("RGB", (width, height), (248, 250, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Blue header
    draw.rectangle([0, 24, width, 80], fill=(0, 75, 145))
    draw.text((30, 36), "STATE BANK OF INDIA", fill=(255, 255, 255), font=font)
    draw.text((30, 54), "Branch: Main Branch Thanjavur | Code: 004128", fill=(200, 230, 255), font=font)

    # Details
    draw.text((40, 105), "Customer ID: CIF8129034", fill=(50, 50, 50), font=font)
    draw.text((40, 130), "Account Holder: Murugan K", fill=(10, 10, 10), font=font)
    draw.text((40, 155), "Account Number: 31094819201", fill=(10, 10, 10), font=font)
    draw.text((40, 180), "Account Type: Regular Savings Bank (SB)", fill=(50, 50, 50), font=font)

    if not missing_ifsc:
        draw.text((40, 210), "IFSC Code: SBIN0004128", fill=(0, 75, 145), font=font)
        draw.text((40, 230), "MICR Code: 600002041", fill=(50, 50, 50), font=font)
    else:
        # Simulate worn-out / fold-damaged IFSC line for Scenario D1 auto-recovery
        draw.rectangle([40, 210, 260, 235], fill=(220, 220, 220))
        draw.text((45, 216), "[UNREADABLE / FOLD CREASE]", fill=(120, 60, 60), font=font)
        # But printed elsewhere in small text
        draw.text((350, 310), "Reg. IFSC: SBIN0004128", fill=(150, 150, 150), font=font)

    draw.text((40, 260), "Nominee Registered: YES", fill=(30, 30, 30), font=font)
    draw.text((40, 280), "Passbook Issue Date: 12-04-2023", fill=(50, 50, 50), font=font)

    # Branch Stamp
    draw.ellipse([width - 180, 120, width - 40, 260], outline=(0, 60, 120), width=2)
    draw.text((width - 165, 175), "SBI THANJAVUR", fill=(0, 60, 120), font=font)
    draw.text((width - 160, 195), "OFFICIAL STAMP", fill=(0, 60, 120), font=font)

    _draw_watermark(draw, width, height)
    img.save(out_path, "PNG")


def create_income_cert_sample(out_path: Path) -> None:
    width, height = 660, 460
    img = Image.new("RGB", (width, height), (255, 255, 250))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    draw.rectangle([15, 28, width - 15, height - 28], outline=(100, 80, 50), width=2)
    draw.text((170, 42), "GOVERNMENT OF TAMIL NADU", fill=(40, 40, 40), font=font)
    draw.text((120, 60), "REVENUE ADMINISTRATION - TALUK OFFICE, MADURAI", fill=(20, 20, 20), font=font)
    draw.text((220, 80), "INCOME CERTIFICATE", fill=(120, 40, 0), font=font)
    draw.line([(30, 100), (width - 30, 100)], fill=(160, 160, 160), width=1)

    draw.text((40, 120), "Certificate Identification: INC/TN/2024/918231", fill=(60, 60, 60), font=font)
    draw.text((40, 140), "Date of Issue: 10-06-2024", fill=(60, 60, 60), font=font)

    body = [
        "This is to certify on careful revenue inquiry that the annual income of:",
        "Candidate / Parent: K. Arumugam",
        "Residing at: No. 14, Ward 4, Madurai Rural, Tamil Nadu",
        "From all legal sources (agricultural and allied labor) is:",
        "Rs. 140,000/- (Rupees One Lakh Forty Thousand Only) per annum.",
        "",
        "Purpose: For educational scholarship / government welfare assistance.",
    ]
    y = 175
    for line in body:
        draw.text((40, y), line, fill=(10, 10, 10), font=font)
        y += 22

    # Revenue seal
    draw.rectangle([width - 240, 320, width - 40, 410], outline=(120, 40, 0), width=2)
    draw.text((width - 220, 340), "TAHSILDAR SIGN & SEAL", fill=(120, 40, 0), font=font)
    draw.text((width - 210, 365), "Madurai Taluk Office", fill=(120, 40, 0), font=font)
    draw.text((width - 200, 385), "Status: VERIFIED", fill=(0, 120, 0), font=font)

    _draw_watermark(draw, width, height)
    img.save(out_path, "PNG")


def create_marksheet_sample(out_path: Path) -> None:
    width, height = 680, 480
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    draw.rectangle([15, 28, width - 15, height - 28], outline=(20, 40, 80), width=2)
    draw.text((120, 42), "STATE BOARD OF SECONDARY & HIGHER EDUCATION - TAMIL NADU", fill=(20, 40, 80), font=font)
    draw.text((180, 62), "SENIOR SECONDARY EXAMINATION SCORE CARD", fill=(10, 10, 10), font=font)
    draw.line([(30, 85), (width - 30, 85)], fill=(150, 150, 150), width=1)

    draw.text((40, 100), "Candidate Name: K. Arumugam", fill=(10, 10, 10), font=font)
    draw.text((40, 120), "Roll / Hall Ticket No: REG202481920", fill=(10, 10, 10), font=font)
    draw.text((40, 140), "Institution: Govt Higher Secondary School, Madurai", fill=(50, 50, 50), font=font)

    headers = ["Subject", "Maximum Marks", "Marks Secured", "Grade"]
    col_x = [40, 240, 400, 540]
    draw.line([(30, 170), (width - 30, 170)], fill=(100, 100, 100), width=1)
    for x, h in zip(col_x, headers):
        draw.text((x, 175), h, fill=(40, 40, 40), font=font)
    draw.line([(30, 195), (width - 30, 195)], fill=(100, 100, 100), width=1)

    rows = [
        ("Language I (Tamil)", "100", "82", "A"),
        ("Language II (English)", "100", "78", "B+"),
        ("Mathematics", "100", "85", "A"),
        ("Science", "100", "90", "A+"),
        ("Social Science", "100", "88", "A"),
    ]
    y = 205
    for sub, max_m, sec_m, gr in rows:
        draw.text((col_x[0], y), sub, fill=(20, 20, 20), font=font)
        draw.text((col_x[1], y), max_m, fill=(20, 20, 20), font=font)
        draw.text((col_x[2], y), sec_m, fill=(20, 20, 20), font=font)
        draw.text((col_x[3], y), gr, fill=(20, 20, 20), font=font)
        y += 24

    draw.line([(30, y + 5), (width - 30, y + 5)], fill=(100, 100, 100), width=1)
    draw.text((40, y + 15), "Total: 423 / 500 | Aggregate Percentage: 84.6%", fill=(0, 60, 140), font=font)
    draw.text((40, y + 35), "Result Classification: PASSED (FIRST CLASS WITH DISTINCTION)", fill=(0, 120, 0), font=font)

    _draw_watermark(draw, width, height)
    img.save(out_path, "PNG")


def create_sample_wav(out_path: Path, duration_sec: float = 3.5, freq: float = 240.0) -> None:
    """Generate a clean, modulated 16kHz mono 16-bit PCM WAV audio note."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration_sec)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)

        # Modulate frequency to mimic natural human speech cadence (formant-like rise/fall)
        frames = bytearray()
        for i in range(num_samples):
            t = float(i) / sample_rate
            # Cadence envelope
            envelope = math.sin(math.pi * t / duration_sec) ** 0.5
            pitch = freq + 25.0 * math.sin(2.0 * math.pi * 3.5 * t)
            sample_val = int(envelope * 8000.0 * math.sin(2.0 * math.pi * pitch * t))
            frames.extend(struct.pack("<h", max(-32768, min(32767, sample_val))))

        wf.writeframes(frames)


def generate_all_samples() -> dict[str, Any]:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Document Images
    create_aadhaar_sample(SAMPLES_DIR / "aadhaar_sample.png")
    create_land_record_sample(SAMPLES_DIR / "land_record_sample.png")
    create_land_record_sample(SAMPLES_DIR / "land_record_blurry.png", blurry=True)
    create_bank_passbook_sample(SAMPLES_DIR / "bank_passbook_sample.png")
    create_bank_passbook_sample(SAMPLES_DIR / "passbook_missing_ifsc.png", missing_ifsc=True)
    create_income_cert_sample(SAMPLES_DIR / "income_cert_sample.png")
    create_marksheet_sample(SAMPLES_DIR / "marksheet_sample.png")

    # 2. Audio Voice Notes
    create_sample_wav(SAMPLES_DIR / "voice_sample_ta.wav", duration_sec=3.5, freq=220.0)
    create_sample_wav(SAMPLES_DIR / "voice_sample_te.wav", duration_sec=3.5, freq=230.0)
    create_sample_wav(SAMPLES_DIR / "voice_sample_hi.wav", duration_sec=3.5, freq=210.0)
    create_sample_wav(SAMPLES_DIR / "voice_sample_en.wav", duration_sec=3.5, freq=200.0)
    create_sample_wav(SAMPLES_DIR / "voice_scholarship_en.wav", duration_sec=3.5, freq=240.0)

    # 3. Catalog Manifest
    manifest = {
        "synthetic_only": True,
        "watermark": WATERMARK_TEXT,
        "description": "Pre-staged sample pack for live Telegram & Web demo presentations.",
        "scenarios": {
            "Scenario_A": {
                "title": "PM-KISAN Auto-Submit (Tamil Voice + All Documents)",
                "voice": "voice_sample_ta.wav",
                "documents": ["aadhaar_sample.png", "land_record_sample.png", "bank_passbook_sample.png"],
                "expected_outcome": "AUTO_SUBMIT",
            },
            "Scenario_B": {
                "title": "PM-KISAN Missing Land Record (Re-entry flow)",
                "voice": "voice_sample_en.wav",
                "documents": ["aadhaar_sample.png", "bank_passbook_sample.png"],
                "expected_outcome": "NEEDS_DOCUMENTS",
            },
            "Scenario_C": {
                "title": "PM-KISAN Blurry Land Record (Reviewer Escalation)",
                "voice": "voice_sample_ta.wav",
                "documents": ["aadhaar_sample.png", "land_record_blurry.png", "bank_passbook_sample.png"],
                "expected_outcome": "NEEDS_REVIEW",
            },
            "Scenario_D1": {
                "title": "PM-KISAN Missing IFSC in primary OCR (Auto-Recovery)",
                "voice": "voice_sample_hi.wav",
                "documents": ["aadhaar_sample.png", "land_record_sample.png", "passbook_missing_ifsc.png"],
                "expected_outcome": "AUTO_RECOVERY_THEN_SUBMIT",
            },
            "Scenario_D2": {
                "title": "PM-KISAN Portal 500/Permanent Reject (Reviewer Escalation)",
                "voice": "voice_sample_te.wav",
                "documents": ["aadhaar_sample.png", "land_record_sample.png", "bank_passbook_sample.png"],
                "expected_outcome": "ESCALATED_TO_REVIEWER",
            },
            "Scenario_E": {
                "title": "PM-KISAN Missing Tax Declaration (Interactive Citizen Question)",
                "voice": "voice_sample_ta.wav",
                "documents": ["aadhaar_sample.png", "land_record_sample.png", "bank_passbook_sample.png"],
                "expected_outcome": "INTERACTIVE_QUESTION_THEN_SUBMIT",
            },
            "Scholarship": {
                "title": "Post-Matric Scholarship (Student)",
                "voice": "voice_scholarship_en.wav",
                "documents": ["aadhaar_sample.png", "income_cert_sample.png", "marksheet_sample.png"],
                "expected_outcome": "ELIGIBILITY_ASSESSED",
            },
        },
        "files": {
            "documents": [
                "aadhaar_sample.png",
                "land_record_sample.png",
                "land_record_blurry.png",
                "bank_passbook_sample.png",
                "passbook_missing_ifsc.png",
                "income_cert_sample.png",
                "marksheet_sample.png",
            ],
            "audio": [
                "voice_sample_ta.wav",
                "voice_sample_te.wav",
                "voice_sample_hi.wav",
                "voice_sample_en.wav",
                "voice_scholarship_en.wav",
            ],
        },
    }

    manifest_path = SAMPLES_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    readme_content = """# ADHIKAAR — Demo Sample Pack

This directory contains pre-staged, synthetic mock documents and audio voice notes for running the live hackathon pitch and judge demos.

> **CRITICAL PRIVACY RULE:** Every file here is 100% synthetic. Every document image is visibly stamped with `SAMPLE — NOT A REAL DOCUMENT`. No real PII or government credentials exist.

## How Presenters Use These Samples

### For Telegram Bot Demo (@adhikaar013bot):
1. Send `/start` on Telegram and accept the consent disclaimer.
2. Send one audio voice note (e.g. `voice_sample_ta.wav` for Tamil, or `voice_sample_hi.wav` for Hindi).
3. Send the document photos (`aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png`).
4. Click **Done** on Telegram to trigger autonomous multi-agent analysis.

### For Next.js Web Form Demo:
1. Open the web interface (`http://localhost:3000`).
2. Accept the consent checkbox.
3. Upload voice note and document image files.
4. Watch the real-time SSE audit timeline render each stage (`INPUT → UNDERSTAND → PLAN → USE TOOLS → ACT → VERIFY`).

## Scenario File Mapping

| Scenario | Voice File | Document Files | Expected Stage |
|---|---|---|---|
| **Scenario A** (Auto-Submit) | `voice_sample_ta.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png` | Automatic submission with portal ref `PMK-TN-...` |
| **Scenario B** (Missing Doc) | `voice_sample_en.wav` | `aadhaar_sample.png`, `bank_passbook_sample.png` | Pauses with `NEEDS_DOCUMENTS`; asks for land record |
| **Scenario C** (Human Review) | `voice_sample_ta.wav` | `aadhaar_sample.png`, `land_record_blurry.png`, `bank_passbook_sample.png` | Escalates to Reviewer queue with confidence < 0.85 |
| **Scenario D1** (Auto-Recovery) | `voice_sample_hi.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `passbook_missing_ifsc.png` | Auto-recovers missing IFSC via secondary pass |
| **Scenario D2** (Portal Failure) | `voice_sample_te.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png` | Mock portal rejection → Escalated with failure trace |
| **Scenario E** (Clarification) | `voice_sample_ta.wav` | `aadhaar_sample.png`, `land_record_sample.png`, `bank_passbook_sample.png` | Inline question: "Does anyone pay income tax?" |
| **Scholarship** | `voice_scholarship_en.wav` | `aadhaar_sample.png`, `income_cert_sample.png`, `marksheet_sample.png` | Assesses student entitlement |
"""
    (SAMPLES_DIR / "README.md").write_text(readme_content, encoding="utf-8")

    return manifest


if __name__ == "__main__":
    manifest = generate_all_samples()
    print(f"Generated {len(manifest['files']['documents'])} documents and {len(manifest['files']['audio'])} audio files in {SAMPLES_DIR}")
