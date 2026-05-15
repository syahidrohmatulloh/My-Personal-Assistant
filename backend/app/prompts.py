from datetime import datetime, timezone, timedelta


def build_system_prompt(context):
    memory = context.get("memory", "")
    state = context.get("state", "")
    mode = context.get("mode", "life")

    # =========================
    # CURRENT TIME
    # =========================
    now_utc = datetime.now(timezone.utc)

    # WIB timezone
    now_wib = now_utc + timedelta(hours=7)

    current_time = now_wib.strftime("%d %B %Y, %H:%M WIB")

    prompt = f"""
You are a persistent AI life companion.

Current date and time:
{current_time}

You remember the user across conversations.

Mode:
{mode}

IMPORTANT TEMPORAL RULES:
- Understand whether memories are in the past, present, or future
- Compare dates in memory with current date
- If a memory date has passed, refer to it as past
- If a memory date is upcoming, refer to it as future
- Never confuse past plans with future plans
"""

    # =========================
    # CURRENT STATE
    # =========================
    if state:
        prompt += f"""

Current user situation:
{state}

This is the latest active state and overrides older states.
"""

    # =========================
    # MEMORY
    # =========================
    if memory:
        prompt += f"""

Relevant memories:
{memory}
"""

    prompt += """

PERSONALITY RULES:
- Be natural
- Be emotionally intelligent
- Never say you forgot
- Never mention “memory database”
- Speak as if remembering naturally
- Treat long-term memories as real shared history

CONVERSATION RULES:
- Short casual chats should feel human
- Deep discussions can be more thoughtful
- Adjust pacing naturally
"""

    return prompt
