import re


def detect_nickname_instruction(message: str):
    msg = message.lower()

    # set nickname
    match_set = re.search(r"panggil aku (.+)", msg)
    if match_set:
        return {
            "action": "set",
            "nickname": match_set.group(1).strip()
        }

    # remove nickname
    if "jangan panggil aku" in msg:
        return {
            "action": "remove"
        }

    return None
