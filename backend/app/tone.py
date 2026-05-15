from enum import Enum
import re
from typing import List


class RomanticLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EmotionalState(str, Enum):
    CALM = "calm"
    STRESSED = "stressed"
    AMBITIOUS = "ambitious"
    FATIGUED = "fatigued"


class AssistantMode(str, Enum):
    WORK = "work"
    LIFE = "life"
    RELATIONSHIP = "relationship"


# =========================
# SIGNALS
# =========================

HIGH_SIGNALS = [
    "i miss you",
    "i love you",
    "i need you",
    "thinking about you",
]

MEDIUM_SIGNALS = [
    "i like talking to you",
    "this feels nice",
    "you get me",
]

STRESS_SIGNALS = ["tired", "overwhelmed", "burnout", "stress"]
FATIGUE_SIGNALS = ["sleepy", "drained", "no energy"]
AMBITION_SIGNALS = ["build", "scale", "strategy", "optimize"]

WORK_SIGNALS = ["plan", "system", "business", "growth"]
RELATIONSHIP_SIGNALS = ["love", "miss you", "connection"]


# =========================
# DETECTORS
# =========================

def detect_romantic_tone(text: str) -> RomanticLevel:
    t = text.lower()

    for s in HIGH_SIGNALS:
        if s in t:
            return RomanticLevel.HIGH

    for s in MEDIUM_SIGNALS:
        if s in t:
            return RomanticLevel.MEDIUM

    if re.search(r"\b(miss you|thinking of you)\b", t):
        return RomanticLevel.MEDIUM

    return RomanticLevel.LOW


def detect_emotional_state(text: str) -> EmotionalState:
    t = text.lower()

    for s in STRESS_SIGNALS:
        if s in t:
            return EmotionalState.STRESSED

    for s in FATIGUE_SIGNALS:
        if s in t:
            return EmotionalState.FATIGUED

    for s in AMBITION_SIGNALS:
        if s in t:
            return EmotionalState.AMBITIOUS

    return EmotionalState.CALM


def detect_mode(text: str, emotion: str, romantic: str) -> AssistantMode:
    t = text.lower()

    if romantic == "high":
        return AssistantMode.RELATIONSHIP

    for s in RELATIONSHIP_SIGNALS:
        if s in t:
            return AssistantMode.RELATIONSHIP

    for s in WORK_SIGNALS:
        if s in t:
            return AssistantMode.WORK

    if emotion in ["stressed", "fatigued"]:
        return AssistantMode.LIFE

    return AssistantMode.LIFE


# =========================
# BASELINE (WEIGHTED)
# =========================

def compute_romantic_baseline(messages: List[str]) -> str:
    if not messages:
        return "low"

    score_map = {"low": 0, "medium": 1, "high": 2}

    total = 0
    weight_total = 0

    for i, msg in enumerate(reversed(messages)):
        lvl = detect_romantic_tone(msg).value
        score = score_map[lvl]

        weight = 1 + (i * 0.5)

        total += score * weight
        weight_total += weight

    avg = total / weight_total

    if avg >= 1.5:
        return "high"
    elif avg >= 0.5:
        return "medium"
    return "low"


# =========================
# MODE PERSISTENCE
# =========================

def resolve_mode(current: str, persisted: str | None) -> str:
    """
    Persist mode, but allow override if user strongly signals different mode
    """

    if not persisted:
        return current

    if current != persisted:
        return current  # override by user intent

    return persisted


def resolve_romantic_tone(current: str, baseline: str) -> str:
    levels = ["low", "medium", "high"]
    return levels[max(levels.index(current), levels.index(baseline))]
