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
    command = detect_assistant_mode_command("mode chief of staff")
    text = render_mode_command_confirmation(command, previous_mode="life_companion")
    assert "beb" not in text.lower()
    assert "sayang" not in text.lower()
    assert "Chief of Staff mode" in text
