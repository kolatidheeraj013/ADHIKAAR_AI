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

        # Comprehensive Indian profession & livelihood recognition across all trades
        if any(w in combined for w in (
            "farmer", "kisan", "cultivator", "agriculture", "agricultural", "crop",
            "landowner", "raitu", "vyavasayam", "vivasayi", "krishi", "khet", "kheti",
            "tenant farmer", "sharecropper", "rythu", "kisan bhai",
        )):
            info["occupation"] = "farmer"
        elif any(w in combined for w in (
            "vendor", "street vendor", "hawker", "cart", "thela", "footpath", "stall",
            "pushcart", "vegetable seller", "fruit seller", "sabziwala", "thelawala",
            "pheriwala", "petty vendor", "roadside seller", "chaiwala", "tea stall",
        )):
            info["occupation"] = "street vendor"
        elif any(w in combined for w in (
            "student", "college", "school", "scholarship", "study", "marksheet",
            "degree", "university", "matric", "post-matric", "pre-matric", "vidyarthi",
            "padhai", "education", "student pass", "polytechnic", "diploma",
        )):
            info["occupation"] = "student"
        elif any(w in combined for w in (
            "artisan", "weaver", "craftsman", "vishwakarma", "carpenter", "potter",
            "blacksmith", "goldsmith", "tailor", "cobbler", "barber", "handloom",
            "sculptor", "handicraft", "silversmith", "darji", "lohar", "sonar",
            "kumhar", "mochi", "badhai", "suthar", "bunker", "karigar", "bunkar",
            "toy maker", "basket weaver", "embroidery", "zardozi", "stone carver",
        )):
            info["occupation"] = "artisan"
        elif any(w in combined for w in (
            "construction", "building worker", "labour", "labourer", "mazdoor",
            "daily wage", "shramik", "bocw", "mason", "painter", "plumber",
            "electrician", "helper", "rajmistri", "beldar", "tile worker",
            "welder", "plasterer", "concrete", "cement", "scaffolding",
        )):
            info["occupation"] = "construction worker"
        elif any(w in combined for w in (
            "driver", "auto driver", "taxi driver", "transport", "cab", "truck driver",
            "rickshaw", "auto", "cab driver", "tempo", "vehicle driver", "conductor",
            "ola driver", "uber driver", "bus driver", "commercial driver", "chalak",
            "lorry driver", "van driver",
        )):
            info["occupation"] = "driver"
        elif any(w in combined for w in (
            "fisherman", "fisherwoman", "fisheries", "matsya", "fish", "boat", "coastal",
            "aquaculture", "fish farmer", "machuwara", "boatman", "navik", "sea worker",
            "prawn farmer", "meenavar", "machliwala",
        )):
            info["occupation"] = "fisherman"
        elif any(w in combined for w in (
            "sanitation", "safai", "safai karamchari", "domestic worker", "maid",
            "cleaner", "sweeper", "housemaid", "aaya", "bai", "caretaker",
            "rag picker", "waste picker", "kabadiwala", "scavenger", "garbage collector",
        )):
            info["occupation"] = "sanitation worker"
        elif any(w in combined for w in (
            "security guard", "guard", "watchman", "chowkidar", "security staff",
            "private security", "gunman", "chaukidar",
        )):
            info["occupation"] = "security guard"
        elif any(w in combined for w in (
            "gig worker", "delivery", "delivery boy", "delivery partner", "zomato",
            "swiggy", "dunzo", "zepto", "blinkit", "amazon delivery", "flipkart delivery",
            "courier", "rider", "platform worker",
        )):
            info["occupation"] = "gig worker"
        elif any(w in combined for w in (
            "factory worker", "manufacturing", "industrial worker", "plant worker",
            "textile worker", "garment worker", "loom worker", "beedi worker",
            "packaging worker", "mill worker", "powerloom",
        )):
            info["occupation"] = "factory worker"
        elif any(w in combined for w in (
            "business", "shopkeeper", "trader", "merchant", "entrepreneur",
            "micro enterprise", "dukaan", "shop", "kirana", "grocery", "store owner",
            "dukanwala", "vyapari", "commercial establishment", "hotel", "restaurant",
            "cook", "waiter", "chef", "dhaba", "canteen",
        )):
            info["occupation"] = "small business"
        elif any(w in combined for w in (
            "asha", "anganwadi", "nurse", "health worker", "midwife", "sevika",
            "compounder", "ward boy", "hospital staff", "arogya mitra", "dai",
        )):
            info["occupation"] = "health worker"
        elif any(w in combined for w in (
            "unemployed", "job seeker", "youth", "skill", "training", "fresher",
            "graduate", "berozgar", "rozgar", "job search", "kaushal", "vocational",
            "unemployed youth", "looking for job", "pass out",
        )):
            info["occupation"] = "unemployed youth"
        elif any(w in combined for w in (
            "washerman", "dhobi", "laundry", "ironing", "presswala",
        )):
            info["occupation"] = "artisan"
        elif any(w in combined for w in (
            "worker", "unorganized", "coolie", "porter", "loader", "hamali", "mathadi",
        )):
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

    def clean_stale_sessions(self) -> list[str]:
        """Safely prune all sessions older than ttl_seconds (30 minutes).

        Ensures inactive sessions are cleaned without affecting active users.
        """
        now = time.time()
        cleared_cids: list[str] = []
        for cid, turns in list(self._history.items()):
            valid = [t for t in turns if now - t.timestamp < self.ttl_seconds]
            if not valid:
                cleared_cids.append(cid)
                self._history.pop(cid, None)
            else:
                self._history[cid] = valid
        return cleared_cids
