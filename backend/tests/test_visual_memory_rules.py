from app.services.visual_memory_rules import decide_visual_memory


def test_skips_ui_screenshot_memory():
    decision = decide_visual_memory("A screenshot of a browser showing a Supabase SQL editor error message.")
    assert decision is not None
    assert decision.should_store is False
    assert decision.reason == "skip_screenshot_or_debug"


def test_stores_personal_travel_photo_candidate():
    decision = decide_visual_memory(
        "A person in a black coat smiles on a boat with the Statue of Liberty visible in New York Harbor."
    )
    assert decision is not None
    assert decision.should_store is True
    assert decision.structured_field == "visual_memory_personal_travel_photo"


def test_stores_food_photo_candidate():
    decision = decide_visual_memory("A takeout box contains fried chicken, vegetables, and sauce.")
    assert decision is not None
    assert decision.should_store is True
    assert decision.structured_field == "visual_memory_food_photo"


def test_skips_generic_unclear_image():
    decision = decide_visual_memory("A blurry object on a table.")
    assert decision is not None
    assert decision.should_store is False
