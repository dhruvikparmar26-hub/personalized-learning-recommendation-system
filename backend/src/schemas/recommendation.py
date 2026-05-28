"""Pydantic schemas for recommendation responses and onboarding."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RecommendationItem(BaseModel):
    """A single recommended course with its scoring breakdown."""
    course_id: str
    course_name: str
    university: Optional[str]
    difficulty: Optional[str]
    rating: float
    skills: Optional[str]
    url: Optional[str]

    # Scoring breakdown — transparent and explainable
    similarity_score: float = Field(
        ..., description="Cosine similarity from TF-IDF [0, 1]"
    )
    topic_weight: float = Field(
        ..., description="Adjusted by user feedback [0.1, 3.0]"
    )
    recency_factor: float = Field(
        ..., description="Time decay factor [0, 1]"
    )
    final_score: float = Field(
        ..., description="similarity × topic_weight × recency"
    )


class RecommendationResponse(BaseModel):
    """Full recommendation response with ranked list and metadata."""
    user_id: str
    recommendations: List[RecommendationItem]
    is_cold_start: bool = Field(
        default=False,
        description="True if using onboarding quiz tags (no interactions yet)",
    )
    generated_at: datetime
    source: str = Field(
        default="live_ranked",
        description="'cold_start', 'cached', or 'live_ranked'",
    )


class OnboardingQuestion(BaseModel):
    """A single onboarding quiz question."""
    question_id: int
    question_text: str
    options: List[str]
    skill_tags_map: dict = Field(
        ...,
        description="Maps each option to skill tags. E.g., {'Python': ['python', 'programming']}"
    )


class OnboardingAnswer(BaseModel):
    """A single quiz answer from the user."""
    question_id: int
    answer: str
    skill_tags: List[str] = Field(
        default_factory=list,
        description="Derived skill tags from the selected answer",
    )


class OnboardingRequest(BaseModel):
    """Full onboarding submission."""
    user_id: str
    answers: List[OnboardingAnswer]


class OnboardingResponse(BaseModel):
    """Response after processing onboarding quiz."""
    user_id: str
    skill_tags: List[str]
    initial_recommendations: List[RecommendationItem]
    message: str = "Onboarding complete. Your personalized recommendations are ready."
