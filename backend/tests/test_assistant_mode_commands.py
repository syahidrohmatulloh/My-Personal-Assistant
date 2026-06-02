from app.services.assistant_mode_commands import (
    detect_assistant_mode_command,
    render_mode_command_confirmation,
)


def test_detect_chief_of_staff_indonesian_command():
    command = detect_assistant_mode_command("Aliyya, mode serius dulu")
    assert command is not None
    assert command.target_mode == "chief_of_staff"


def test_detect_life_companion_indonesian_command():
    command = detect_assistant_mode_command("balik companion mode aja")
    assert command is not None
    assert command.target_mode == "life_companion"


def test_does_not_trigger_explanatory_question():
    assert detect_assistant_mode_command("apa itu chief of staff mode?") is None
    assert detect_assistant_mode_command("jelaskan life companion mode") is None


def test_confirmation_has_no_affectionate_nickname():
    command = detect_assistant_mode_command("mode chief of staff lagi")
    text = render_mode_command_confirmation(command, previous_mode="life_companion")
    assert "beb" not in text.lower()
    assert "sayang" not in text.lower()
    assert "Chief of Staff mode" in text

def test_does_not_trigger_when_discussing_two_mode_feature_indonesian():
    assert (
        detect_assistant_mode_command(
            "lagi mau buat 2 mode nih, mode chief of staff sama companion mode"
        )
        is None
    )


def test_does_not_trigger_when_discussing_two_mode_feature_english():
    assert (
        detect_assistant_mode_command(
            "I want to build two modes: Chief of Staff and Life Companion."
        )
        is None
    )


def test_does_not_trigger_when_discussing_prompt_english():
    assert (
        detect_assistant_mode_command(
            "I am thinking about changing the prompt for Chief of Staff mode."
        )
        is None
    )


def test_still_detects_mode_companion_lagi_command():
    command = detect_assistant_mode_command("Aliyya, mode companion lagi")
    assert command is not None
    assert command.target_mode == "life_companion"


def test_still_detects_mode_serius_lagi_command():
    command = detect_assistant_mode_command("Aliyya, mode serius lagi")
    assert command is not None
    assert command.target_mode == "chief_of_staff"


def test_still_detects_english_switch_command():
    command = detect_assistant_mode_command("Switch to Chief of Staff mode.")
    assert command is not None
    assert command.target_mode == "chief_of_staff"
