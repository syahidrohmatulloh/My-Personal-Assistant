def detect_communication_style(message: str) -> str:
    msg = message.lower()

    if any(w in msg for w in ["gw", "gue", "lo", "lu"]):
        return "casual_indonesia"

    if any(w in msg for w in ["aku", "kamu"]):
        return "soft_indonesia"

    if any(w in msg for w in ["i", "you"]):
        return "english"

    return "neutral"
