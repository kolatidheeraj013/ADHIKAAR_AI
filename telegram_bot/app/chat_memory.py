"""Temporary conversational memory for citizens in Telegram.

Provides rolling context retention across conversational turns so citizens
can refer to previously stated personal facts (e.g. occupation, land size, state, income)
without repeating them.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


@dataclass
class ChatTurn:
    role: str  # "user" or "bot"
    text: str
    timestamp: float = field(default_factory=time.time)


class ChatMemory:
    """Rolling in-memory chat context per citizen chat_id."""

    def __init__(self, max_turns: int = 10, ttl_seconds: float = 1800.0) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self._history: dict[str, list[ChatTurn]] = {}

    def add_message(self, chat_id: int | str, role: str, text: str) -> None:
        cid = str(chat_id)
        now = time.time()
        turns = self._history.setdefault(cid, [])
        # Prune expired turns
        turns = [t for t in turns if now - t.timestamp < self.ttl_seconds]
        turns.append(ChatTurn(role=role, text=text.strip(), timestamp=now))
        if len(turns) > self.max_turns:
            turns = turns[-self.max_turns:]
        self._history[cid] = turns

    def get_history(self, chat_id: int | str) -> list[ChatTurn]:
        cid = str(chat_id)
        now = time.time()
        turns = self._history.get(cid, [])
        valid = [t for t in turns if now - t.timestamp < self.ttl_seconds]
        self._history[cid] = valid
        return list(valid)

    def get_context_text(self, chat_id: int | str, max_turns: int = 6) -> str:
        turns = self.get_history(chat_id)[-max_turns:]
        if not turns:
            return ""
        lines = []
        for t in turns:
            prefix = "Citizen: " if t.role == "user" else "Bot: "
            lines.append(f"{prefix}{t.text}")
        return "\n".join(lines)

    def extract_personal_info(self, chat_id: int | str) -> dict[str, str]:
        """Extract personal attributes mentioned by user in recent memory."""
        turns = [t for t in self.get_history(chat_id) if t.role == "user"]
        combined = " ".join(t.text.lower() for t in turns)
        info: dict[str, str] = {}

        # Occupation
        farmer_words = ("farmer", "kisan", "cultivator", "agriculture", "raitu")
        student_words = (
            "student", "college", "school", "scholarship", "study", "marksheet"
        )
        vendor_words = ("vendor", "street", "cart", "shopkeeper", "hawker")
        worker_words = (
            "worker", "labour", "daily wage", "unorganized", "carpenter", "mason"
        )

        if any(w in combined for w in farmer_words):
            info["occupation"] = "farmer"
        elif any(w in combined for w in student_words):
            info["occupation"] = "student"
        elif any(w in combined for w in vendor_words):
            info["occupation"] = "street vendor"
        elif any(w in combined for w in worker_words):
            info["occupation"] = "worker"

        # Demographics
        if any(w in combined for w in ("widow", "mahila", "woman", "women", "girl")):
            info["gender"] = "female"
        senior_words = ("pension", "senior", "elderly", "old age", "above 60", "aged 60")
        if any(w in combined for w in senior_words):
            info["age_group"] = "senior"
        if any(w in combined for w in ("disabled", "handicap", "divyang", "disability", "pwd")):
            info["special_category"] = "disabled"

        # Land
        land_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:acre|acres|bigha|hectare|cents)", combined)
        if land_match:
            info["land_size"] = f"{land_match.group(1)} acres"
        elif any(w in combined for w in ("land", "patta", "ror", "khasra", "chitta")):
            info["land_record"] = "landowner"

        # Income
        low_inc_words = (
            "bpl", "ration card", "poor", "low income", "below poverty", "poverty line"
        )
        if any(w in combined for w in low_inc_words):
            info["economic_status"] = "BPL / Low Income"

        # State
        for st in (
            "tamil nadu", "andhra pradesh", "telangana", "uttar pradesh",
            "karnataka", "maharashtra", "rajasthan", "bihar", "punjab",
            "madhya pradesh", "odisha", "kerala", "gujarat", "haryana",
        ):
            if st in combined:
                info["state"] = st.title()
                break

        return info

    def clear(self, chat_id: int | str) -> None:
        self._history.pop(str(chat_id), None)
