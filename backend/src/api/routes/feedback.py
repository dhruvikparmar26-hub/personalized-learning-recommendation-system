"""
Feedback API route.

POST /api/feedback — Record user feedback and trigger real-time re-ranking.
"""

# FIX [DEPRECATION] — datetime.utcnow() is deprecated in Python 3.12+
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.database import get_db
from src.db.models import User, Course, Interaction
from src.db.redis_client import redis_client
from src.schemas.feedback import FeedbackCreate, FeedbackResponse

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("/", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Record user feedback on a course and trigger re-ranking.

    Flow:
        1. Validate user and course exist
        2. Write interaction to PostgreSQL
        3. Publish event to Redis (triggers re-ranking async)
        4. Return immediately — re-ranking happens in background

    The Redis event triggers the event listener which:
        - Adjusts topic weights
        - Re-ranks the recommendation list
        - Pushes update via SSE to the user's browser
    """
    # Validate user
    user_result = await db.execute(
        select(User).where(User.id == feedback.user_id)
    )
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    # Validate course
    course_result = await db.execute(
        select(Course).where(Course.id == feedback.course_id)
    )
    if not course_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Course not found")

    # Write to database
    interaction = Interaction(
        user_id=feedback.user_id,
        course_id=feedback.course_id,
        action=feedback.action,
        # FIX [DEPRECATION] — use timezone-aware UTC instead of deprecated utcnow()
        timestamp=datetime.now(timezone.utc),
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)

    # Publish event to Redis — triggers re-ranking in event listener
    # FIX [ERROR_HANDLING] — wrap Redis operations in try/except to prevent
    # feedback endpoint from crashing when Redis is unavailable
    try:
        await redis_client.publish_event("interaction_events", {
            "user_id": feedback.user_id,
            "course_id": feedback.course_id,
            "action": feedback.action,
            # FIX [DEPRECATION] — use timezone-aware UTC
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Invalidate cached recommendations
        await redis_client.invalidate_recommendations(feedback.user_id)
    except Exception:
        pass  # Redis unavailable — feedback still saved to DB

    return FeedbackResponse(
        id=interaction.id,
        user_id=interaction.user_id,
        course_id=interaction.course_id,
        action=interaction.action,
        timestamp=interaction.timestamp,
        message="Feedback recorded. Recommendations will update in real-time.",
    )
