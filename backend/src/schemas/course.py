"""Pydantic schemas for course-related requests and responses."""

from pydantic import BaseModel, Field
from typing import Optional


class CourseResponse(BaseModel):
    """Schema for course data in API responses."""
    id: str
    name: str
    university: Optional[str]
    difficulty: Optional[str]
    rating: float
    num_reviews: int
    description: Optional[str]
    skills: Optional[str]
    url: Optional[str]
    certificate_type: Optional[str]

    model_config = {"from_attributes": True}


class CourseCreate(BaseModel):
    """Schema for creating a course (used in seeding)."""
    name: str = Field(..., max_length=500)
    university: Optional[str] = None
    difficulty: Optional[str] = None
    rating: float = Field(default=0.0, ge=0.0, le=5.0)
    num_reviews: int = Field(default=0, ge=0)
    description: Optional[str] = None
    skills: Optional[str] = None
    url: Optional[str] = None
    certificate_type: Optional[str] = None
