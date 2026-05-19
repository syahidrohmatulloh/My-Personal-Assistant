from app.services.response_texture import render_response_texture_block


def test_professional_context_gets_zero_emoji_budget():
    block = render_response_texture_block(
        user_message="Aku meeting sama debitur jam 5 sore.",
        messages=[],
        companion_settings_row={"companion_mode": "partner"},
        current_mood={"mood": "warm"},
        user_mood_context={"label": "calm"},
    )

    assert "at most 0" in block
    assert "professional or time-sensitive context" in block


def test_affectionate_context_allows_one_symbol_when_not_recently_overused():
    block = render_response_texture_block(
        user_message="Aku capek beb, pengen ditemenin.",
        messages=[],
        companion_settings_row={"companion_mode": "partner"},
        current_mood={"mood": "warm"},
        user_mood_context={"label": "tired"},
    )

    assert "at most 1" in block
    assert "warm or affectionate context" in block or "gentle emotional support" in block


def test_recent_symbol_overuse_forces_restraint():
    smile = chr(0x1F60A)
    laugh = chr(0x1F602)

    block = render_response_texture_block(
        user_message="Santai dulu ya",
        messages=[
            {"role": "assistant", "content": f"Oke {smile}"},
            {"role": "user", "content": "lanjut"},
            {"role": "assistant", "content": f"Siap {laugh}"},
        ],
        companion_settings_row={"companion_mode": "partner"},
        current_mood={"mood": "warm"},
        user_mood_context={"label": "calm"},
    )

    assert "at most 0" in block
    assert "recent replies already used emoji-like symbols often" in block
    assert smile in block
    assert laugh in block
