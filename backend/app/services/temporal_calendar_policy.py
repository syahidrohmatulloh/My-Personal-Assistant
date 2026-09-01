"""M34 — deterministic temporal / Calendar semantic policy.

Core invariant:

    time mention != event != commitment != scheduling request

This module owns semantic gating only. It does not call an LLM, database,
embedding provider, Google Calendar, or any persistence API.

The policy is intentionally precision-first: ambiguous temporal language stays
in normal chat unless the user clearly expresses a committed personal event or
an explicit Calendar/reminder action.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


TEMPORAL_CALENDAR_POLICY_VERSION = "M34-v1"

TemporalReference = Literal[
    "none",
    "date",
    "time",
    "datetime",
    "range",
    "recurring",
]
CalendarSubject = Literal[
    "user",
    "other",
    "public",
    "unknown",
]
Eventhood = Literal[
    "none",
    "possible",
    "event",
]
Commitment = Literal[
    "none",
    "tentative",
    "committed",
    "cancelled",
]
SpeechAct = Literal[
    "inform",
    "ask",
    "plan",
    "commit",
    "create",
    "update",
    "delete",
    "confirm",
    "deny",
]
PersistenceTarget = Literal[
    "none",
    "reminder",
    "calendar",
]
CalendarRoute = Literal[
    "normal_chat",
    "clarify_eventhood",
    "calendar_candidate",
    "calendar_action",
]


@dataclass(frozen=True)
class CalendarSemanticAssessment:
    temporal_reference: TemporalReference
    subject: CalendarSubject
    eventhood: Eventhood
    commitment: Commitment
    speech_act: SpeechAct
    persistence_target: PersistenceTarget
    route: CalendarRoute
    temporal_confidence: float
    eventhood_confidence: float
    commitment_confidence: float
    action_confidence: float
    reason_codes: tuple[str, ...]


_DATE_TERMS = (
    "hari ini", "pagi ini", "siang ini", "sore ini", "malam ini",
    "nanti malam", "besok", "tomorrow", "lusa", "minggu depan",
    "next week", "senin", "selasa", "rabu", "kamis", "jumat",
    "jum'at", "sabtu", "minggu", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "januari", "februari",
    "maret", "april", "mei", "juni", "juli", "agustus", "september",
    "oktober", "november", "desember", "january", "february", "march",
    "may", "june", "july", "august", "october", "november", "december",
)

_ROUTINE_MARKERS = (
    "setiap ", "tiap ", "biasanya ", "rutin ", "rutinnya ",
    "setiap hari", "setiap minggu", "harian", "mingguan",
    "every ", "usually ", "daily", "weekly", "weekdays", "weekends",
)

_TENTATIVE_MARKERS = (
    "mungkin", "kayaknya", "sepertinya", "kemungkinan aku",
    "kemungkinan saya", "rencananya", "pengen", "pingin", "ingin coba",
    "mau coba", "kalau sempat", "kalau bisa", "if possible", "maybe",
    "perhaps", "probably", "possibly", "might ", "may ",
)

_EVENT_TERMS = (
    "meeting", "rapat", "meet ", "call", "zoom", "gmeet", "google meet",
    "ketemu", "diskusi", "briefing", "review", "deadline", "appointment",
    "janji", "agenda", "jadwal", "interview", "presentasi", "presentation",
    "sharing session", "session", "seminar", "workshop", "dokter", "klinik",
    "fisioterapi", "terapi", "flight", "penerbangan", "terbang", "gym",
    "golf", "dinner", "lunch", "makan malam", "makan siang", "nonton",
    "bioskop", "bowling",
)

_PUBLIC_TERMS = (
    "hujan", "cuaca", "banjir", "macet", "kemacetan", "demo",
    "demonstrasi", "unjuk rasa", "aksi massa", "razia", "kecelakaan",
    "konser", "launching", "peluncuran",
)

_PUBLIC_MARKERS = (
    "katanya", "kabarnya", "beritanya", "ada kabar", "rumornya",
    "isunya", "menurut berita", "denger", "dengar", "info ", "informasi ",
)

_FIRST_PERSON_RE = re.compile(
    r"\b(?:aku|saya|gue|gw|gua|kami|kita|i|we|my)\b",
    re.IGNORECASE,
)

_EXPLICIT_CALENDAR_PATTERNS = (
    "masukin ke kalender", "masukkan ke kalender", "tambahin ke kalender",
    "tambahkan ke kalender", "catat ke kalender", "masukin kalender",
    "masukkan kalender", "tambahin kalender", "tambahkan kalender",
    "catat kalender", "masukin ke calendar", "masukkan ke calendar",
    "tambahin ke calendar", "tambahkan ke calendar", "add to calendar",
    "put on calendar", "jadwalkan", "schedule ", "schedule this",
)

_REMINDER_PATTERNS = (
    "ingatkan aku", "ingetin aku", "ingatkan saya", "ingetin saya",
    "tolong ingatkan", "tolong ingetin", "remind me", "set reminder",
    "buat reminder", "bikin reminder", "kasih reminder",
)

_UPDATE_PATTERNS = (
    "ubah ", "ganti ", "pindah ", "pindahkan ", "reschedule", "update ",
)

_DELETE_PATTERNS = (
    "hapus ", "delete ", "batalkan ", "cancel ",
)

_CANCELLED_PATTERNS = (
    "batal", "dibatalkan", "nggak jadi", "ngga jadi", "ga jadi",
    "gak jadi", "tidak jadi", "cancelled", "canceled",
)

_CALENDAR_ABSENCE_EVENT_TERMS = (
    "meeting",
    "meet",
    "rapat",
    "agenda",
    "jadwal",
    "acara",
    "appointment",
    "janji",
    "call",
    "briefing",
    "interview",
    "presentasi",
    "presentation",
    "session",
    "seminar",
    "workshop",
    "deadline",
    "event",
)


_QUESTION_PATTERNS = (
    "kapan ", "kapan?", "jam berapa", "pukul berapa", "tanggal berapa",
    "what time", "when ", "when?",
)

_PENDING_EXACT_REPLIES = frozenset({
    "iya", "ya", "yes", "y", "oke", "ok", "sip", "siap", "boleh",
    "setuju", "batal", "jangan", "nggak", "ngga", "enggak", "ga", "gak",
    "tidak", "no", "nope", "google aja", "google saja", "local aja",
    "lokal aja", "masukin aja", "masukkan aja", "masukin saja",
    "masukkan saja", "boleh masukin", "boleh masukkan",
})

_PENDING_REFERENCE_MARKERS = (
    "yang tadi", "agenda tadi", "jadwal tadi", "calendar tadi",
    "kalender tadi", "yang sebelumnya", "agenda sebelumnya",
    "jadwal sebelumnya", "calendar sebelumnya", "kalender sebelumnya",
    "yang kemarin",
)

_PENDING_CALENDAR_TERMS = (
    "agenda", "jadwal", "calendar", "kalender", "reminder", "ingetin",
    "ingatkan", "masukin", "masukkan", "tambahin", "tambahkan", "sync",
)

_TIME_RE = re.compile(
    r"(?:\b(?:jam|pukul|at)\s*\d{1,2}(?:[.:]\d{2})?"
    r"(?:\s*(?:am|pm|pagi|siang|sore|malam))?\b)"
    r"|(?:\b\d{1,2}[.:]\d{2}\s*(?:am|pm|pagi|siang|sore|malam)?\b)",
    re.IGNORECASE,
)

_TIME_RANGE_RE = re.compile(
    r"\b(?:jam|pukul|at)?\s*\d{1,2}(?:[.:]\d{2})?\s*"
    r"(?:-|–|—|sampai|s/d|to)\s*"
    r"\d{1,2}(?:[.:]\d{2})?\b",
    re.IGNORECASE,
)

_NUMERIC_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2})\b"
)

_THIRD_PERSON_EVENT_RE = re.compile(
    r"\b(?:dia|mereka|he|she|they|pak\s+[a-z]+|bu\s+[a-z]+)"
    r"\s+(?:ada|punya|akan|mau|has|have|will)\s+"
    r"(?:meeting|rapat|call|agenda|jadwal|appointment|janji|interview)\b",
    re.IGNORECASE,
)


def _normalize(text: str | None) -> str:
    return " ".join(
        str(text or "").replace("\n", " ").casefold().split()
    )


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def _has_date(text: str) -> bool:
    return (
        _contains_any(text, _DATE_TERMS)
        or bool(_NUMERIC_DATE_RE.search(text))
        or bool(re.search(r"\b(?:tgl|tanggal)\s+\d{1,2}\b", text))
    )


def _has_time(text: str) -> bool:
    return bool(_TIME_RE.search(text))


def _temporal_reference(text: str) -> TemporalReference:
    if _contains_any(text, _ROUTINE_MARKERS):
        return "recurring"
    if _TIME_RANGE_RE.search(text):
        return "range"
    has_date = _has_date(text)
    has_time = _has_time(text)
    if has_date and has_time:
        return "datetime"
    if has_date:
        return "date"
    if has_time:
        return "time"
    return "none"


def _is_explicit_calendar_action(text: str) -> bool:
    if _contains_any(text, _EXPLICIT_CALENDAR_PATTERNS):
        return True

    return bool(
        re.search(
            r"\b(?:masukin|masukkan|tambahin|tambahkan|catat|add|put)\b"
            r"(?:\s+\S+){0,24}\s+"
            r"(?:ke\s+|to\s+)?(?:kalender|calendar)\b",
            text,
            re.IGNORECASE,
        )
    )


def _is_explicit_reminder_action(text: str) -> bool:
    return _contains_any(text, _REMINDER_PATTERNS)


def _is_calendar_absence_statement(
    text: str,
) -> bool:
    if not text:
        return False

    event_pattern = (
        "(?:"
        + "|".join(
            re.escape(term)
            for term in sorted(
                _CALENDAR_ABSENCE_EVENT_TERMS,
                key=len,
                reverse=True,
            )
        )
        + r")(?:s)?"
    )

    negation = (
        r"(?:"
        r"nggak|ngga|enggak|engga|"
        r"gak|ga|gk|"
        r"tidak|tdk|tak|belum"
        r")"
    )

    indonesian_patterns = (
        (
            rf"\b{negation}\s+"
            rf"(?:ada|punya|memiliki)\s+"
            rf"(?:(?:lagi|rencana|sebuah|suatu)\s+)?"
            rf"{event_pattern}\b"
        ),
        (
            rf"\b{negation}\s+"
            rf"(?:mau|akan|bakal|jadi)\s+"
            rf"{event_pattern}\b"
        ),
        (
            rf"\b(?:aku|saya|gue|gw|gua|kita|kami)\s+"
            rf"{negation}\s+"
            rf"(?:akan\s+|bakal\s+)?"
            rf"(?:punya\s+|memiliki\s+)?"
            rf"{event_pattern}\b"
        ),
        (
            rf"\b{event_pattern}\b"
            rf"(?:\s+\S+){{0,4}}\s+"
            rf"{negation}\s+"
            rf"(?:jadi|ada)\b"
        ),
        (
            rf"\b{event_pattern}\b"
            rf"(?:\s+\S+){{0,4}}\s+"
            rf"(?:batal|dibatalkan)\b"
        ),
        (
            rf"\b(?:batal|batalkan)\s+"
            rf"{event_pattern}\b"
        ),
        (
            r"\b(?:jadwal|agenda|kalender|calendar)\b"
            r"(?:\s+\S+){0,4}\s+"
            r"(?:kosong|empty|clear)\b"
        ),
    )

    if any(
        re.search(pattern, text)
        for pattern in indonesian_patterns
    ):
        return True

    english_patterns = (
        (
            rf"\bno\s+(?:more\s+)?"
            rf"{event_pattern}\b"
        ),
        (
            rf"\bthere(?:'s|\s+is|\s+are)\s+"
            rf"no\s+(?:more\s+)?"
            rf"{event_pattern}\b"
        ),
        (
            rf"\b(?:i|we)\s+"
            rf"(?:do\s+not|don't|dont)\s+"
            rf"have\s+"
            rf"(?:(?:a|an|any)\s+)?"
            rf"{event_pattern}\b"
        ),
        (
            rf"\b(?:i|we)\s+have\s+no\s+"
            rf"{event_pattern}\b"
        ),
        (
            rf"\b{event_pattern}\b"
            rf"(?:\s+\S+){{0,4}}\s+"
            rf"(?:is\s+)?"
            rf"(?:cancelled|canceled)\b"
        ),
    )

    return any(
        re.search(pattern, text)
        for pattern in english_patterns
    )


def _looks_like_question(text: str) -> bool:
    if _contains_any(text, _QUESTION_PATTERNS):
        return True
    if text.endswith("?") and any(
        term in text
        for term in (
            "agenda", "jadwal", "meeting", "rapat", "flight", "dinner",
            "calendar", "kalender",
        )
    ):
        return True
    return False


def _looks_like_self_regulation_reminder(
    text: str,
    temporal_reference: TemporalReference,
) -> bool:
    if temporal_reference != "none":
        return False
    conditional = any(
        marker in text
        for marker in (
            "kalau aku ", "kalau saya ", "ketika aku ", "ketika saya ",
            "saat aku ", "saat saya ", "when i ",
        )
    )
    return conditional and _is_explicit_reminder_action(text)


def _looks_public(text: str) -> bool:
    if _FIRST_PERSON_RE.search(text):
        return False
    has_public_term = _contains_any(text, _PUBLIC_TERMS)
    has_public_marker = _contains_any(text, _PUBLIC_MARKERS)
    if has_public_marker and has_public_term:
        return True
    if has_public_term and (_has_date(text) or _has_time(text)):
        return True
    return False


def _subject(text: str) -> CalendarSubject:
    if _FIRST_PERSON_RE.search(text):
        return "user"
    if _looks_public(text):
        return "public"
    if _THIRD_PERSON_EVENT_RE.search(text):
        return "other"
    return "unknown"


def _has_event_signal(text: str) -> bool:
    return _contains_any(text, _EVENT_TERMS)


def assess_calendar_semantics(
    user_message: str | None,
) -> CalendarSemanticAssessment:
    text = _normalize(user_message)

    if not text:
        return CalendarSemanticAssessment(
            temporal_reference="none",
            subject="unknown",
            eventhood="none",
            commitment="none",
            speech_act="inform",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.0,
            eventhood_confidence=0.0,
            commitment_confidence=0.0,
            action_confidence=0.0,
            reason_codes=("calendar.empty",),
        )

    temporal = _temporal_reference(text)
    subject = _subject(text)
    explicit_calendar = _is_explicit_calendar_action(text)
    explicit_reminder = _is_explicit_reminder_action(text)

    if _looks_like_self_regulation_reminder(text, temporal):
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject=subject,
            eventhood="none",
            commitment="none",
            speech_act="inform",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.0,
            eventhood_confidence=0.1,
            commitment_confidence=0.0,
            action_confidence=0.1,
            reason_codes=("calendar.self_regulation_not_schedule",),
        )

    if explicit_calendar or explicit_reminder:
        persistence_target: PersistenceTarget = (
            "reminder"
            if explicit_reminder and not explicit_calendar
            else "calendar"
        )
        speech_act: SpeechAct = "create"
        if _contains_any(text, _DELETE_PATTERNS):
            speech_act = "delete"
        elif _contains_any(text, _UPDATE_PATTERNS):
            speech_act = "update"
        event_signal = _has_event_signal(text)
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject="user" if subject == "unknown" else subject,
            eventhood="event" if event_signal else "possible",
            commitment="committed",
            speech_act=speech_act,
            persistence_target=persistence_target,
            route="calendar_action",
            temporal_confidence=0.98 if temporal != "none" else 0.25,
            eventhood_confidence=0.95 if event_signal else 0.55,
            commitment_confidence=0.95,
            action_confidence=1.0,
            reason_codes=("calendar.explicit_persistence_request",),
        )

    if _contains_any(text, _CANCELLED_PATTERNS):
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject=subject,
            eventhood="event" if _has_event_signal(text) else "possible",
            commitment="cancelled",
            speech_act="deny",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.95 if temporal != "none" else 0.2,
            eventhood_confidence=0.8,
            commitment_confidence=0.98,
            action_confidence=0.15,
            reason_codes=("calendar.cancelled_not_new_candidate",),
        )

    if _is_calendar_absence_statement(text):
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject=subject,
            eventhood="none",
            commitment="none",
            speech_act="deny",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=(
                0.95
                if temporal != "none"
                else 0.2
            ),
            eventhood_confidence=0.95,
            commitment_confidence=0.05,
            action_confidence=0.0,
            reason_codes=(
                "calendar.absence_statement_not_schedule",
            ),
        )

    if _looks_like_question(text):
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject=subject,
            eventhood="possible" if _has_event_signal(text) else "none",
            commitment="none",
            speech_act="ask",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.95 if temporal != "none" else 0.3,
            eventhood_confidence=0.55 if _has_event_signal(text) else 0.1,
            commitment_confidence=0.1,
            action_confidence=0.05,
            reason_codes=("calendar.temporal_question_not_schedule",),
        )

    if temporal == "recurring":
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject=subject,
            eventhood="possible" if _has_event_signal(text) else "none",
            commitment="none",
            speech_act="inform",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.95,
            eventhood_confidence=0.6 if _has_event_signal(text) else 0.2,
            commitment_confidence=0.2,
            action_confidence=0.05,
            reason_codes=("calendar.routine_routes_outside_calendar",),
        )

    if _looks_public(text):
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject="public",
            eventhood="possible",
            commitment="none",
            speech_act="inform",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.95 if temporal != "none" else 0.2,
            eventhood_confidence=0.65,
            commitment_confidence=0.05,
            action_confidence=0.02,
            reason_codes=("calendar.public_information_not_user_schedule",),
        )

    if subject == "other":
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject="other",
            eventhood="event" if _has_event_signal(text) else "possible",
            commitment="none",
            speech_act="inform",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.95 if temporal != "none" else 0.2,
            eventhood_confidence=0.75,
            commitment_confidence=0.05,
            action_confidence=0.02,
            reason_codes=("calendar.third_party_event_not_user_schedule",),
        )

    if _contains_any(text, _TENTATIVE_MARKERS):
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject=subject,
            eventhood="possible" if _has_event_signal(text) else "none",
            commitment="tentative",
            speech_act="plan",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.95 if temporal != "none" else 0.2,
            eventhood_confidence=0.6 if _has_event_signal(text) else 0.2,
            commitment_confidence=0.35,
            action_confidence=0.05,
            reason_codes=("calendar.tentative_plan_not_commitment",),
        )

    event_signal = _has_event_signal(text)

    if event_signal and temporal != "none":
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject="user" if subject == "unknown" else subject,
            eventhood="event",
            commitment="committed",
            speech_act="commit",
            persistence_target="none",
            route="calendar_candidate",
            temporal_confidence=0.95,
            eventhood_confidence=0.9,
            commitment_confidence=0.82,
            action_confidence=0.25,
            reason_codes=("calendar.committed_personal_event_candidate",),
        )

    if event_signal:
        return CalendarSemanticAssessment(
            temporal_reference=temporal,
            subject=subject,
            eventhood="possible",
            commitment="none",
            speech_act="inform",
            persistence_target="none",
            route="normal_chat",
            temporal_confidence=0.1,
            eventhood_confidence=0.6,
            commitment_confidence=0.2,
            action_confidence=0.05,
            reason_codes=("calendar.event_without_temporal_commitment",),
        )

    reason = (
        "calendar.temporal_information_not_event"
        if temporal != "none"
        else "calendar.no_calendar_semantics"
    )
    return CalendarSemanticAssessment(
        temporal_reference=temporal,
        subject=subject,
        eventhood="none",
        commitment="none",
        speech_act="inform",
        persistence_target="none",
        route="normal_chat",
        temporal_confidence=0.9 if temporal != "none" else 0.0,
        eventhood_confidence=0.1,
        commitment_confidence=0.05,
        action_confidence=0.01,
        reason_codes=(reason,),
    )


def requires_calendar_handling(
    assessment: CalendarSemanticAssessment,
) -> bool:
    return assessment.route in {
        "calendar_candidate",
        "calendar_action",
        "clarify_eventhood",
    }


def should_offer_calendar_candidate(
    assessment: CalendarSemanticAssessment,
) -> bool:
    return assessment.route == "calendar_candidate"


def allows_cross_conversation_pending_reference(
    user_message: str | None,
) -> bool:
    text = _normalize(user_message)
    if not text:
        return False
    has_reference = _contains_any(text, _PENDING_REFERENCE_MARKERS)
    has_calendar_term = _contains_any(text, _PENDING_CALENDAR_TERMS)
    return bool(has_reference and has_calendar_term)


def should_check_pending_confirmation(
    user_message: str | None,
) -> bool:
    text = _normalize(user_message)
    if not text:
        return False
    if text in _PENDING_EXACT_REPLIES:
        return True
    if allows_cross_conversation_pending_reference(text):
        return True
    if re.search(r"\byang\s+(?:nomor\s+)?\d+\b", text):
        return True

    short = len(text.split()) <= 7

    if short and any(
        phrase in text
        for phrase in (
            "masukin yang", "masukkan yang", "batal yang", "hapus yang",
            "yang ini aja", "yang ini saja", "google calendar aja",
            "ke google aja", "ke calendar aja", "ke kalender aja",
        )
    ):
        return True

    if short and (_has_time(text) or _has_date(text)) and any(
        marker in text
        for marker in ("aja", "saja", "jadi", "ubah", "ganti", "pindah")
    ):
        return True

    if short and re.search(r"\b(?:di|lokasi)\s+[a-z0-9]", text):
        return True

    return False


def should_surface_pending_context(
    user_message: str | None,
) -> bool:
    return should_check_pending_confirmation(user_message)
