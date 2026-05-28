"""
Seed courses from CSV into PostgreSQL database.

Usage:
    cd backend
    python -m scripts.seed_courses
"""

import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from src.db.database import AsyncSessionLocal, init_db
from src.db.models import Course
from scripts.precompute import load_coursera_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed():
    """Load courses from CSV and insert into database."""
    await init_db()

    df = load_coursera_csv()
    logger.info(f"Seeding {len(df)} courses...")

    async with AsyncSessionLocal() as session:
        for _, row in df.iterrows():
            # Check if already exists
            existing = await session.execute(
                select(Course).where(Course.id == row["id"])
            )
            if existing.scalar_one_or_none():
                continue

            course = Course(
                id=row["id"],
                name=row.get("name", ""),
                university=row.get("university"),
                difficulty=row.get("difficulty"),
                rating=float(row.get("rating", 0)),
                num_reviews=int(row.get("num_reviews", 0)),
                description=row.get("description"),
                skills=row.get("skills"),
                url=row.get("url"),
            )
            session.add(course)

        await session.commit()
        logger.info("Seeding complete!")


if __name__ == "__main__":
    asyncio.run(seed())
