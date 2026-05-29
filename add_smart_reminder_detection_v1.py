from pathlib import Path
import shutil

EXTRACTOR = Path("backend/app/services/calendar_candidate_extractor.py")
CONFIRM = Path("backend/app/services/calendar_confirmation_actions.py")

for path in (EXTRACTOR, CONFIRM):
    backup = path.with_name(path.name + ".before-smart-reminders-v1")
    if not backup.exists():
        shutil.copy2(path, backup)

extractor = EXTRACTOR.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1) Add reminder keywords.
# ---------------------------------------------------------------------------
if "_REMINDER_KEYWORDS" not in extractor:
    marker = '''_EXPLICIT_CALENDAR_COMMANDS = (
    "masukin ke kalender",
'''
    insert = '''_REMINDER_KEYWORDS = (
    "ingatkan aku",
    "ingetin aku",
    "tolong ingatkan",
    "tolong ingetin",
    "remind me",
    "reminder",
    "set reminder",
    "buat reminder",
    "bikin reminder",
    "kasih reminder",
    "jangan lupa ingatkan",
)

'''
    if marker not in extractor:
        raise SystemExit("calendar command marker not found")
    extractor = extractor.replace(marker, insert + marker, 1)

# ---------------------------------------------------------------------------
# 2) Treat reminder keywords + date/time as calendar signal.
# ---------------------------------------------------------------------------
old_has_signal = '''    has_explicit_calendar_command = any(
        command in normalized for command in _EXPLICIT_CALENDAR_COMMANDS
    )

    # Explicit calendar command + date/time is enough, even when the event noun is unusual.
    if has_explicit_calendar_command and (has_date_signal or has_time_signal):
        return True
'''

new_has_signal = '''    has_explicit_calendar_command = any(
        command in normalized for command in _EXPLICIT_CALENDAR_COMMANDS
    )
    has_reminder_keyword = any(keyword in normalized for keyword in _REMINDER_KEYWORDS)

    # Reminder language + date/time is enough, even without a meeting/event noun.
    if has_reminder_keyword and (has_date_signal or has_time_signal):
        return True

    # Explicit calendar command + date/time is enough, even when the event noun is unusual.
    if has_explicit_calendar_command and (has_date_signal or has_time_signal):
        return True
'''

if old_has_signal not in extractor:
    raise SystemExit("has_calendar_signal command block not found")
extractor = extractor.replace(old_has_signal, new_has_signal, 1)

# ---------------------------------------------------------------------------
# 3) should_attempt also reacts to reminder command.
# ---------------------------------------------------------------------------
old_attempt = '''    if any(command in normalized for command in _EXPLICIT_CALENDAR_COMMANDS):
        return True
'''

new_attempt = '''    if any(command in normalized for command in _EXPLICIT_CALENDAR_COMMANDS):
        return True

    if any(keyword in normalized for keyword in _REMINDER_KEYWORDS):
        return True
'''

if old_attempt not in extractor:
    raise SystemExit("should_attempt calendar command block not found")
extractor = extractor.replace(old_attempt, new_attempt, 1)

# ---------------------------------------------------------------------------
# 4) Add helper functions before extract_candidate.
# ---------------------------------------------------------------------------
marker = '''def extract_candidate(
    *,
    text: str,
'''

helpers = '''def _is_reminder_request(normalized: str) -> bool:
    return any(keyword in normalized for keyword in _REMINDER_KEYWORDS)


def _clean_reminder_title(text: str) -> str:
    title = _build_title(text).strip()

    cleanup_patterns = [
        r"^(tolong\\s+)?ingatkan\\s+aku\\s+(untuk\\s+)?",
        r"^(tolong\\s+)?ingetin\\s+aku\\s+(untuk\\s+)?",
        r"^remind\\s+me\\s+(to\\s+)?",
        r"^set\\s+reminder\\s+(to\\s+)?",
        r"^buat\\s+reminder\\s+(untuk\\s+)?",
        r"^bikin\\s+reminder\\s+(untuk\\s+)?",
        r"^kasih\\s+reminder\\s+(untuk\\s+)?",
    ]

    cleaned = title
    for pattern in cleanup_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned[:120] or title[:120] or "Reminder"


'''

