"""Phase 4 unit tests for real speech, OCR, and LLM integrations.

Strict zero-network invariant: All HTTP requests and heavy ML engines are mocked
or run in offline fixture-replay mode.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.agents.graph import _grounded
from app.integrations.llm import ProviderLLMClient, mask_identifiers
from app.integrations.ocr import PaddleOCRClient
from app.integrations.sarvam import (
    SarvamSpeechClient,
    get_wav_duration_seconds,
    map_language_code,
)


def _make_dummy_wav(path: Path, duration_seconds: float, sample_rate: int = 16000) -> Path:
    """Create a minimal valid PCM WAV file for duration and audio testing."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(duration_seconds * sample_rate)
        wf.writeframes(b"\x00\x00" * num_frames)
    return path


# -----------------------------------------------------------------------------
# Sarvam AI Speech Client Tests
# -----------------------------------------------------------------------------


def test_sarvam_language_code_mapping():
    """Verify project language codes map to Sarvam-supported codes."""
    assert map_language_code("ta") == "ta-IN"
    assert map_language_code("te") == "te-IN"
    assert map_language_code("hi") == "hi-IN"
    assert map_language_code("en") == "en-IN"
    assert map_language_code("UNKNOWN") == "ta-IN"


def test_sarvam_wav_duration_calculation(tmp_path: Path):
    """Verify standard library wave duration calculation."""
    wav_file = _make_dummy_wav(tmp_path / "test_2s.wav", duration_seconds=2.0)
    duration = get_wav_duration_seconds(wav_file)
    assert abs(duration - 2.0) < 0.05


def test_sarvam_duration_limit_exceeded(tmp_path: Path):
    """Verify audio longer than max_voice_seconds is rejected with ValueError."""
    long_wav = _make_dummy_wav(tmp_path / "long.wav", duration_seconds=35.0)
    client = SarvamSpeechClient(api_key="mock-key", max_voice_seconds=30, demo_mode="live")

    with pytest.raises(ValueError, match="exceeds maximum allowed limit of 30s"):
        client.transcribe(str(long_wav), language="ta")


def test_sarvam_transcribe_mocked_http(tmp_path: Path):
    """Verify live transcribe calls Sarvam STT API with correct parameters."""
    valid_wav = _make_dummy_wav(tmp_path / "valid.wav", duration_seconds=3.0)
    client = SarvamSpeechClient(api_key="mock-key", max_voice_seconds=30, demo_mode="live")

    expected_transcript = "I am a farmer and I want PM-Kisan scheme."

    def fake_post(url, *args, **kwargs):
        assert "speech-to-text-translate" in url
        assert kwargs["headers"]["api-subscription-key"] == "mock-key"
        assert kwargs["data"]["language_code"] == "ta-IN"
        return httpx.Response(
            200,
            json={"transcript": expected_transcript},
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.Client, "post", side_effect=fake_post):
        transcript = client.transcribe(str(valid_wav), language="ta")
        assert transcript == expected_transcript


def test_sarvam_transcribe_offline_fixture_replay():
    """Verify offline mode returns recorded transcript without audio file or network."""
    fixtures_file = Path("data/fixtures/voice_transcripts.json")
    client = SarvamSpeechClient(
        api_key=None,
        demo_mode="offline",
        fixtures_path=fixtures_file,
    )

    transcript = client.transcribe("scenario_a_voice.ogg", language="ta")
    assert "PM-Kisan" in transcript
    assert "income tax" in transcript


def test_sarvam_translate_mocked_http():
    """Verify translate calls Sarvam translate API."""
    client = SarvamSpeechClient(api_key="mock-key", demo_mode="live")

    def fake_post(url, *args, **kwargs):
        assert "translate" in url
        assert kwargs["headers"]["api-subscription-key"] == "mock-key"
        assert kwargs["json"]["target_language_code"] == "ta-IN"
        return httpx.Response(
            200,
            json={"translated_text": "வணக்கம் உங்கள் மனு ஏற்கப்பட்டது"},
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.Client, "post", side_effect=fake_post):
        translated = client.translate("Hello, your application is accepted", "ta")
        assert "வணக்கம்" in translated


