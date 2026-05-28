"""
SSE streaming endpoints.

GET /api/stream/recommendations/{user_id} — live recommendation updates
GET /api/stream/explanation/{user_id} — Claude streaming explanation
GET /api/stream/learning-path/{user_id} — Claude streaming learning path
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.database import get_db
from src.db.models import User
from src.db.redis_client import redis_client
from src.ai.assistant import stream_explanation, generate_learning_path
from src.ai.context import build_explanation_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stream", tags=["streaming"])


@router.get("/recommendations/{user_id}")
async def stream_recommendations(user_id: str, request: Request):
    """
    SSE endpoint for live recommendation updates.

    Frontend subscribes with EventSource. When re-ranking fires,
    the new ranked list is pushed here automatically.
    Cards reorder live without page refresh.
    """
    async def event_generator():
        # Send initial data (try Redis, but continue if not available)
        try:
            cached = await redis_client.get_cached_recommendations(user_id)
        except Exception:
            cached = None

        if cached:
            yield f"data: {json.dumps({'type': 'initial', 'recommendations': cached})}\n\n"

        # Subscribe to user-specific Redis channel
        try:
            pubsub = await redis_client.subscribe(f"recommendations:{user_id}")
        except Exception:
            logger.warning(f"Redis unavailable for SSE subscription: {user_id}")
            yield f"data: {json.dumps({'type': 'error', 'message': 'Real-time updates unavailable. Refresh for latest recommendations.'})}\n\n"
            return

        try:
            while True:
                if await request.is_disconnected():
                    break

                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=30.0,
                )

                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    yield f"data: {json.dumps({'type': 'update', **data})}\n\n"
                else:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except Exception as e:
            logger.error(f"SSE error for {user_id}: {e}")
        finally:
            try:
                await pubsub.unsubscribe(f"recommendations:{user_id}")
            except Exception:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/explanation/{user_id}")
async def stream_explanation_endpoint(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE endpoint for Claude streaming explanation.

    When user clicks "Explain these recommendations", Claude streams
    a personalized explanation word-by-word.
    """
    # Get user and recommendations
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    try:
        cached = await redis_client.get_cached_recommendations(user_id) or []
    except Exception:
        cached = []

    try:
        weights = await redis_client.get_user_weights(user_id)
    except Exception:
        weights = {}

    user_profile = {
        "name": user.name if user else "User",
        "skill_tags": user.skill_tags if user else [],
        "goal": user.goal if user else None,
        "experience_level": user.experience_level if user else None,
    }

    context = build_explanation_context(user_profile, weights)

    async def token_generator():
        async for token in stream_explanation(context, cached):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/learning-path/{user_id}")
async def stream_learning_path_endpoint(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    SSE endpoint for Claude streaming learning path.
    User clicks "Generate My Path" -> 30-day plan streams in live.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    try:
        cached = await redis_client.get_cached_recommendations(user_id) or []
    except Exception:
        cached = []

    user_profile = {
        "name": user.name if user else "User",
        "skill_tags": user.skill_tags if user else [],
        "goal": user.goal if user else None,
        "weekly_hours": user.weekly_hours if user else 5,
    }

    context = build_explanation_context(user_profile)

    async def token_generator():
        async for token in generate_learning_path(context, cached):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
