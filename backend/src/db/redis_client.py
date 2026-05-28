"""
Async Redis client for pub/sub, caching, and topic weight storage.

Redis is the backbone of real-time in this system:
- Pub/sub: interaction events trigger re-ranking
- Cache: pre-computed similarity scores for sub-100ms response
- Hash: per-user topic weights that adjust on every like/skip
"""

import json
from typing import Optional
import redis.asyncio as aioredis

from src.config import settings


class RedisClient:
    """
    Async Redis client wrapper with helpers for the recommendation engine.
    
    Channels:
        - interaction_events: published when user likes/skips/saves/completes a course
        - recommendations:{user_id}: published when re-ranking produces a new list
    
    Keys:
        - user_weights:{user_id}: hash of topic → weight
        - recommendations:{user_id}: cached ranked list (JSON)
        - similarity_matrix: serialized similarity data
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._connected = False

    async def connect(self):
        """Initialize the Redis connection pool."""
        self._redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        try:
            await self._redis.ping()
            self._connected = True
        except Exception:
            self._redis = None
            self._connected = False

    async def disconnect(self):
        """Close the Redis connection pool."""
        if self._redis:
            await self._redis.close()
        self._redis = None
        self._connected = False

    @property
    def client(self) -> aioredis.Redis:
        """Get the raw Redis client for direct operations."""
        if not self._redis:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._redis

    # ── Pub/Sub ─────────────────────────────────────────────────

    async def publish_event(self, channel: str, data: dict):
        """
        Publish an event to a Redis channel.
        
        Used when a user interaction occurs:
            await redis.publish_event("interaction_events", {
                "user_id": "abc",
                "course_id": "xyz",
                "action": "like"
            })
        """
        if not self._redis:
            return
        await self._redis.publish(channel, json.dumps(data))

    async def subscribe(self, channel: str):
        """
        Subscribe to a Redis channel. Returns a pubsub object.
        
        Usage:
            pubsub = await redis.subscribe("interaction_events")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
        """
        if not self._redis:
            raise RuntimeError("Redis not connected. Call connect() first.")
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        return pubsub

    # ── User Topic Weights ──────────────────────────────────────

    async def get_user_weights(self, user_id: str) -> dict[str, float]:
        """
        Retrieve topic weights for a user.
        Returns dict of {topic: weight} where weight defaults to 1.0.
        
        These weights are adjusted on every like/skip:
            - like → +0.2 to that course's topics
            - skip → -0.3 to that course's topics
            - complete → +0.5
            - save → +0.15
        """
        if not self._redis:
            return {}
        raw = await self._redis.hgetall(f"user_weights:{user_id}")
        return {k: float(v) for k, v in raw.items()} if raw else {}

    async def set_user_weights(self, user_id: str, weights: dict[str, float]):
        """Store updated topic weights for a user."""
        if not self._redis or not weights:
            return
        str_weights = {k: str(v) for k, v in weights.items()}
        await self._redis.hset(f"user_weights:{user_id}", mapping=str_weights)

    async def update_topic_weight(
        self, user_id: str, topic: str, delta: float
    ) -> float:
        """
        Atomically increment/decrement a single topic weight.
        Returns the new weight value. Clamps to [WEIGHT_MIN, WEIGHT_MAX].
        """
        if not self._redis:
            return 1.0
        key = f"user_weights:{user_id}"
        current = await self._redis.hget(key, topic)
        current_val = float(current) if current else 1.0
        new_val = max(
            settings.WEIGHT_MIN,
            min(settings.WEIGHT_MAX, current_val + delta),
        )
        await self._redis.hset(key, topic, str(new_val))
        return new_val

    # ── Recommendation Cache ────────────────────────────────────

    async def cache_recommendations(
        self, user_id: str, ranked_list: list[dict], ttl: int = None
    ):
        """
        Cache a user's ranked recommendation list.
        TTL defaults to SIMILARITY_CACHE_TTL from settings.
        Invalidated when re-ranking fires.
        """
        if not self._redis:
            return
        ttl = ttl or settings.SIMILARITY_CACHE_TTL
        await self._redis.setex(
            f"recommendations:{user_id}",
            ttl,
            json.dumps(ranked_list),
        )

    async def get_cached_recommendations(self, user_id: str) -> Optional[list[dict]]:
        """Retrieve cached recommendations. Returns None on cache miss."""
        if not self._redis:
            return None
        raw = await self._redis.get(f"recommendations:{user_id}")
        return json.loads(raw) if raw else None

    async def invalidate_recommendations(self, user_id: str):
        """Delete cached recommendations (called before re-ranking)."""
        if not self._redis:
            return
        await self._redis.delete(f"recommendations:{user_id}")

    # ── General Cache ───────────────────────────────────────────

    async def set_cache(self, key: str, value: str, ttl: int = 3600):
        """Generic cache set with TTL."""
        if not self._redis:
            return
        await self._redis.setex(key, ttl, value)

    async def get_cache(self, key: str) -> Optional[str]:
        """Generic cache get."""
        if not self._redis:
            return None
        return await self._redis.get(key)


# Singleton instance
redis_client = RedisClient()
