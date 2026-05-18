#!/usr/bin/env python3
"""Patch My Personal Assistant to send browser local time to backend prompts.

Run from repo root:
  python3 timezone_context_patch.py
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()


def require(path: str) -> Path:
    p = ROOT / path
    if not p.exists():
        raise SystemExit(f"Missing expected file: {path}\nRun this from /Users/syahidrohmatulloh/my-assistant")
    return p


def backup(p: Path) -> None:
    b = p.with_suffix(p.suffix + ".before-timezone-context")
    if not b.exists():
        b.write_text(p.read_text())


def write_if_changed(p: Path, text: str) -> bool:
    old = p.read_text() if p.exists() else None
    if old == text:
        return False
    if p.exists():
        backup(p)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return True


changed: list[str] = []

# ---------------------------------------------------------------------------
# 1) Frontend helper: capture browser timezone/local time.
# ---------------------------------------------------------------------------
client_ctx_path = ROOT / "frontend/lib/client-time-context.ts"
client_ctx_text = '''export type ClientTimeContext = {
  timezone: string;
  local_time: string;
  utc_offset_minutes: number;
  locale: string;
  source: "browser";
  captured_at_utc: string;
};

function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function formatLocalTime(date: Date, timeZone: string): string {
  try {
    // sv-SE gives a stable ISO-like local timestamp: YYYY-MM-DD HH:mm:ss.
    return date.toLocaleString("sv-SE", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return date.toLocaleString("sv-SE", { hour12: false });
  }
}

export function buildClientTimeContext(): ClientTimeContext {
  const now = new Date();
  const timezone = getBrowserTimeZone();

  return {
    timezone,
    local_time: formatLocalTime(now, timezone),
    // JavaScript returns minutes behind UTC. Invert it, so Jakarta = +420.
    utc_offset_minutes: -now.getTimezoneOffset(),
    locale: typeof navigator !== "undefined" ? navigator.language : "unknown",
    source: "browser",
    captured_at_utc: now.toISOString(),
  };
}
'''
if write_if_changed(client_ctx_path, client_ctx_text):
    changed.append(str(client_ctx_path.relative_to(ROOT)))

# ---------------------------------------------------------------------------
# 2) Frontend API: include client_context in streamChat request body.
# ---------------------------------------------------------------------------
api_path = require("frontend/lib/api.ts")
api_text = api_path.read_text()
orig = api_text
if 'client-time-context' not in api_text:
    # Keep imports simple and deterministic.
    api_text = api_text.replace(
        'import { createClient } from "@/lib/supabase/client";\n',
        'import { createClient } from "@/lib/supabase/client";\nimport { buildClientTimeContext } from "@/lib/client-time-context";\n',
        1,
    )
if 'client_context:' not in api_text:
    if 'attachment_ids: attachmentIds,' in api_text:
        api_text = api_text.replace(
            '      attachment_ids: attachmentIds,\n',
            '      attachment_ids: attachmentIds,\n      client_context: buildClientTimeContext(),\n',
            1,
        )
    elif '      message,\n' in api_text:
        api_text = api_text.replace(
            '      message,\n',
            '      message,\n      client_context: buildClientTimeContext(),\n',
            1,
        )
    else:
        raise SystemExit("Could not find streamChat JSON body insertion point in frontend/lib/api.ts")
if api_text != orig:
    backup(api_path)
    api_path.write_text(api_text)
    changed.append(str(api_path.relative_to(ROOT)))

# ---------------------------------------------------------------------------
# 3) Backend schemas: accept client_context.
# Patch both schemas package and legacy schemas.py if present.
# ---------------------------------------------------------------------------
def patch_schema_file(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text()
    orig = text

    if 'class ClientContextIn(BaseModel):' not in text:
        marker = '# --- Chat ---'
        cls = '''\n\nclass ClientContextIn(BaseModel):\n    # Browser-provided local time context for this chat turn.\n    # This is prompt context only; it is not persisted.\n    timezone: str | None = Field(default=None, max_length=80)\n    local_time: str | None = Field(default=None, max_length=64)\n    utc_offset_minutes: int | None = None\n    locale: str | None = Field(default=None, max_length=32)\n    source: str | None = Field(default="browser", max_length=32)\n    captured_at_utc: str | None = Field(default=None, max_length=64)\n'''
        if marker in text:
            text = text.replace(marker, marker + cls, 1)
        else:
            # Legacy small schemas.py may not have section comments.
            insert_at = text.find('class ChatIn(BaseModel):')
            if insert_at == -1:
                raise SystemExit(f"Could not find ChatIn in {path}")
            text = text[:insert_at] + cls + "\n" + text[insert_at:]

    if 'client_context:' not in text:
        # Prefer after attachment_ids if present, else after message.
        if re.search(r'attachment_ids:.*\n', text):
            text = re.sub(
                r'(\s+attachment_ids:.*\n)',
                r'\1    client_context: ClientContextIn | None = None\n',
                text,
                count=1,
            )
        elif re.search(r'\s+message:.*\n', text):
            text = re.sub(
                r'(\s+message:.*\n)',
                r'\1    client_context: ClientContextIn | None = None\n',
                text,
                count=1,
            )
        else:
            raise SystemExit(f"Could not add client_context field in {path}")

    # Legacy schemas.py may not import Field.
    if 'Field(' in text and 'from pydantic import BaseModel, Field' not in text:
        text = text.replace('from pydantic import BaseModel', 'from pydantic import BaseModel, Field', 1)

    if text != orig:
        backup(path)
        path.write_text(text)
        changed.append(str(path.relative_to(ROOT)))

patch_schema_file(ROOT / "backend/app/schemas/__init__.py")
patch_schema_file(ROOT / "backend/app/schemas.py")

# ---------------------------------------------------------------------------
# 4) Prompt builder: render browser local time as explicit source of truth.
# ---------------------------------------------------------------------------
prompt_path = require("backend/app/services/prompt_builder.py")
prompt_text = prompt_path.read_text()
orig = prompt_text

if 'def render_client_time_context(' not in prompt_text:
    insert_marker = '# ---------------------------------------------------------------------------\n# Main renderer\n# ---------------------------------------------------------------------------'
    block = r'''
# ---------------------------------------------------------------------------
# Client local time context
# ---------------------------------------------------------------------------

def _format_utc_offset_label(offset_minutes: Any) -> str | None:
    try:
        minutes = int(offset_minutes)
    except Exception:  # noqa: BLE001
        return None
    sign = "+" if minutes >= 0 else "-"
    absolute = abs(minutes)
    hours = absolute // 60
    mins = absolute % 60
    if mins == 0:
        return f"GMT{sign}{hours}"
    return f"GMT{sign}{hours}:{mins:02d}"


def render_client_time_context(
    client_context: dict[str, Any] | None,
    profile: dict[str, Any] | None = None,
) -> str:
    """Render browser-provided time context for the current turn.

    Browser local time is the source of truth for greetings and time-sensitive
    wording. Server time is intentionally not used because the backend may run
    in UTC or another region.
    """
    ctx = client_context or {}
    profile = profile or {}

    timezone_name = ctx.get("timezone") or profile.get("timezone")
    local_time = ctx.get("local_time")
    locale = ctx.get("locale")
    offset_label = _format_utc_offset_label(ctx.get("utc_offset_minutes"))
    captured_at_utc = ctx.get("captured_at_utc")

    if not timezone_name and not local_time and not offset_label:
        return ""

    lines = [
        "## User local time — source of truth for this turn",
        "Use the browser/client local time below for greetings, date references, countdowns, and time-sensitive answers.",
        "Do NOT infer the current time from server time, UTC, logs, or model knowledge unless the user explicitly asks for UTC/server time.",
    ]
    if timezone_name:
        lines.append(f"- User local timezone: {timezone_name}")
    if local_time:
        lines.append(f"- User local time now: {local_time}")
    if offset_label:
        lines.append(f"- UTC offset: {offset_label}")
    if locale:
        lines.append(f"- Browser locale: {locale}")
    if captured_at_utc:
        lines.append(f"- Captured at UTC: {captured_at_utc} (debug only; do not prefer over local time)")

    return "\n".join(lines)

'''
    if insert_marker not in prompt_text:
        raise SystemExit("Could not find Main renderer marker in prompt_builder.py")
    prompt_text = prompt_text.replace(insert_marker, block + insert_marker, 1)

if prompt_text != orig:
    backup(prompt_path)
    prompt_path.write_text(prompt_text)
    changed.append(str(prompt_path.relative_to(ROOT)))

# ---------------------------------------------------------------------------
# 5) Chat router: append client time context to volatile prompt.
# ---------------------------------------------------------------------------
chat_path = require("backend/app/routers/chat.py")
chat_text = chat_path.read_text()
orig = chat_text

if 'render_client_time_context' not in chat_text:
    chat_text = chat_text.replace(
        'from app.services.prompt_builder import (\n    BASE_PROMPT,\n    render_context,\n    trim_history,\n)',
        'from app.services.prompt_builder import (\n    BASE_PROMPT,\n    render_client_time_context,\n    render_context,\n    trim_history,\n)',
        1,
    )

if 'client_time_block = render_client_time_context' not in chat_text:
    needle = '    volatile_context = render_context(context)\n'
    add = '''    identity = context.get("identity") or {}\n    profile = identity.get("profile") or {}\n    raw_client_context = None\n    if getattr(body, "client_context", None) is not None:\n        raw = body.client_context\n        raw_client_context = (\n            raw.model_dump(exclude_none=True)\n            if hasattr(raw, "model_dump")\n            else raw.dict(exclude_none=True)\n            if hasattr(raw, "dict")\n            else raw\n        )\n    client_time_block = render_client_time_context(raw_client_context, profile)\n    if client_time_block:\n        volatile_context += "\\n\\n" + client_time_block\n'''
    if needle not in chat_text:
        raise SystemExit("Could not find volatile_context assignment in chat.py")
    chat_text = chat_text.replace(needle, needle + add, 1)

if chat_text != orig:
    backup(chat_path)
    chat_path.write_text(chat_text)
    changed.append(str(chat_path.relative_to(ROOT)))

# ---------------------------------------------------------------------------
# 6) Smoke test helper.
# ---------------------------------------------------------------------------
smoke_path = ROOT / "backend/tools/smoke_client_time_context.py"
smoke_text = '''#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.prompt_builder import render_client_time_context

block = render_client_time_context(
    {
        "timezone": "Asia/Jakarta",
        "local_time": "2026-05-18 13:05:00",
        "utc_offset_minutes": 420,
        "locale": "id-ID",
        "source": "browser",
        "captured_at_utc": "2026-05-18T06:05:00.000Z",
    },
    {},
)

print(block)
assert "Asia/Jakarta" in block
assert "13:05" in block
assert "GMT+7" in block
assert "source of truth" in block
print("OK: client local time context rendered correctly")
'''
if write_if_changed(smoke_path, smoke_text):
    changed.append(str(smoke_path.relative_to(ROOT)))

print("Timezone context patch complete.")
if changed:
    print("Changed files:")
    for item in changed:
        print(f"- {item}")
else:
    print("No file changes needed; patch was already applied.")
print("\nNext:")
print("  rm -rf frontend/.next")
print("  pnpm --dir frontend build")
print("  cd backend && python tools/smoke_client_time_context.py")
