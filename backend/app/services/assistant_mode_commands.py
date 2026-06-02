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
    "mode kerja",
    "mode eksekusi",
    "mode executive",
    "mode eksekutif",
    "mode chief",
    "chief of staff mode",
    "mode chief of staff",
    "jadi chief of staff",
    "masuk chief of staff",
    "aktifkan chief of staff",
    "switch to chief of staff",
    "change to chief of staff",
    "turn on chief of staff",
    "be my chief of staff",
    "pakai chief of staff",
    "sebagai chief of staff",
)

_LIFE_PATTERNS = (
    "life companion mode",
    "mode life companion",
    "companion mode",
    "mode companion",
    "balik companion",
    "balik life companion",
    "kembali companion",
    "kembali life companion",
    "mode santai",
    "mode personal",
    "mode teman",
    "mode hangat",
    "mode ngobrol",
    "mode biasa",
    "switch to life companion",
    "change to life companion",
    "turn on life companion",
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
)


def _normalise(message: str | None) -> str:
    if not message:
        return ""
    text = unicodedata.normalize("NFKC", message)
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_question_about_mode(text: str) -> bool:
    if not text:
        return False
    return text.startswith(_QUESTION_PREFIXES)


def _find_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    padded = f" {text} "
    for phrase in phrases:
        if f" {phrase} " in padded:
            return phrase
    return None


def detect_assistant_mode_command(message: str | None) -> AssistantModeCommand | None:
    """Return a mode command only for explicit switch requests.

    It intentionally ignores explanatory questions like:
    "apa itu chief of staff mode?" or "jelaskan companion mode".
    """
    text = _normalise(message)
    if not text or _looks_like_question_about_mode(text):
        return None

    chief = _find_phrase(text, _CHIEF_PATTERNS)
    life = _find_phrase(text, _LIFE_PATTERNS)

    # If both appear, prefer the phrase that appears later because users often say:
    # "bukan companion, mode chief of staff dulu".
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
    """Short deterministic confirmation. No affectionate nicknames."""
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
