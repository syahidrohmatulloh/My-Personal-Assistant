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
