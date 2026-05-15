"""Journal endpoints — daily check-in.

GET  /journal/today    → did the user journal today? Returns entry or null.
POST /journal          → save a new entry, schedule event extraction.
GET  /journal/recent   → last 30 days of self-reported entries.
"""

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_user_id
from app.services import journal

router = APIRouter(prefix="/journal", tags=["journal"])


class JournalIn(BaseModel):
    mood: int | None = Field(default=None, ge=-5, le=5)
    energy: int | None = Field(default=None, ge=-5, le=5)
    stress: int | None = Field(default=None, ge=-5, le=5)
    note: str | None = Field(default=None, max_length=4000)


@router.get("/today")
async def get_todays_entry(user_id: str = Depends(get_current_user_id)):
    entry = await journal.todays_entry(user_id)
    return {"entry": entry}


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_entry(
    body: JournalIn,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    saved = await journal.save_entry(
        user_id=user_id,
        mood=body.mood,
        energy=body.energy,
        stress=body.stress,
        note=body.note,
    )

    if body.note and len(body.note.strip()) >= 20:
        background_tasks.add_task(
            journal.extract_events_from_entry,
            user_id=user_id,
            entry_text=body.note,
            entry_date=date.today(),
        )
        # Parallel: extract notes about registered people + goal check-ins
        # from the same journal text. Conservative — only writes when
        # specific people/goals are named.
        background_tasks.add_task(
            journal.extract_people_and_goals_from_entry,
            user_id=user_id,
            entry_text=body.note,
        )

    return saved


@router.get("/recent")
async def get_recent(user_id: str = Depends(get_current_user_id)):
    return await journal.recent_entries(user_id, days=30)