if "_is_reminder_request" not in extractor:
    if marker not in extractor:
        raise SystemExit("extract_candidate marker not found")
    extractor = extractor.replace(marker, helpers + marker, 1)

# ---------------------------------------------------------------------------
# 5) Use reminder title/content when extracting.
# ---------------------------------------------------------------------------
old_title = '''    title = _build_title(text)
    event_date_iso = event_date.isoformat()
'''

new_title = '''    is_reminder = _is_reminder_request(normalized)
    title = _clean_reminder_title(text) if is_reminder else _build_title(text)
    event_date_iso = event_date.isoformat()
'''

if old_title not in extractor:
    raise SystemExit("title build block not found")
extractor = extractor.replace(old_title, new_title, 1)

old_return = '''        content=f"User has a scheduled event: {title} on {event_date_iso}",
        evidence=[text[:220]],
        confidence=0.86 if local_time else 0.78,
        reason="deterministic_calendar_candidate",
'''

new_return = '''        content=(
            f"User wants a reminder: {title} on {event_date_iso}"
            if is_reminder
            else f"User has a scheduled event: {title} on {event_date_iso}"
        ),
        evidence=[text[:220]],
        confidence=0.9 if is_reminder and local_time else 0.86 if local_time else 0.78,
        reason="deterministic_reminder_candidate" if is_reminder else "deterministic_calendar_candidate",
'''

if old_return not in extractor:
    raise SystemExit("candidate return content block not found")
extractor = extractor.replace(old_return, new_return, 1)

for required in [
    "_REMINDER_KEYWORDS",
    "_is_reminder_request",
    "_clean_reminder_title",
    "User wants a reminder",
    "deterministic_reminder_candidate",
]:
    if required not in extractor:
        raise SystemExit(f"extractor missing {required}")

EXTRACTOR.write_text(extractor, encoding="utf-8")


# ---------------------------------------------------------------------------
# 6) Pending context: make LLM ask naturally.
# ---------------------------------------------------------------------------
confirm = CONFIRM.read_text(encoding="utf-8")

old_context = '''    return (
        "Calendar pending suggestion context — internal:\\n"
        "- There is a hidden pending Calendar suggestion awaiting user confirmation.\\n"
        "- If the user confirms, you may say you will add it to Calendar.\\n"
        "- If the user asks for Google Calendar, you may say you will sync it to Google Calendar.\\n"
        "- If the user declines, you may say you will ignore/remove the suggestion.\\n"
        "- Do not use internal terms like candidate or event draft.\\n"
        f"- Pending suggestion id: {row.get('id')}\\n"
        f"- Event: {title}\\n"
        f"- Date: {date}\\n"
        f"- Time: {time_text}"
    )
'''

new_context = '''    is_reminder = "reminder" in str(row.get("content") or "").lower()
    item_label = "reminder" if is_reminder else "calendar item"

    return (
        "Calendar/reminder pending suggestion context — internal:\\n"
        f"- There is a hidden pending {item_label} awaiting user confirmation.\\n"
        "- If the user seems to be asking you to remember/remind/schedule something, ask for confirmation naturally.\\n"
        "- For reminders, prefer wording like: 'Mau aku ingetin?' or 'Do you want me to remind you?'\\n"
        "- If the user confirms, you may say you will add it to Calendar/reminders.\\n"
        "- If the user asks for Google Calendar, you may say you will sync it to Google Calendar.\\n"
        "- If the user declines, you may say you will ignore/remove the suggestion.\\n"
        "- Do not use internal terms like candidate or event draft.\\n"
        f"- Pending suggestion id: {row.get('id')}\\n"
        f"- Item: {title}\\n"
        f"- Date: {date}\\n"
        f"- Time: {time_text}"
    )
'''

if old_context not in confirm:
    raise SystemExit("pending calendar context block not found")
confirm = confirm.replace(old_context, new_context, 1)

for required in [
    "Calendar/reminder pending suggestion context",
    "Mau aku ingetin",
    "is_reminder",
]:
    if required not in confirm:
        raise SystemExit(f"confirmation context missing {required}")

CONFIRM.write_text(confirm, encoding="utf-8")

print("added Smart Reminder Detection v1")
