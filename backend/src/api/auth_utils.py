"""
Authentication utilities: password hashing and JWT token creation.

Uses settings from config for JWT secret/algorithm to stay consistent
with the middleware auth module.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from jose import jwt

from src.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_byte_enc = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password_byte_enc)


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token using settings from config."""
    to_encode = data.copy()
    # FIX [DEPRECATION] — use timezone-aware UTC instead of deprecated utcnow()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    # FIX [SECURITY] — use settings.JWT_SECRET instead of hardcoded key
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt
