"""
Learning Path API route.

GET /api/learning-path/{user_id} — Get or generate learning path.
POST /api/learning-path/{user_id}/progress — Update course progress.
"""

# FIX [CODE_QUALITY] — moved json import to module level (was inline)
import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.redis_client import redis_client

router = APIRouter(prefix="/api/learning-path", tags=["learning-path"])


@router.get("/{user_id}")
async def get_learning_path(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the user's current learning path.
    If none exists, returns empty — user must click 'Generate My Path'
    which triggers the SSE streaming endpoint.
    """
    # FIX [ERROR_HANDLING] — wrap Redis call so endpoint doesn't crash
    # when Redis is unavailable
    try:
        cached = await redis_client.get_cache(f"learning_path:{user_id}")
    except Exception:
        cached = None

    if cached:
        return {"user_id": user_id, "path": json.loads(cached), "exists": True}
    return {"user_id": user_id, "path": None, "exists": False}

