"""
Pytest configuration and shared fixtures.

Sets up test-specific database (in-memory SQLite) and
ensures tests don't interfere with dev/prod data.
"""

import os

# Force test environment before any imports
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("APP_ENV", "testing")

import pytest
