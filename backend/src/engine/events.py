"""
Redis event listener that triggers real-time re-ranking.

Event flow:
    User action -> POST /feedback -> Redis PUBLISH -> this listener -> re_rank() -> push via SSE

This is the heartbeat of real-time. It runs as a background asyncio task
started during FastAPI lifespan. When a user gives feedback:
    1. Receives event from 'interaction_events' channel
    2. Adjusts topic weights in Redis
    3. Triggers re-ranking for the affected user
    4. Pushes updated list to ConnectionManager for SSE broadcast

Target: entire loop under 200ms.
"""

import json
import logging
# FIX [DEPRECATION] — datetime.utcnow() is deprecated in Python 3.12+
from datetime import datetime, timezone

from src.db.redis_client import redis_client
from src.engine.recommender import recommender
from src.engine.scorer import compute_weight_delta

logger = logging.getLogger(__name__)

# Reference to connection manager — set during app startup
_connection_manager = None
_running = False


def set_connection_manager(manager):
    """Called during app startup to inject the ConnectionManager."""
    global _connection_manager
    _connection_manager = manager


async def start_event_listener():
    """
    Background task that listens to Redis interaction events
    and triggers re-ranking for affected users.
    
    Started during FastAPI lifespan, runs indefinitely.
    """
    global _running
    _running = True
    logger.info("Redis event listener started on channel: interaction_events")

    try:
        pubsub = await redis_client.subscribe("interaction_events")
    except Exception:
        logger.info("Redis unavailable; event listener disabled")
        _running = False
        return

    try:
        async for message in pubsub.listen():
            if not _running:
                break
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
                await handle_interaction_event(data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in event: {message['data']}")
            except Exception as e:
                logger.error(f"Error handling event: {e}", exc_info=True)
    finally:
        await pubsub.unsubscribe("interaction_events")
        logger.info("Redis event listener stopped")


async def handle_interaction_event(data: dict):
    """
    Process a single interaction event.
    
    Expected data: {user_id, course_id, action, timestamp}
    
    Steps:
        1. Get course skills from the recommender
        2. Compute weight delta based on action
        3. Update each topic weight in Redis
        4. Get current recommendation list
        5. Re-rank with updated weights
        6. Cache new list and push via SSE
    """
    user_id = data.get("user_id")
    course_id = data.get("course_id")
    action = data.get("action")

    if not all([user_id, course_id, action]):
        logger.warning(f"Incomplete event data: {data}")
        return

    # FIX [DEPRECATION] — use timezone-aware UTC
    start_time = datetime.now(timezone.utc)
    logger.info(f"Processing event: {user_id} -> {action} -> {course_id}")

    # Step 1: Get course skills
    course_skills = _get_course_skills(course_id)
    if not course_skills:
        logger.warning(f"No skills found for course {course_id}")
        course_skills = ["general"]

    # Step 2: Compute weight delta
    delta = compute_weight_delta(action)

    # Step 3: Update topic weights in Redis
    for skill in course_skills:
        new_weight = await redis_client.update_topic_weight(
            user_id, skill, delta
        )
        logger.debug(f"  {skill}: weight -> {new_weight}")

    # Step 4: Get current recommendations
    cached = await redis_client.get_cached_recommendations(user_id)
    if not cached:
        # No cached list — generate fresh
        user_weights = await redis_client.get_user_weights(user_id)
        tags = list(user_weights.keys()) if user_weights else ["general"]
        cached = recommender.recommend_for_user(
            user_tags=tags, top_n=20, exclude_ids=set()
        )

    # Step 5: Re-rank with updated weights
    topic_weights = await redis_client.get_user_weights(user_id)
    re_ranked = recommender.re_rank(
        current_list=cached,
        topic_weights=topic_weights,
    )

    # Step 6: Cache and push
    await redis_client.cache_recommendations(user_id, re_ranked)

    # Push to SSE via connection manager
    if _connection_manager:
        await _connection_manager.send_recommendations(
            user_id, re_ranked
        )

    # Also publish to user-specific Redis channel for SSE subscribers
    await redis_client.publish_event(
        f"recommendations:{user_id}",
        {"recommendations": re_ranked, "source": "live_ranked"},
    )

    # FIX [DEPRECATION] — use timezone-aware UTC
    elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    logger.info(
        f"Re-ranking complete for {user_id}: "
        f"{len(re_ranked)} courses, {elapsed_ms:.0f}ms"
    )


async def stop_event_listener():
    """Signal the event listener to stop."""
    global _running
    _running = False


def _get_course_skills(course_id: str) -> list[str]:
    """Extract skills from a course in the recommender's dataset."""
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
