from app.services import manual_memory_structure, name_normalization


def test_greeting_petname_does_not_rename_assistant():
    names = name_normalization.extract_explicit_names("hai beb")
    assert names.assistant_name is None


def test_calling_assistant_petname_does_not_rename_assistant():
    names = name_normalization.extract_explicit_names("aku panggil kamu beb ya")
    assert names.assistant_name is None


def test_assistant_name_changes_only_with_nama_kamu_phrase():
    names = name_normalization.extract_explicit_names("nama kamu Aliyya")
    assert names.assistant_name == "Aliyya"


def test_assistant_name_can_change_to_zahra_with_explicit_phrase():
    names = name_normalization.extract_explicit_names("nama kamu Zahra")
    assert names.assistant_name == "Zahra"


def test_assistant_name_can_change_to_beb_when_explicitly_named_beb():
    names = name_normalization.extract_explicit_names("nama kamu beb")
    assert names.assistant_name is not None
    assert names.assistant_name.lower() == "beb"


def test_change_assistant_name_phrase_works():
    names = name_normalization.extract_explicit_names("ganti nama kamu jadi Zahra")
    assert names.assistant_name == "Zahra"


def test_manual_memory_does_not_store_panggil_kamu_beb_as_assistant_name():
    assert manual_memory_structure._detect_assistant_name("panggil kamu beb") is None


def test_manual_memory_stores_nama_kamu_as_assistant_name():
    assert manual_memory_structure._detect_assistant_name("nama kamu Aliyya") == "Aliyya"
