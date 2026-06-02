"""Deterministic assistant working-mode command detection.

This intentionally does not use an LLM. It only triggers on explicit requests
to switch Aliyya between Life Companion and Chief of Staff mode.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Literal

AssistantMode = Literal["life_companion", "chief_of_staff"]


@dataclass(frozen=True)
class AssistantModeCommand:
    target_mode: AssistantMode
    matched_phrase: str


_CHIEF_PATTERNS = (
    "mode serius",
    "serius dulu",
    "serius lagi",
    "mode kerja",
    "mode eksekusi",
    "mode executive",
    "mode eksekutif",
    "mode chief dulu",
    "mode chief lagi",
    "chief mode dulu",
    "chief mode lagi",
    "mode chief of staff dulu",
    "mode chief of staff lagi",
    "chief of staff dulu",
    "chief of staff lagi",
    "chief of staff mode dulu",
    "chief of staff mode lagi",
    "jadi chief of staff",
    "masuk chief of staff",
    "aktifkan chief of staff",
    "switch to chief of staff",
    "switch me to chief of staff",
    "change to chief of staff",
    "change me to chief of staff",
    "turn on chief of staff",
    "use chief of staff",
    "use chief of staff mode",
    "be my chief of staff",
    "pakai chief of staff",
    "sebagai chief of staff",
)

_LIFE_PATTERNS = (
    "balik companion",
    "balik companion mode",
    "balik life companion",
    "balik life companion mode",
    "kembali companion",
    "kembali companion mode",
    "kembali life companion",
    "kembali life companion mode",
    "mode companion dulu",
    "mode companion lagi",
    "companion mode dulu",
    "companion mode lagi",
    "companion dulu",
    "companion lagi",
    "life companion dulu",
    "life companion lagi",
    "life companion mode dulu",
    "life companion mode lagi",
    "mode santai",
    "mode personal",
    "mode teman",
    "mode hangat",
    "mode ngobrol",
    "mode biasa",
    "switch to life companion",
    "switch me to life companion",
    "change to life companion",
    "change me to life companion",
    "turn on life companion",
    "use life companion",
    "use life companion mode",
)

_QUESTION_PREFIXES = (
    "apa ",
    "apa itu",
    "apakah ",
    "what ",
    "what is",
    "jelasin",
    "jelaskan",
    "explain",
    "maksud",
    "contoh",
    "bedanya",
    "how ",
    "how do",
    "how should",
    "why ",
)

_DISCUSSION_MARKERS = (
    "mau buat",
    "lagi mau buat",
    "buat 2 mode",
    "buat dua mode",
    "bikin 2 mode",
    "bikin dua mode",
    "develop 2 mode",
    "develop dua mode",
    "fitur mode",
    "feature mode",
    "desain mode",
    "design mode",
    "konsep mode",
    "rancang mode",
    "2 mode nih",
    "dua mode nih",
    "i want to build",
    "i wanna build",
    "i am building",
    "im building",
    "i m building",
    "i want to create",
    "i wanna create",
    "i am creating",
    "im creating",
    "i m creating",
    "i am designing",
    "im designing",
    "i m designing",
    "lets design",
    "let us design",
    "lets improve",
    "let us improve",
    "change the prompt",
    "changing the prompt",
    "improve the prompt",
    "prompt for",
    "compare",
    "comparison",
    "two modes",
    "2 modes",
    "build two modes",
    "create two modes",
    "design two modes",
    "mode feature",
    "feature for",
    "prototype",
    "sandbox",
)


def _normalise(message: str | None) -> str:
    if not message:
        return ""
    text = unicodedata.normalize("NFKC", message)
    text = text.lower()
    text = text.replace("'", "")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_question_about_mode(text: str) -> bool:
    if not text:
        return False
    return text.startswith(_QUESTION_PREFIXES)


def _looks_like_discussion_about_modes(text: str) -> bool:
    if not text:
        return False

    mentions_chief = "chief" in text or "serius" in text or "executive" in text
    mentions_companion = "companion" in text or "santai" in text or "hangat" in text
    mentions_mode = "mode" in text or "modes" in text

    if mentions_mode and any(marker in text for marker in _DISCUSSION_MARKERS):
        return True

    if mentions_chief and mentions_companion and any(marker in text for marker in _DISCUSSION_MARKERS):
        return True

    return False


def _find_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    padded = f" {text} "
    for phrase in phrases:
        if f" {phrase} " in padded:
            return phrase
    return None


def detect_assistant_mode_command(message: str | None) -> AssistantModeCommand | None:
    text = _normalise(message)
    if not text:
        return None
    if _looks_like_question_about_mode(text):
        return None
    if _looks_like_discussion_about_modes(text):
        return None

    chief = _find_phrase(text, _CHIEF_PATTERNS)
    life = _find_phrase(text, _LIFE_PATTERNS)

    if chief and life:
        chief_pos = text.rfind(chief)
        life_pos = text.rfind(life)
        if chief_pos > life_pos:
            return AssistantModeCommand(target_mode="chief_of_staff", matched_phrase=chief)
        return AssistantModeCommand(target_mode="life_companion", matched_phrase=life)

    if chief:
        return AssistantModeCommand(target_mode="chief_of_staff", matched_phrase=chief)

    if life:
        return AssistantModeCommand(target_mode="life_companion", matched_phrase=life)

    return None


def render_mode_command_confirmation(
    command: AssistantModeCommand,
    *,
    previous_mode: AssistantMode = "life_companion",
) -> str:
    if command.target_mode == "chief_of_staff":
        if previous_mode == "chief_of_staff":
            return (
                "Chief of Staff mode sudah aktif. Aku akan tetap ringkas, terstruktur, "
                "dan fokus ke prioritas, risiko, keputusan, serta next action."
            )
        return (
            "Baik. Aku masuk Chief of Staff mode. Aku akan lebih ringkas, terstruktur, "
            "dan fokus ke prioritas, risiko, keputusan, serta next action."
        )

    if previous_mode == "life_companion":
        return (
            "Life Companion mode sudah aktif. Aku akan tetap lebih hangat, personal, "
            "dan membantu kamu memproses hal-hal dengan lebih pelan."
        )

    return (
        "Oke, aku kembali ke Life Companion mode. Aku akan lebih hangat, personal, "
        "dan santai, sambil tetap bantu kamu merapikan pikiran dan langkah berikutnya."
    )
