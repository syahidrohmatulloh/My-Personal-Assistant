from typing import Dict, Any


def build_system_prompt(context: Dict[str, Any]) -> str:
    return f"""
You are a calm, intelligent, and adaptive AI assistant.

You adjust tone, behavior, and personality dynamically.

---

## Context
{context}
"""


# =========================
# INTERACTION CONTEXT
# =========================

def build_interaction_context(tone: str, baseline: str) -> str:
    return f"""
## Interaction Context
Romantic tone level: {tone}
Baseline tone: {baseline}
"""


def build_emotional_context(emotion: str) -> str:
    return f"""
## Emotional Context
User emotional state: {emotion}
"""


def build_mode_context(mode: str) -> str:
    return f"""
## Assistant Mode
Current mode: {mode}
"""


# =========================
# SHAPING
# =========================

def get_tone_instruction(level: str) -> str:
    if level == "low":
        return "Keep tone neutral and composed."
    if level == "medium":
        return "Allow slight warmth, remain restrained."
    if level == "high":
        return "Allow romantic tone but stay grounded."
    return ""


def get_emotional_instruction(emotion: str) -> str:
    if emotion == "stressed":
        return "Be calming and reduce complexity."
    if emotion == "fatigued":
        return "Keep responses short and simple."
    if emotion == "ambitious":
        return "Be sharp and strategic."
    return ""


def get_mode_instruction(mode: str) -> str:
    if mode == "work":
        return "Be structured and outcome-focused."
    if mode == "life":
        return "Be calm and conversational."
    if mode == "relationship":
        return "Be warm but not dependent."
    return ""

# =========================
# GREETING (TIME + ADAPTIVE)
# =========================

from datetime import datetime, timezone, timedelta


def get_wib_time_label() -> str:
    now_utc = datetime.now(timezone.utc)
    wib = now_utc + timedelta(hours=7)
    hour = wib.hour

    if 5 <= hour < 11:
        return "morning"
    elif 11 <= hour < 15:
        return "midday"
    elif 15 <= hour < 19:
        return "afternoon"
    elif 19 <= hour < 23:
        return "evening"
    return "night"


def build_greeting(name: str, tone: str, emotion: str, mode: str) -> str:
    time_label = get_wib_time_label()

    # WORK MODE
    if mode == "work":
        if time_label == "morning":
            return f"Selamat pagi, {name}. Ready to move things forward today?"
        if time_label == "evening":
            return f"Malam, {name}. Mau wrap up atau masih mau push?"
        return f"Hey {name}, what are we focusing on right now?"

    # STRESS / FATIGUE
    if emotion == "stressed":
        return f"Hey {name}, kelihatannya lagi banyak ya. Kita pelan-pelan aja."

    if emotion == "fatigued":
        return f"Hey {name}, kita keep it light aja ya."

    # HIGH ROMANTIC
    if tone == "high":
        if time_label == "night":
            return f"Masih bangun juga ya, {name}... gue di sini kok."
        return f"Hey {name}... good to see you again."

    # MEDIUM
    if tone == "medium":
        if time_label == "morning":
            return f"Selamat pagi, {name}. Semoga hari lo smooth."
        return f"Hey {name}, glad you're back."

    # DEFAULT
    if time_label == "morning":
        return f"Selamat pagi, {name}. Ada yang bisa gue bantu?"
    if time_label == "evening":
        return f"Malam, {name}. How can I help tonight?"

    return f"Hey {name}, what can I help you with?"
