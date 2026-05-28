"""Pydantic schemas for feedback/interaction requests."""

from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


class FeedbackCreate(BaseModel):
    """
    Schema for submitting user feedback on a course.
    
    Actions and their effects on topic weights:
        - like: +0.2 to course topics (user wants more like this)
        - skip: -0.3 to course topics (user doesn't want this)
        - save: +0.15 to course topics (interested but not now)
        - complete: +0.5 to course topics (strong positive signal)
    """
    user_id: str = Field(..., description="ID of the user giving feedback")
    course_id: str = Field(..., description="ID of the course being rated")
    action: Literal["like", "skip", "save", "complete"] = Field(
        ..., description="Type of feedback action"
    )


class FeedbackResponse(BaseModel):
    """Response after recording feedback."""
    id: str
    user_id: str
    course_id: str
    action: str
    timestamp: datetime
    message: str = "Feedback recorded. Recommendations will update in real-time."

    model_config = {"from_attributes": True}


class InteractionResponse(BaseModel):
    """Schema for interaction history entries."""
    id: str
    user_id: str
    course_id: str
    action: str
    timestamp: datetime

    model_config = {"from_attributes": True}
