"""Ephemeral language and consent state held until a backend case exists."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Language = Literal["ta", "te", "hi", "en"]


@dataclass
class OnboardingState:
    language: Language | None = None
    consent: bool = False


class OnboardingStore:
    def __init__(self) -> None:
        self._states: dict[str, OnboardingState] = {}

    def get(self, chat_id: int | str) -> OnboardingState:
        return self._states.setdefault(str(chat_id), OnboardingState())

    def set_language(self, chat_id: int | str, language: Language) -> OnboardingState:
        state = self.get(chat_id)
        state.language = language
        return state

    def set_consent(self, chat_id: int | str, consent: bool) -> OnboardingState:
        state = self.get(chat_id)
        state.consent = consent
        return state

    def clear(self, chat_id: int | str) -> None:
        self._states.pop(str(chat_id), None)

    def language_for(self, chat_id: int | str) -> Language:
        return self.get(chat_id).language or "en"
