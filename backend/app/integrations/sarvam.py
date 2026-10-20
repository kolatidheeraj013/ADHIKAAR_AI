"""Sarvam AI speech-to-text and translation client implementation."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.interfaces import SpeechClient

logger = logging.getLogger(__name__)

LANGUAGE_CODE_MAP = {
    "ta": "ta-IN",
    "te": "te-IN",
    "hi": "hi-IN",
    "en": "en-IN",
}


def map_language_code(language: str) -> str:
    """Map project language codes (ta, te, hi, en) to Sarvam language codes."""
    return LANGUAGE_CODE_MAP.get(language.lower(), "ta-IN")


def normalize_audio_with_ffmpeg(input_path: str | Path, output_path: str | Path) -> None:
    """Normalize input audio to 16 kHz mono WAV using ffmpeg if available."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        # If ffmpeg is not installed, copy if already wav, or warn
        if str(input_path).lower().endswith(".wav"):
            shutil.copyfile(input_path, output_path)
            return
        raise RuntimeError("ffmpeg is required for audio normalization but is not installed.")

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err_msg = result.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"ffmpeg conversion failed: {err_msg}")


def get_wav_duration_seconds(wav_path: str | Path) -> float:
    """Calculate duration of a WAV file in seconds using standard library wave module."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        # Fallback approximation for 16kHz 16-bit mono PCM (32000 bytes/sec)
        size = os.path.getsize(wav_path)
        return size / 32000.0


class SarvamSpeechClient(SpeechClient):
    """Real implementation of SpeechClient using Sarvam AI APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        max_voice_seconds: int | None = None,
        demo_mode: str | None = None,
        fixtures_path: Path | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.sarvam_api_key
        self.max_voice_seconds = max_voice_seconds or settings.max_voice_seconds
        self.demo_mode = (demo_mode or settings.demo_mode).lower()
        self.fixtures_path = fixtures_path or Path("data/fixtures/voice_transcripts.json")
        self._fixtures: dict[str, str] = {}
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        if self.fixtures_path.exists():
            try:
                with open(self.fixtures_path, "r", encoding="utf-8") as f:
                    self._fixtures = json.load(f)
            except Exception as e:
                logger.warning("Failed to load voice fixtures from %s: %s", self.fixtures_path, e)

    def transcribe(self, voice_path: str, language: str) -> str:
        """Transcribe and translate voice audio to English text.

        Rejects audio longer than max_voice_seconds. Normalizes to 16kHz mono WAV.
        """
        path = Path(voice_path)
        filename = path.name

        # 1. Offline replay or fallback
        if self.demo_mode == "offline" or not self.api_key:
            if filename in self._fixtures:
                return self._fixtures[filename]
            # Match partial key
            for key, val in self._fixtures.items():
                if key in filename or filename in key:
                    return val
            return "I am a farmer, I want PM-Kisan, nobody in my family pays income tax."

        if not path.exists():
            raise FileNotFoundError(f"Voice file not found: {voice_path}")

        # 2. Normalize with ffmpeg and check duration
        sarvam_lang = map_language_code(language)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            tmp_wav_path = Path(tmp_wav.name)

        try:
            normalize_audio_with_ffmpeg(path, tmp_wav_path)
            duration = get_wav_duration_seconds(tmp_wav_path)
            if duration > self.max_voice_seconds:
                raise ValueError(
                    f"Audio duration ({duration:.1f}s) exceeds maximum allowed limit "
                    f"of {self.max_voice_seconds}s."
                )

            # 3. Call Sarvam speech-to-text-translate API
            url = "https://api.sarvam.ai/speech-to-text-translate"
            headers = {"api-subscription-key": self.api_key}

            with open(tmp_wav_path, "rb") as audio_file:
                files = {"file": (tmp_wav_path.name, audio_file, "audio/wav")}
                data = {"model": "saaras:v2", "language_code": sarvam_lang}
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(url, headers=headers, data=data, files=files)
                    response.raise_for_status()
                    payload = response.json()
                    transcript = payload.get("transcript", "")
                    return transcript.strip()

        finally:
            if tmp_wav_path.exists():
                tmp_wav_path.unlink(missing_ok=True)

    def translate(self, text: str, target_language: str) -> str:
        """Translate English explanation text to the citizen's target language."""
        if not text:
            return ""

        target_code = map_language_code(target_language)
        if target_code == "en-IN":
            return text

        if self.demo_mode == "offline" or not self.api_key:
            return text

        url = "https://api.sarvam.ai/translate"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "input": text,
            "source_language_code": "en-IN",
            "target_language_code": target_code,
            "speaker_gender": "Female",
            "mode": "formal",
        }
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            res_data = response.json()
            return str(res_data.get("translated_text", text)).strip()
