from app.services.memory_consolidation import build_consolidation_candidates


def row(content, **extra):
    return {
        "id": extra.get("id", content[:8]),
        "content": content,
        "category": extra.get("category", "other"),
        "structured_field": extra.get("structured_field"),
        "structured_value": extra.get("structured_value"),
        "confidence": extra.get("confidence", 0.8),
        "superseded": extra.get("superseded", False),
    }


def test_no_consolidation_for_too_few_memories():
    candidates = build_consolidation_candidates(
        [
            row("User likes direct answers."),
            row("User likes UI polish."),
        ]
    )

    assert candidates == []


def test_builds_monthly_development_focus():
    candidates = build_consolidation_candidates(
        [
            row("User is building Aliyya personal assistant memory system."),
            row("User added mood context for Aliyya."),
            row("User is polishing frontend UI and mobile sidebar."),
            row("User is working on backend deploy and memory reliability."),
        ],
        days=30,
    )

    fields = {c.structured_field for c in candidates}
    assert "monthly_focus" in fields

    monthly = next(c for c in candidates if c.structured_field == "monthly_focus")
    assert monthly.category == "goals"
    assert monthly.kind == "context"
    assert "memory reliability" in monthly.content
    assert monthly.confidence >= 0.8


def test_builds_interaction_pattern():
    candidates = build_consolidation_candidates(
        [
            row("User prefers careful comprehensive patch instead of incremental fixes."),
            row("User wants root cause debugging help during deploy errors."),
            row("User asked for full patch implementation support."),
        ],
        days=30,
    )

    fields = {c.structured_field for c in candidates}
    assert "consolidated_interaction_pattern" in fields


def test_builds_ui_design_preference():
    candidates = build_consolidation_candidates(
        [
            row("User appreciates polished UI with glass vibes."),
            row("User wants theme-aware contrast and smooth mobile behavior."),
            row("User wants sidebar hover highlight."),
        ],
        days=30,
    )

    fields = {c.structured_field for c in candidates}
    assert "consolidated_ui_design_preference" in fields


def test_ignores_superseded_rows():
    candidates = build_consolidation_candidates(
        [
            row("User is building Aliyya memory system."),
            row("User is building Aliyya mood system.", superseded=True),
            row("User is polishing frontend UI."),
        ],
        days=30,
    )

    assert candidates == []
