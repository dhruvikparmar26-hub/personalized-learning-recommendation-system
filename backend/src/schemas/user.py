"""Pydantic schemas for user-related requests and responses."""

# FIX [VALIDATION] — use EmailStr for proper email format validation
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    """Schema for creating a new user."""
    # FIX [VALIDATION] — email was a bare str, accepting any value including XSS payloads
    email: EmailStr = Field(..., description="User's email address")
    name: str = Field(..., min_length=1, max_length=255)
    skill_tags: List[str] = Field(default_factory=list)
    goal: Optional[str] = Field(default=None, max_length=500)
    experience_level: Optional[str] = Field(default=None, max_length=50)
    weekly_hours: int = Field(default=5, ge=1, le=40)


class UserResponse(BaseModel):
    """Schema for user data in API responses."""
    id: str
    email: str
    name: str
    skill_tags: List[str]
    goal: Optional[str]
    experience_level: Optional[str]
    weekly_hours: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Schema for updating user profile."""
    # FIX [VALIDATION] — add constraints to prevent empty/oversized values
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    skill_tags: Optional[List[str]] = None
    goal: Optional[str] = Field(default=None, max_length=500)
    experience_level: Optional[str] = Field(default=None, max_length=50)
    weekly_hours: Optional[int] = Field(default=None, ge=1, le=40)

