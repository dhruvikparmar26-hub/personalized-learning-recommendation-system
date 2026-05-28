"""
SQLAlchemy ORM models for the learning recommendation system.

Tables:
    - users: User profiles with skill tags and goals
    - courses: Course catalog (loaded from Coursera dataset)
    - interactions: Every user action (like, skip, save, complete) — drives re-ranking
    - onboarding_responses: Quiz answers for cold start bootstrapping
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Text,
    Float,
    Integer,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import enum

from src.db.database import Base


def _uuid_type():
    """Use native UUID on PostgreSQL and a portable string elsewhere."""
    return String(36).with_variant(UUID(as_uuid=False), "postgresql")


def _skill_tags_type():
    """Store tag lists portably across SQLite and PostgreSQL."""
    return JSON().with_variant(ARRAY(String), "postgresql")


# ── Enums ───────────────────────────────────────────────────────

class InteractionType(str, enum.Enum):
    """Types of user interactions with courses."""
    LIKE = "like"
    SKIP = "skip"
    SAVE = "save"
    COMPLETE = "complete"
    VIEW = "view"


class DifficultyLevel(str, enum.Enum):
    """Course difficulty levels."""
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"
    MIXED = "Mixed"


# ── Users ───────────────────────────────────────────────────────

class User(Base):
    """
    User profile. Stores skill tags from onboarding quiz,
    learning goals, and current course enrollments.
    Updated live as users interact.
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        _uuid_type(),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    skill_tags: Mapped[list] = mapped_column(
        _skill_tags_type(),
        default=list,
    )
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weekly_hours: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    onboarding_responses: Mapped[list["OnboardingResponse"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User {self.name} ({self.email})>"


# ── Courses ─────────────────────────────────────────────────────

class Course(Base):
    """
    Course catalog entry. Loaded from Coursera dataset.
    TF-IDF vectors are computed from description + skills fields.
    """
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(
        _uuid_type(),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(500), index=True)
    university: Mapped[str | None] = mapped_column(String(255), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    num_reviews: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certificate_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    interactions: Mapped[list["Interaction"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Course {self.name[:50]}>"


# ── Interactions ────────────────────────────────────────────────

class Interaction(Base):
    """
    Every user action on a course. This is the heartbeat of real-time re-ranking.
    Each like, skip, save, or complete triggers a Redis event that updates
    topic weights and re-ranks the user's recommendation list.
    
    Schema designed for high-frequency writes — this table grows fast.
    """
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(
        _uuid_type(),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        _uuid_type(),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    course_id: Mapped[str] = mapped_column(
        _uuid_type(),
        ForeignKey("courses.id", ondelete="CASCADE"),
        index=True,
    )
    action: Mapped[str] = mapped_column(
        SAEnum(InteractionType, name="interaction_type", create_constraint=True),
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="interactions")
    course: Mapped["Course"] = relationship(back_populates="interactions")

    def __repr__(self):
        return f"<Interaction {self.user_id} → {self.action} → {self.course_id}>"


# ── Onboarding Responses ───────────────────────────────────────

class OnboardingResponse(Base):
    """
    Stores each answer from the onboarding quiz.
    Used for cold start: when a user has zero interactions,
    these responses bootstrap the initial recommendation set.
    
    Each answer maps to skill tags that become the user's
    initial topic weights.
    """
    __tablename__ = "onboarding_responses"

    id: Mapped[str] = mapped_column(
        _uuid_type(),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        _uuid_type(),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    question_id: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    skill_tags: Mapped[list] = mapped_column(
        _skill_tags_type(),
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="onboarding_responses")

    def __repr__(self):
        return f"<OnboardingResponse Q{self.question_id}: {self.answer[:30]}>"
