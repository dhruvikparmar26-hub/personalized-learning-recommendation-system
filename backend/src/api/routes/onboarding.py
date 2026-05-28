"""
Onboarding API route.

POST /api/onboarding — Process quiz answers, bootstrap recommendations.
GET /api/onboarding/questions — Return the quiz questions.
"""

# FIX [DEPRECATION] — datetime.utcnow() is deprecated in Python 3.12+
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.database import get_db
from src.db.models import User, OnboardingResponse as OnboardingResponseModel
from src.db.redis_client import redis_client
from src.engine.cold_start import (
    get_onboarding_questions,
    extract_tags_from_answers,
    generate_cold_start_recommendations,
)
from src.schemas.recommendation import (
    OnboardingRequest,
    OnboardingResponse,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.get("/questions", response_model=list[dict])
async def get_questions():
    """Return the onboarding quiz questions."""
    return get_onboarding_questions()


@router.post("/", response_model=OnboardingResponse)
async def submit_onboarding(
    request: OnboardingRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Process onboarding quiz answers.

    1. Extract skill tags from answers
    2. Update user profile with tags
    3. Store quiz responses
    4. Generate cold-start recommendations
    5. Cache recommendations in Redis
    """
    # Verify user exists
    result = await db.execute(select(User).where(User.id == request.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Extract tags from answers
    skill_tags = extract_tags_from_answers(
        [a.model_dump() for a in request.answers]
    )

    # Update user profile
    existing_tags = set(user.skill_tags or [])
    existing_tags.update(skill_tags)
    user.skill_tags = list(existing_tags)
    # FIX [DEPRECATION] — use timezone-aware UTC
    user.updated_at = datetime.now(timezone.utc)

    # Store quiz responses
    for answer in request.answers:
        response = OnboardingResponseModel(
            user_id=request.user_id,
            question_id=answer.question_id,
            question_text=next(
                (q["question_text"] for q in get_onboarding_questions()
                 if q["question_id"] == answer.question_id),
                "",
            ),
            answer=answer.answer,
            skill_tags=answer.skill_tags or [],
        )
        db.add(response)

    await db.commit()

    # Generate cold-start recommendations
    recommendations, _ = generate_cold_start_recommendations(
        user_tags=list(existing_tags),
        top_n=10,
    )

    # FIX [ERROR_HANDLING] — wrap Redis operations so onboarding doesn't
    # crash when Redis is unavailable
    try:
        # Cache in Redis
        await redis_client.cache_recommendations(request.user_id, recommendations)
        # Initialize topic weights from tags
        for tag in existing_tags:
            await redis_client.update_topic_weight(request.user_id, tag, 0.0)
    except Exception:
        pass  # Redis unavailable — onboarding still succeeds

    return OnboardingResponse(
        user_id=request.user_id,
        skill_tags=list(existing_tags),
        initial_recommendations=recommendations,
    )