def test_sarvam_translate_offline_fallback():
    """Verify translate in offline mode returns source English text cleanly."""
    client = SarvamSpeechClient(api_key=None, demo_mode="offline")
    text = "Application eligible"
    assert client.translate(text, "ta") == text
    assert client.translate(text, "en") == text


# -----------------------------------------------------------------------------
# PaddleOCR Client Tests
# -----------------------------------------------------------------------------


def test_paddleocr_offline_fixture_replay():
    """Verify OCR returns pre-recorded text and confidence from fixtures."""
    fixtures_file = Path("data/fixtures/ocr_results.json")
    client = PaddleOCRClient(demo_mode="offline", fixtures_path=fixtures_file)

    result = client.ocr("aadhaar_murugan.jpg")
    assert "Murugan K" in result["text"]
    assert "8942" in result["text"]
    assert result["confidence"] >= 0.90


def test_paddleocr_missing_file_raises_in_live_mode(tmp_path: Path):
    """Verify non-existent file in live mode raises FileNotFoundError."""
    client = PaddleOCRClient(demo_mode="live", fixtures_path=Path("non_existent_fixture.json"))
    with pytest.raises(FileNotFoundError):
        client.ocr(str(tmp_path / "ghost_doc.png"))


def test_paddleocr_with_mocked_engine(tmp_path: Path):
    """Verify live OCR extraction parsing and confidence averaging."""
    dummy_img = tmp_path / "real_doc.png"
    dummy_img.write_bytes(b"dummy image bytes")

    client = PaddleOCRClient(demo_mode="live")

    mock_engine = MagicMock()
    mock_engine.ocr.return_value = [
        [
            [[[0, 0], [10, 10]], ("GOVERNMENT OF INDIA", 0.96)],
            [[[0, 20], [10, 30]], ("Name: Murugan K", 0.94)],
        ]
    ]
    client._engine = mock_engine
    client._engine_attempted = True

    result = client.ocr(str(dummy_img))
    assert "GOVERNMENT OF INDIA" in result["text"]
    assert "Murugan K" in result["text"]
    assert result["confidence"] == 0.95


# -----------------------------------------------------------------------------
# Provider LLM Client Tests
# -----------------------------------------------------------------------------


def test_llm_mask_identifiers():
    """Verify 12-digit Aadhaar and account numbers are masked to last 4 digits."""
    raw = "Citizen Aadhaar 1234 5678 9012 and account 9876-5432-1098."
    masked = mask_identifiers(raw)
    assert "1234 5678 9012" not in masked
    assert "XXXX-XXXX-9012" in masked
    assert "XXXX-XXXX-1098" in masked


def test_llm_extract_facts_mocked_http():
    """Verify live fact extraction parses JSON and filters strictly to requested keys."""
    client = ProviderLLMClient(api_key="mock-key", demo_mode="live")

    mock_llm_payload = {
        "applicant_name": "Murugan K",
        "aadhaar_last4": "8942",
        "land_owned_hectares": 1.4,
        "is_income_tax_payer": False,
        "unrelated_hallucination": "random_data",
    }

    def fake_post(url, *args, **kwargs):
        assert "chat/completions" in url
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(mock_llm_payload),
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.Client, "post", side_effect=fake_post):
        facts = client.extract_facts(
            text="Name: Murugan K, Aadhaar XXXX-XXXX-8942",
            source_type="document",
            source_doc_id="doc1",
            target_keys=["applicant_name", "aadhaar_last4", "land_owned_hectares"],
        )
        assert facts == {
            "applicant_name": "Murugan K",
            "aadhaar_last4": "8942",
            "land_owned_hectares": 1.4,
        }
        assert "unrelated_hallucination" not in facts


def test_llm_local_endpoint_can_run_without_api_key():
    """LM Studio-style endpoints are live when configured without a secret."""
    client = ProviderLLMClient(
        api_key="",
        model="dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF",
        base_url="http://127.0.0.1:1234/v1",
        demo_mode="live",
    )

    def fake_post(url, *args, **kwargs):
        assert url == "http://127.0.0.1:1234/v1/chat/completions"
        assert kwargs["json"]["model"] == "dheeraj013/adhikaar-llama3.1-8b-fact-extractor-GGUF"
        assert "Authorization" not in kwargs["headers"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"applicant_name": "Local Model"}'}}]},
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.Client, "post", side_effect=fake_post):
        facts = client.extract_facts(
            text="Name: Local Model",
            source_type="document",
            source_doc_id="doc1",
            target_keys=["applicant_name"],
        )

    assert facts == {"applicant_name": "Local Model"}


