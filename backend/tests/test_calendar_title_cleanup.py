from app.services import calendar_candidate_extractor as extractor


def test_calendar_event_title_removes_temporal_leadins():
    assert extractor._clean_calendar_event_title("sekarang padel di Parta Kuningan") == "Padel di Parta Kuningan"
    assert extractor._clean_calendar_event_title("nanti mau ke Epiwalk Mall") == "Epiwalk Mall"
    assert extractor._clean_calendar_event_title("ini mau Bowling sama Mandiri Club") == "Bowling sama Mandiri Club"


def test_calendar_event_title_removes_destination_prefix():
    assert extractor._clean_calendar_event_title("Ke FX Sudirman") == "FX Sudirman"
    assert extractor._clean_calendar_event_title("aku mau ke dentist di Grand Indonesia") == "Dentist di Grand Indonesia"


def test_calendar_event_title_removes_casual_tail():
    assert extractor._clean_calendar_event_title("terapi di Sukhmaraga ya") == "Terapi di Sukhmaraga"
    assert extractor._clean_calendar_event_title("padel di Parta Kuningan hehe") == "Padel di Parta Kuningan"


def test_calendar_event_title_extracts_canonical_golf_title_from_conversation():
    raw = (
        "sayang aku mau kasih tau kamu, hari Minggu (14 juni 2026) "
        "aku ada agenda golf di Rainbow Hills dengan Indosat, "
        "tee off jam 05.52"
    )

    assert (
        extractor._clean_calendar_event_title(raw)
        == "Golf dengan Indosat"
    )


def test_calendar_event_title_reads_human_structured_calendar_value():
    raw = (
        "Calendar event: Golf dengan Indosat; date 2026-06-14; "
        "starts 2026-06-14T05:52:00+07:00; location Rainbow Hills"
    )

    assert (
        extractor._clean_calendar_event_title(raw)
        == "Golf dengan Indosat"
    )
