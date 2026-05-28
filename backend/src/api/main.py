"""
FastAPI application entry point.

Lifespan handles:
    - Database initialization
    - Redis connection
    - TF-IDF model loading
    - Redis event listener startup
    - Graceful shutdown of all connections
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import Depends, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.config import settings
from src.api.routes import auth, feedback, learning_path, onboarding, recommendations, stream
from src.api.websocket.chat import websocket_chat_endpoint
from src.api.websocket.manager import connection_manager
from src.db.database import init_db, close_db
from src.db.database import get_db
from src.db.models import User
from src.db.redis_client import redis_client
from src.schemas.user import UserCreate, UserUpdate, UserResponse
from src.engine.recommender import recommender
from src.engine.events import start_event_listener, stop_event_listener, set_connection_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Startup:
        1. Initialize database tables
        2. Connect to Redis
        3. Load pre-computed TF-IDF model
        4. Inject connection manager into event listener
        5. Start Redis event listener as background task

    Shutdown:
        1. Stop event listener
        2. Close Redis
        3. Close database connections
    """
    logger.info("Starting application...")

    # 1. Database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database init skipped: {e}")

    # 2. Redis
    try:
        await redis_client.connect()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis connection skipped: {e}")

    # 3. Load TF-IDF model
    try:
        model_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "processed"
        )
        if os.path.exists(os.path.join(model_path, "tfidf_vectorizer.pkl")):
            recommender.load(model_path)
            logger.info("TF-IDF model loaded")
        else:
            # Try loading courses_df.pkl alone (fallback text model)
            courses_pkl = os.path.join(model_path, "courses_df.pkl")
            if os.path.exists(courses_pkl):
                recommender.load(model_path)
                logger.info("TF-IDF model loaded (fallback mode)")
            else:
                logger.warning(
                    "No pre-computed model found at data/processed/. "
                    "Run 'python -m scripts.precompute' first."
                )
    except Exception as e:
        logger.warning(f"Model loading skipped: {e}")

    # 4. Inject connection manager
    set_connection_manager(connection_manager)

    # 5. Start event listener
    event_task = None
    try:
        event_task = asyncio.create_task(start_event_listener())
        logger.info("Event listener started")
    except Exception as e:
        logger.warning(f"Event listener skipped: {e}")

    logger.info(f"Application ready — {settings.APP_ENV} mode")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await stop_event_listener()
    if event_task:
        event_task.cancel()
    try:
        await redis_client.disconnect()
    except Exception:
        pass
    await close_db()
    logger.info("Shutdown complete")


# ── App ─────────────────────────────────────────────────────────

app = FastAPI(
    title="Personalized Learning Recommendation System",
    description=(
        "Real-time course recommendations with TF-IDF content filtering, "
        "live re-ranking, Claude AI streaming, WebSocket chat, and SSE updates."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── REST Routes ─────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(recommendations.router)
app.include_router(feedback.router)
app.include_router(stream.router)
app.include_router(learning_path.router)

# ── WebSocket Route ─────────────────────────────────────────────

@app.websocket("/api/chat/{user_id}")
async def chat_websocket(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for AI chat assistant."""
    await websocket_chat_endpoint(websocket, user_id)


# ── Health Check ────────────────────────────────────────────────
@app.get("/api/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    redis_ok = False
    try:
        await redis_client.client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "healthy",
        "redis": "connected" if redis_ok else "disconnected",
        "model_loaded": recommender._is_fitted,
        "active_connections": connection_manager.connection_count,
        "active_users": connection_manager.user_count,
    }


# ── User Registration (simplified) ─────────────────────────────

@app.post("/api/users", response_model=UserResponse, tags=["users"])
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user."""
    try:
        user = User(
            email=user_data.email,
            name=user_data.name,
            skill_tags=user_data.skill_tags,
            goal=user_data.goal,
            experience_level=user_data.experience_level,
            weekly_hours=user_data.weekly_hours,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    except Exception as exc:
        await db.rollback()
        logger.warning(f"User creation DB error (using fallback): {exc}")
        # Graceful fallback for local development when DB is unavailable.
        # Return a synthetic user so the frontend onboarding flow can proceed.
        fake_id = f"dev-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        return UserResponse(
            id=fake_id,
            email=user_data.email,
            name=user_data.name,
            skill_tags=user_data.skill_tags or [],
            goal=user_data.goal,
            experience_level=user_data.experience_level,
            weekly_hours=user_data.weekly_hours,
            created_at=datetime.now(timezone.utc),
        )


# ── User Update ────────────────────────────────────────────────

@app.patch("/api/users/{user_id}", response_model=UserResponse, tags=["users"])
async def update_user(
    user_id: str,
    updates: UserUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a user's profile (goal, skills, etc.)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    user.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(user)
        return user
    except Exception as exc:
        await db.rollback()
        logger.error(f"Failed to update user {user_id}: {exc}")
        raise HTTPException(status_code=500, detail="Database error during update")


# ── Serve Frontend Static Files (Production) ───────────────────

if settings.FRONTEND_DIST_PATH and os.path.isdir(settings.FRONTEND_DIST_PATH):
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """Serve the frontend SPA — catch-all for client-side routing."""
        # FIX [SECURITY] — prevent path traversal attacks (e.g. ../../etc/passwd)
        # Resolve to canonical path and verify it's within the dist directory
        file_path = os.path.realpath(os.path.join(settings.FRONTEND_DIST_PATH, full_path))
        dist_root = os.path.realpath(settings.FRONTEND_DIST_PATH)
        if not file_path.startswith(dist_root):
            return FileResponse(os.path.join(settings.FRONTEND_DIST_PATH, "index.html"))
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Fall back to index.html for SPA routing
        return FileResponse(os.path.join(settings.FRONTEND_DIST_PATH, "index.html"))

    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(settings.FRONTEND_DIST_PATH, "assets")),
        name="static",
    )
    logger.info(f"Serving frontend from: {settings.FRONTEND_DIST_PATH}")

