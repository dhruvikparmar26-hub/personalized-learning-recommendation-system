"""
Recommendations API route.

GET /api/recommendations/{user_id} — Get personalized recommendations.
"""

# FIX [DEPRECATION] — datetime.utcnow() is deprecated in Python 3.12+
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.database import get_db
from src.db.models import User, Interaction
from src.db.redis_client import redis_client
from src.engine.recommender import recommender
from src.engine.cold_start import generate_cold_start_recommendations
from src.schemas.recommendation import RecommendationResponse

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/{user_id}", response_model=RecommendationResponse)
async def get_recommendations(
    user_id: str,
    top_n: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """
    Get personalized course recommendations for a user.

    Strategy:
        1. Check Redis cache first (sub-50ms)
        2. If miss: check if user has interactions
        3. Has interactions -> content similarity + re-rank with weights
        4. No interactions -> cold start with profile tags
    """
    # Verify user exists
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Step 1: Check cache (gracefully handle Redis being unavailable)
    try:
        cached = await redis_client.get_cached_recommendations(user_id)
    except Exception:
        cached = None

    if cached:
        return RecommendationResponse(
            user_id=user_id,
            recommendations=cached[:top_n],
            is_cold_start=False,
            # FIX [DEPRECATION] — use timezone-aware UTC
            generated_at=datetime.now(timezone.utc),
            source="cached",
        )

    # Step 2: Check for interactions
    interaction_result = await db.execute(
        select(Interaction)
        .where(Interaction.user_id == user_id)
        .order_by(Interaction.timestamp.desc())
        .limit(50)
    )
    interactions = interaction_result.scalars().all()

    # Get completed/skipped course IDs to exclude
    exclude_ids = {
        i.course_id for i in interactions
        if i.action in ("complete", "skip")
    }

    if interactions:
        # Step 3: Has interactions — use weights for re-ranking
        try:
            topic_weights = await redis_client.get_user_weights(user_id)
        except Exception:
            topic_weights = {}
        user_tags = list(topic_weights.keys()) if topic_weights else (user.skill_tags or [])

        base_recs = recommender.recommend_for_user(
            user_tags=user_tags,
            top_n=top_n * 2,  # Get extra for filtering
            exclude_ids=exclude_ids,
        )

        # Build interaction times for recency
        interaction_times = {}
        for i in interactions:
            skills = _get_course_skills(i.course_id)
            for skill in skills:
                if skill not in interaction_times or i.timestamp > interaction_times[skill]:
                    interaction_times[skill] = i.timestamp

        recommendations = recommender.re_rank(
            current_list=base_recs,
            topic_weights=topic_weights,
            interaction_times=interaction_times,
        )[:top_n]
        source = "live_ranked"
        is_cold = False
    else:
        # Step 4: Cold start
        recommendations, is_cold = generate_cold_start_recommendations(
            user_tags=user.skill_tags or [],
            exclude_ids=exclude_ids,
            top_n=top_n,
        )
        source = "cold_start"

    # Cache results
    await redis_client.cache_recommendations(user_id, recommendations)

    return RecommendationResponse(
        user_id=user_id,
        recommendations=recommendations,
        is_cold_start=is_cold,
        # FIX [DEPRECATION] — use timezone-aware UTC
        generated_at=datetime.now(timezone.utc),
        source=source,
    )


def _get_course_skills(course_id: str) -> list[str]:
    """Extract skills from a course."""
    if not recommender._is_fitted:
        return []
    if course_id not in recommender.course_id_to_idx:
        return []
    idx = recommender.course_id_to_idx[course_id]
    row = recommender.courses_df.iloc[idx]
    skills_str = row.get("skills", "")
    if not skills_str:
        return []
    return [s.strip().lower() for s in str(skills_str).split(",") if s.strip()]
