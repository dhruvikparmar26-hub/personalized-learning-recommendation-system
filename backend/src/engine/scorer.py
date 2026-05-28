"""
Scoring module for the recommendation engine.

Score Formula:
    final_score = similarity_score × topic_weight × recency_factor

This is the core formula that drives all recommendations. Each component:

    similarity_score (float, 0 to 1):
        Cosine similarity from TF-IDF vectors between user profile and course.
        Higher = more textually similar to user's interests.
        Computed once during pre-processing, cached in Redis.

    topic_weight (float, 0.1 to 3.0):
        Dynamic weight per topic, adjusted by user feedback:
            - like    → +0.2 (user wants more of this)
            - skip    → -0.3 (user rejects this topic)
            - save    → +0.15 (mild interest)
            - complete → +0.5 (strong positive signal)
        Starts at 1.0, clamped to [0.1, 3.0].
        Stored in Redis hash, updated atomically.

    recency_factor (float, 0 to 1):
        Time decay — newer interactions weight more.
        Formula: 1 / (1 + days_since_last_interaction × 0.1)
        A course interacted with today → recency ≈ 1.0
        A course from 10 days ago → recency ≈ 0.5
        A course from 30 days ago → recency ≈ 0.25

Why re-ranking instead of retraining?
    Full model retraining (re-fitting TF-IDF) takes minutes.
    Re-ranking a scored list (multiply three floats, sort) takes milliseconds.
    For real-time UX, re-ranking is the correct engineering choice.
"""

# FIX [DEPRECATION] — datetime.utcnow() is deprecated in Python 3.12+
from datetime import datetime, timezone
from src.config import settings


def compute_final_score(
    similarity_score: float,
    topic_weight: float,
    recency_factor: float,
) -> float:
    """
    Compute the final recommendation score.

    Args:
        similarity_score: Cosine similarity [0, 1] from TF-IDF
        topic_weight: User feedback weight [0.1, 3.0]
        recency_factor: Time decay [0, 1]

    Returns:
        final_score: Product of all three factors
    """
    return similarity_score * topic_weight * recency_factor


def compute_recency_factor(
    last_interaction: datetime = None,
    decay_rate: float = 0.1,
) -> float:
    """
    Compute time decay factor for a course.

    If no interaction exists (cold start), returns 1.0.
    Formula: 1 / (1 + days_since × decay_rate)

    Args:
        last_interaction: Timestamp of last user interaction with this topic
        decay_rate: How fast the score decays (default 0.1)

    Returns:
        recency_factor between 0 and 1
    """
    if last_interaction is None:
        return 1.0

    # FIX [DEPRECATION] — use timezone-aware UTC
    days_since = (datetime.now(timezone.utc) - last_interaction).total_seconds() / 86400
    return 1.0 / (1.0 + days_since * decay_rate)


def compute_weight_delta(action: str) -> float:
    """
    Get the weight adjustment for a given user action.

    Args:
        action: One of 'like', 'skip', 'save', 'complete'

    Returns:
        Delta to apply to topic weight (positive or negative)
    """
    deltas = {
        "like": settings.WEIGHT_LIKE_INCREMENT,       # +0.2
        "skip": -settings.WEIGHT_SKIP_DECREMENT,      # -0.3
        "save": settings.WEIGHT_SAVE_INCREMENT,        # +0.15
        "complete": settings.WEIGHT_COMPLETE_INCREMENT, # +0.5
    }
    return deltas.get(action, 0.0)


def clamp_weight(weight: float) -> float:
    """Clamp a topic weight to the configured [min, max] range."""
    return max(settings.WEIGHT_MIN, min(settings.WEIGHT_MAX, weight))
