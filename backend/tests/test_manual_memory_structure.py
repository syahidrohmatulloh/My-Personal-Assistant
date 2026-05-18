from app.services.manual_memory_structure import auto_structure_manual_memory


def test_timezone_is_detected():
    result = auto_structure_manual_memory(
        content="My timezone is Asia/Jakarta",
        category="other",
    )

    assert result.category == "identity"
    assert result.structured_field == "timezone"
    assert result.structured_value == "Asia/Jakarta"


def test_wib_is_detected_as_jakarta_timezone():
    result = auto_structure_manual_memory(
        content="Saya pakai WIB untuk sapaan pagi/malam",
        category="other",
    )

    assert result.category == "identity"
    assert result.structured_field == "timezone"
    assert result.structured_value == "Asia/Jakarta"


def test_preferred_name_is_detected():
    result = auto_structure_manual_memory(
        content="Panggil aku Beb",
        category="other",
    )

    assert result.category == "identity"
    assert result.structured_field == "preferred_name"
    assert result.structured_value == "Beb"


def test_avoid_name_is_detected():
    result = auto_structure_manual_memory(
        content="Jangan panggil saya pak",
        category="other",
    )

    assert result.category == "preferences"
    assert result.structured_field == "avoid_calling_user"
    assert result.structured_value == "pak"


def test_birthday_is_detected():
    result = auto_structure_manual_memory(
        content="Ulang tahun saya 7 Januari",
        category="other",
    )

    assert result.category == "important_dates"
    assert result.structured_field == "birthday"
    assert result.structured_value == "7 Januari"


def test_ui_preference_is_detected():
    result = auto_structure_manual_memory(
        content="Saya suka UI yang theme-aware, glassy, dan mobile smooth.",
        category="other",
    )

    assert result.category == "preferences"
    assert result.structured_field == "ui_preference"
    assert "theme-aware" in result.structured_value


def test_interaction_preference_is_detected():
    result = auto_structure_manual_memory(
        content="Tolong kalau patch kode jangan incremental, harus hati-hati dan menyeluruh.",
        category="other",
    )

    assert result.category == "relationships"
    assert result.structured_field == "interaction_preference"
    assert "jangan incremental" in result.structured_value.lower()


def test_unknown_memory_still_gets_category_field_value():
    result = auto_structure_manual_memory(
        content="I like quiet afternoons near the window.",
        category="other",
    )

    assert result.category == "other"
    assert result.structured_field == "manual_memory"
    assert result.structured_value == "I like quiet afternoons near the window."


def test_explicit_advanced_override_is_respected_and_normalized():
    result = auto_structure_manual_memory(
        content="Anything",
        category="preferences",
        structured_field="Favorite Food",
        structured_value="Soto Betawi",
    )

    assert result.category == "preferences"
    assert result.structured_field == "favorite_food"
    assert result.structured_value == "Soto Betawi"


def test_short_terms_do_not_match_inside_words():
    examples = [
        "I like quiet afternoons near the window.",  # contains ui in quiet
        "I enjoy luxury hotels sometimes.",          # contains ux in luxury
        "This idea is interesting.",                 # contains id in idea
        "It is raining today.",                      # contains it
    ]

    for text in examples:
        result = auto_structure_manual_memory(content=text, category="other")
        assert result.category == "other", text
        assert result.structured_field == "manual_memory", text
        assert result.structured_value == text, text


def test_ui_and_ux_match_as_clear_terms_only():
    ui = auto_structure_manual_memory(
        content="I prefer UI that is theme-aware and mobile smooth.",
        category="other",
    )
    assert ui.category == "preferences"
    assert ui.structured_field == "ui_preference"

    ux = auto_structure_manual_memory(
        content="UX should be simple enough for non-technical users.",
        category="other",
    )
    assert ux.category == "preferences"
    assert ux.structured_field == "ui_preference"


def test_generic_like_and_want_do_not_overclassify():
    examples = [
        "I like walking after lunch.",
        "I want coffee later.",
        "I plan to read tonight.",
    ]

    for text in examples:
        result = auto_structure_manual_memory(content=text, category="other")
        assert result.category == "other", text
        assert result.structured_field == "manual_memory", text


def test_clear_preferences_still_classify_as_preferences():
    examples = [
        "I prefer concise answers.",
        "Saya lebih suka jawaban yang langsung.",
        "Please use a warm but direct tone.",
        "Saya suka kalau Aliyya menjelaskan step by step.",
    ]

    for text in examples:
        result = auto_structure_manual_memory(content=text, category="other")
        assert result.category == "preferences", text
        assert result.structured_field != "manual_memory", text