def test_llm_extract_facts_json_retry():
    """Verify client retries on malformed JSON on first attempt and succeeds on second."""
    client = ProviderLLMClient(api_key="mock-key", demo_mode="live")

    attempts = 0

    def fake_post(url, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            content = "{ invalid json content..."
        else:
            content = json.dumps({"applicant_name": "Murugan K"})

        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.Client, "post", side_effect=fake_post):
        facts = client.extract_facts(
            text="Murugan K",
            source_type="document",
            source_doc_id="doc1",
            target_keys=["applicant_name"],
        )
        assert facts == {"applicant_name": "Murugan K"}
        assert attempts == 2


def test_llm_targeted_field_reextraction():
    """Verify extract_field single-field recovery for Scenario D1."""
    client = ProviderLLMClient(api_key="mock-key", demo_mode="live")

    def fake_post(url, *args, **kwargs):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"bank_ifsc": "SBIN0004128"}),
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    with patch.object(httpx.Client, "post", side_effect=fake_post):
        ifsc = client.extract_field(
            text="Branch Thanjavur IFSC: SBIN0004128",
            field="bank_ifsc",
            source_doc_id="passbook1",
        )
        assert ifsc == "SBIN0004128"


def test_llm_explain_and_pii_safety():
    """Verify explanation generation aligns with outcome and masks raw citizen identifiers."""
    client = ProviderLLMClient(demo_mode="offline")

    trace = [
        {"rule_id": "land_threshold", "passed": True},
        {
            "rule_id": "tax_exclusion",
            "passed": False,
            "fail_reason": "taxpayer 123456789012 excluded",
        },
    ]

    # NOT_ELIGIBLE explanation
    explanation = client.explain(
        outcome="NOT_ELIGIBLE",
        trace=trace,
        language="en",
    )
    assert "not eligible" in explanation.lower()
    assert "123456789012" not in explanation
    assert "XXXX-XXXX-9012" in explanation

    # ELIGIBLE explanation
    eligible_exp = client.explain(
        outcome="ELIGIBLE",
        trace=[{"rule_id": "land_threshold", "passed": True}],
        language="en",
    )
    assert "eligible" in eligible_exp.lower()


def test_llm_offline_fixture_replay():
    """Verify offline extraction extracts facts from fixtures and heuristics without API key."""
    client = ProviderLLMClient(api_key=None, demo_mode="offline")

    text = "I am a farmer, I want PM-Kisan, nobody in my family pays income tax."
    facts = client.extract_facts(
        text=text,
        source_type="declaration",
        source_doc_id=None,
        target_keys=["is_income_tax_payer"],
    )
    assert facts.get("is_income_tax_payer") is False


# -----------------------------------------------------------------------------
# Grounding Check Logic Tests
# -----------------------------------------------------------------------------


def test_grounding_verification_logic():
    """Verify anti-hallucination grounding check matches text, handles whitespace and digits."""
    ocr_text = (
        "GOVERNMENT OF TAMIL NADU\n"
        "Name: Murugan K\n"
        "Total Extent: 1.40 Hectares\n"
        "Bank A/C: 31094819201\n"
        "Aadhaar: XXXX-XXXX-8942"
    )

    # Exact and case/space-insensitive match
    assert _grounded("Murugan K", ocr_text) is True
    assert _grounded("murugan k", ocr_text) is True

    # Numeric / decimal match
    assert _grounded(1.40, ocr_text) is True
    assert _grounded("31094819201", ocr_text) is True
    assert _grounded("8942", ocr_text) is True

    # Ungrounded hallucinations
    assert _grounded("John Doe", ocr_text) is False
    assert _grounded(5.50, ocr_text) is False
    assert _grounded("9999999999", ocr_text) is False
