"""
Comprehensive test suite for the Personalized Learning Recommendation System.

Covers:
    - Basic: Health check, schema validation, config loading
    - Intermediate: Scoring engine, cold start, recommender logic
    - Advanced: API endpoints, auth flow, re-ranking, edge cases
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes import recommendations
from src.api.routes.recommendations import _get_course_skills
from src.config import settings
from src.engine.scorer import (
    compute_final_score,
    compute_recency_factor,
    compute_weight_delta,
    clamp_weight,
)
from src.engine.cold_start import (
    get_onboarding_questions,
    extract_tags_from_answers,
)
from src.engine.recommender import ContentRecommender
from src.schemas.user import UserCreate, UserUpdate, UserResponse
from src.schemas.feedback import FeedbackCreate, FeedbackResponse
from src.schemas.course import CourseResponse, CourseCreate
from src.schemas.recommendation import (
    OnboardingAnswer,
    OnboardingRequest,
    OnboardingResponse,
    RecommendationItem,
    RecommendationResponse,
)
from src.ai.context import build_chat_context, build_explanation_context
from src.api.auth_utils import get_password_hash, verify_password, create_access_token


# ═══════════════════════════════════════════════════════════════
# BASIC TESTS — Core infrastructure and sanity checks
# ═══════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    """Test the /api/health endpoint."""

    def test_health_returns_200(self):
        with TestClient(app) as client:
            response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_returns_expected_fields(self):
        with TestClient(app) as client:
            response = client.get("/api/health")
        body = response.json()
        assert body["status"] == "healthy"
        assert "redis" in body
        assert "model_loaded" in body
        assert "active_connections" in body
        assert "active_users" in body


class TestConfig:
    """Test configuration loading and defaults."""

    def test_default_values(self):
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.JWT_EXPIRATION_MINUTES == 1440
        assert settings.APP_PORT == 8000
        assert settings.RECOMMENDATION_TOP_N == 10
        assert settings.TFIDF_MAX_FEATURES == 5000

    def test_cors_origins_parsed_as_list(self):
        origins = settings.cors_origins_list
        assert isinstance(origins, list)
        assert len(origins) >= 1

    def test_weight_bounds(self):
        assert settings.WEIGHT_MIN < settings.WEIGHT_MAX
        assert settings.WEIGHT_MIN > 0
        assert settings.WEIGHT_LIKE_INCREMENT > 0
        assert settings.WEIGHT_SKIP_DECREMENT > 0
        assert settings.WEIGHT_COMPLETE_INCREMENT > 0
        assert settings.WEIGHT_SAVE_INCREMENT > 0


# ═══════════════════════════════════════════════════════════════
# SCHEMA VALIDATION TESTS — Pydantic model validation
# ═══════════════════════════════════════════════════════════════


class TestUserSchemas:
    """Test user Pydantic schemas."""

    def test_user_create_valid(self):
        user = UserCreate(
            email="test@example.com",
            name="Test User",
            skill_tags=["python", "ml"],
            goal="Learn ML",
            experience_level="Intermediate",
            weekly_hours=10,
        )
        assert user.email == "test@example.com"
        assert user.name == "Test User"
        assert len(user.skill_tags) == 2

    def test_user_create_invalid_email(self):
        with pytest.raises(Exception):
            UserCreate(email="not-an-email", name="Test", password="pass123")

    def test_user_create_defaults(self):
        user = UserCreate(email="test@example.com", name="Test User")
        assert user.skill_tags == []
        assert user.goal is None
        assert user.weekly_hours == 5

    def test_user_update_partial(self):
        update = UserUpdate(name="New Name")
        data = update.model_dump(exclude_unset=True)
        assert "name" in data
        assert "email" not in data

    def test_user_update_empty(self):
        update = UserUpdate()
        data = update.model_dump(exclude_unset=True)
        assert len(data) == 0

    def test_user_create_weekly_hours_bounds(self):
        # Too low
        with pytest.raises(Exception):
            UserCreate(email="test@example.com", name="Test", weekly_hours=0)
        # Too high
        with pytest.raises(Exception):
            UserCreate(email="test@example.com", name="Test", weekly_hours=50)


class TestFeedbackSchemas:
    """Test feedback Pydantic schemas."""

    def test_feedback_create_valid(self):
        fb = FeedbackCreate(
            user_id="user-1",
            course_id="course-1",
            action="like",
        )
        assert fb.action == "like"

    def test_feedback_create_invalid_action(self):
        with pytest.raises(Exception):
            FeedbackCreate(
                user_id="user-1",
                course_id="course-1",
                action="invalid_action",
            )

    def test_feedback_create_all_actions(self):
        for action in ["like", "skip", "save", "complete"]:
            fb = FeedbackCreate(
                user_id="u1", course_id="c1", action=action
            )
            assert fb.action == action


class TestCourseSchemas:
    """Test course Pydantic schemas."""

    def test_course_create_valid(self):
        course = CourseCreate(
            name="Python for Beginners",
            rating=4.5,
            num_reviews=1000,
        )
        assert course.name == "Python for Beginners"
        assert course.rating == 4.5

    def test_course_create_rating_bounds(self):
        with pytest.raises(Exception):
            CourseCreate(name="Test", rating=6.0)
        with pytest.raises(Exception):
            CourseCreate(name="Test", rating=-1.0)


class TestRecommendationSchemas:
    """Test recommendation Pydantic schemas."""

    def test_recommendation_item(self):
        item = RecommendationItem(
            course_id="c1",
            course_name="Test Course",
            university="MIT",
            difficulty="Beginner",
            rating=4.5,
            skills="python, ml",
            url="https://example.com",
            similarity_score=0.85,
            topic_weight=1.2,
            recency_factor=0.95,
            final_score=0.97,
        )
        assert item.course_id == "c1"
        assert item.final_score == 0.97

    def test_onboarding_answer(self):
        answer = OnboardingAnswer(
            question_id=1,
            answer="Python",
            skill_tags=["python", "programming"],
        )
        assert answer.question_id == 1

    def test_onboarding_request(self):
        req = OnboardingRequest(
            user_id="u1",
            answers=[
                OnboardingAnswer(question_id=1, answer="Python"),
            ],
        )
        assert req.user_id == "u1"
        assert len(req.answers) == 1


# ═══════════════════════════════════════════════════════════════
# SCORING ENGINE TESTS — Core recommendation math
# ═══════════════════════════════════════════════════════════════


class TestScoringEngine:
    """Test the scoring module formulas."""

    def test_compute_final_score_basic(self):
        score = compute_final_score(0.8, 1.5, 0.9)
        assert round(score, 4) == round(0.8 * 1.5 * 0.9, 4)

    def test_compute_final_score_zero_similarity(self):
        score = compute_final_score(0.0, 1.5, 0.9)
        assert score == 0.0

    def test_compute_final_score_all_ones(self):
        score = compute_final_score(1.0, 1.0, 1.0)
        assert score == 1.0

    def test_compute_final_score_max_weight(self):
        score = compute_final_score(1.0, 3.0, 1.0)
        assert score == 3.0

    def test_recency_factor_none(self):
        """No interaction → full recency (1.0)."""
        assert compute_recency_factor(None) == 1.0

    def test_recency_factor_today(self):
        """Interaction just now → recency ≈ 1.0."""
        now = datetime.now(timezone.utc)
        factor = compute_recency_factor(now)
        assert factor > 0.99

    def test_recency_factor_decays(self):
        """Older interactions should have lower recency."""
        now = datetime.now(timezone.utc)
        recent = compute_recency_factor(now - timedelta(days=1))
        old = compute_recency_factor(now - timedelta(days=30))
        assert recent > old

    def test_recency_factor_10_days(self):
        """10 days ago → recency ≈ 0.5."""
        past = datetime.now(timezone.utc) - timedelta(days=10)
        factor = compute_recency_factor(past)
        assert abs(factor - 0.5) < 0.05

    def test_weight_delta_like(self):
        delta = compute_weight_delta("like")
        assert delta == settings.WEIGHT_LIKE_INCREMENT

    def test_weight_delta_skip(self):
        delta = compute_weight_delta("skip")
        assert delta == -settings.WEIGHT_SKIP_DECREMENT

    def test_weight_delta_complete(self):
        delta = compute_weight_delta("complete")
        assert delta == settings.WEIGHT_COMPLETE_INCREMENT

    def test_weight_delta_save(self):
        delta = compute_weight_delta("save")
        assert delta == settings.WEIGHT_SAVE_INCREMENT

    def test_weight_delta_unknown_action(self):
        delta = compute_weight_delta("unknown")
        assert delta == 0.0

    def test_clamp_weight_within_bounds(self):
        assert clamp_weight(1.5) == 1.5

    def test_clamp_weight_too_low(self):
        assert clamp_weight(-1.0) == settings.WEIGHT_MIN

    def test_clamp_weight_too_high(self):
        assert clamp_weight(10.0) == settings.WEIGHT_MAX


# ═══════════════════════════════════════════════════════════════
# COLD START TESTS — Onboarding quiz and bootstrapping
# ═══════════════════════════════════════════════════════════════


class TestColdStart:
    """Test cold start / onboarding logic."""

    def test_get_onboarding_questions_returns_list(self):
        questions = get_onboarding_questions()
        assert isinstance(questions, list)
        assert len(questions) >= 4

    def test_onboarding_questions_have_required_fields(self):
        questions = get_onboarding_questions()
        for q in questions:
            assert "question_id" in q
            assert "question_text" in q
            assert "options" in q
            assert "skill_tags_map" in q
            assert len(q["options"]) >= 2

    def test_extract_tags_from_valid_answers(self):
        answers = [
            {"question_id": 2, "answer": "Data Science & ML"},
            {"question_id": 5, "answer": "Python"},
        ]
        tags = extract_tags_from_answers(answers)
        assert "python" in tags
        assert "data science" in tags

    def test_extract_tags_from_empty_answers(self):
        tags = extract_tags_from_answers([])
        assert tags == []

    def test_extract_tags_from_invalid_answer(self):
        answers = [{"question_id": 1, "answer": "Nonexistent Option"}]
        tags = extract_tags_from_answers(answers)
        assert tags == []

    def test_extract_tags_all_questions(self):
        """Ensure every option in every question maps to tags."""
        questions = get_onboarding_questions()
        for q in questions:
            for option in q["options"]:
                assert option in q["skill_tags_map"], (
                    f"Option '{option}' in question {q['question_id']} "
                    f"has no mapping in skill_tags_map"
                )
                tags = q["skill_tags_map"][option]
                assert len(tags) > 0, (
                    f"Option '{option}' maps to empty tags list"
                )


# ═══════════════════════════════════════════════════════════════
# RECOMMENDER ENGINE TESTS — TF-IDF and re-ranking
# ═══════════════════════════════════════════════════════════════


class TestRecommenderEngine:
    """Test the ContentRecommender class."""

    @pytest.fixture
    def sample_courses_df(self):
        """Create a minimal courses DataFrame for testing."""
        return pd.DataFrame([
            {
                "id": "c1",
                "name": "Python Programming",
                "description": "Learn Python programming language basics",
                "skills": "python, programming, beginner",
                "university": "MIT",
                "difficulty": "Beginner",
                "rating": 4.8,
                "url": "https://example.com/python",
            },
            {
                "id": "c2",
                "name": "Machine Learning Fundamentals",
                "description": "Introduction to machine learning with Python",
                "skills": "machine learning, python, statistics, data science",
                "university": "Stanford",
                "difficulty": "Intermediate",
                "rating": 4.7,
                "url": "https://example.com/ml",
            },
            {
                "id": "c3",
                "name": "Web Development with JavaScript",
                "description": "Build modern web applications with JavaScript and React",
                "skills": "javascript, react, html, css, web development",
                "university": "Coursera",
                "difficulty": "Beginner",
                "rating": 4.5,
                "url": "https://example.com/web",
            },
            {
                "id": "c4",
                "name": "Data Structures and Algorithms",
                "description": "Core computer science data structures and algorithms",
                "skills": "algorithms, data structures, programming, computer science",
                "university": "Princeton",
                "difficulty": "Intermediate",
                "rating": 4.9,
                "url": "https://example.com/dsa",
            },
            {
                "id": "c5",
                "name": "Deep Learning Specialization",
                "description": "Neural networks deep learning AI TensorFlow",
                "skills": "deep learning, neural networks, tensorflow, ai",
                "university": "Stanford",
                "difficulty": "Advanced",
                "rating": 4.6,
                "url": "https://example.com/dl",
            },
        ])

    @pytest.fixture
    def fitted_recommender(self, sample_courses_df):
        """Create a fitted recommender for testing."""
        rec = ContentRecommender()
        rec.fit(sample_courses_df)
        return rec

    def test_fit_sets_is_fitted(self, fitted_recommender):
        assert fitted_recommender._is_fitted is True

    def test_fit_builds_index_mappings(self, fitted_recommender):
        assert "c1" in fitted_recommender.course_id_to_idx
        assert 0 in fitted_recommender.idx_to_course_id

    def test_fit_creates_combined_text(self, fitted_recommender):
        assert "combined_text" in fitted_recommender.courses_df.columns

    def test_recommend_for_user_basic(self, fitted_recommender):
        recs = fitted_recommender.recommend_for_user(
            user_tags=["python", "machine learning"],
            top_n=3,
        )
        assert len(recs) <= 3
        assert all("course_id" in r for r in recs)
        assert all("similarity_score" in r for r in recs)
        assert all("final_score" in r for r in recs)

    def test_recommend_for_user_excludes_courses(self, fitted_recommender):
        recs = fitted_recommender.recommend_for_user(
            user_tags=["python"],
            top_n=5,
            exclude_ids={"c1"},
        )
        course_ids = {r["course_id"] for r in recs}
        assert "c1" not in course_ids

    def test_recommend_for_user_scores_sorted(self, fitted_recommender):
        recs = fitted_recommender.recommend_for_user(
            user_tags=["python", "programming"],
            top_n=5,
        )
        scores = [r["final_score"] for r in recs]
        assert scores == sorted(scores, reverse=True)

    def test_get_similar_basic(self, fitted_recommender):
        similar = fitted_recommender.get_similar("c1", top_n=3)
        assert len(similar) <= 3
        assert all("similarity_score" in s for s in similar)
        # Should not include itself
        assert all(s["course_id"] != "c1" for s in similar)

    def test_get_similar_unknown_course(self, fitted_recommender):
        similar = fitted_recommender.get_similar("nonexistent", top_n=3)
        assert similar == []

    def test_re_rank_basic(self, fitted_recommender):
        base_recs = fitted_recommender.recommend_for_user(
            user_tags=["python"], top_n=5,
        )
        re_ranked = fitted_recommender.re_rank(
            current_list=base_recs,
            topic_weights={"python": 2.0, "javascript": 0.5},
        )
        assert len(re_ranked) == len(base_recs)
        assert all("final_score" in r for r in re_ranked)

    def test_re_rank_changes_order(self, fitted_recommender):
        """Re-ranking with extreme weights should change ordering."""
        base_recs = fitted_recommender.recommend_for_user(
            user_tags=["python", "javascript"], top_n=5,
        )
        # Strongly favor javascript over python
        re_ranked = fitted_recommender.re_rank(
            current_list=base_recs,
            topic_weights={"javascript": 3.0, "python": 0.1},
        )
        # Verify final_scores are sorted descending
        scores = [r["final_score"] for r in re_ranked]
        assert scores == sorted(scores, reverse=True)

    def test_re_rank_with_recency(self, fitted_recommender):
        base_recs = fitted_recommender.recommend_for_user(
            user_tags=["python"], top_n=3,
        )
        re_ranked = fitted_recommender.re_rank(
            current_list=base_recs,
            topic_weights={"python": 1.5},
            interaction_times={"python": datetime.now(timezone.utc)},
        )
        assert len(re_ranked) == len(base_recs)

    def test_not_fitted_raises_error(self):
        rec = ContentRecommender()
        with pytest.raises(RuntimeError, match="not fitted"):
            rec.recommend_for_user(user_tags=["python"])

    def test_extract_skills(self, fitted_recommender):
        skills = fitted_recommender._extract_skills(
            {"skills": "Python, ML, Statistics"}
        )
        assert skills == ["python", "ml", "statistics"]

    def test_extract_skills_empty(self, fitted_recommender):
        assert fitted_recommender._extract_skills({}) == []
        assert fitted_recommender._extract_skills({"skills": ""}) == []
        assert fitted_recommender._extract_skills({"skills": None}) == []


# ═══════════════════════════════════════════════════════════════
# AUTHENTICATION TESTS — Password hashing, JWT tokens
# ═══════════════════════════════════════════════════════════════


class TestAuthentication:
    """Test password hashing and JWT token operations."""

    def test_password_hash_and_verify(self):
        password = "SecureP@ssw0rd!"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_password_wrong_verify(self):
        hashed = get_password_hash("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_create_access_token(self):
        token = create_access_token(data={"sub": "user-123"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_with_custom_expiry(self):
        token = create_access_token(
            data={"sub": "user-123"},
            expires_delta=timedelta(hours=1),
        )
        assert isinstance(token, str)

    def test_different_passwords_different_hashes(self):
        h1 = get_password_hash("password1")
        h2 = get_password_hash("password2")
        assert h1 != h2


# ═══════════════════════════════════════════════════════════════
# AI CONTEXT TESTS — System prompt construction
# ═══════════════════════════════════════════════════════════════


class TestAIContext:
    """Test context building for Claude AI."""

    def test_build_chat_context_minimal(self):
        context = build_chat_context(user_id="u1")
        assert "learning assistant" in context.lower()

    def test_build_chat_context_with_profile(self):
        context = build_chat_context(
            user_id="u1",
            user_profile={
                "name": "Alice",
                "skill_tags": ["python", "ml"],
                "goal": "Become a data scientist",
                "experience_level": "Intermediate",
                "weekly_hours": 10,
            },
        )
        assert "Alice" in context
        assert "python" in context
        assert "data scientist" in context

    def test_build_chat_context_with_weights(self):
        context = build_chat_context(
            user_id="u1",
            topic_weights={"python": 2.0, "javascript": 0.5},
        )
        assert "python" in context.lower()

    def test_build_chat_context_with_recommendations(self):
        context = build_chat_context(
            user_id="u1",
            recommendations=[
                {
                    "course_name": "Python 101",
                    "final_score": 0.95,
                    "skills": "python",
                    "difficulty": "Beginner",
                    "rating": 4.8,
                },
            ],
        )
        assert "Python 101" in context

    def test_build_explanation_context(self):
        context = build_explanation_context(
            user_profile={"skill_tags": ["python"], "goal": "ML career"},
            topic_weights={"python": 1.5, "ml": 1.3},
        )
        assert "python" in context.lower()
        assert "ML career" in context

    def test_build_explanation_context_empty(self):
        context = build_explanation_context()
        assert "learning advisor" in context.lower()


# ═══════════════════════════════════════════════════════════════
# API ENDPOINT TESTS — HTTP routes
# ═══════════════════════════════════════════════════════════════


class TestAPIEndpoints:
    """Test REST API endpoints."""

    def test_root_returns_404_without_frontend(self):
        """Root path returns 404 when FRONTEND_DIST_PATH is not configured (API-only mode)."""
        with TestClient(app) as client:
            response = client.get("/", follow_redirects=False)
        # Backend doesn't serve root in API-only mode — frontend handles it
        assert response.status_code == 404

    def test_onboarding_questions_endpoint(self):
        with TestClient(app) as client:
            response = client.get("/api/onboarding/questions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 4

    def test_register_user(self):
        """Test user registration flow."""
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/register",
                json={
                    "name": "Test User",
                    "email": f"test-{uuid.uuid4().hex[:8]}@example.com",
                    "password": "StrongP@ss123",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data
        assert data["user"]["name"] == "Test User"

    def test_register_duplicate_email_fails(self):
        """Registering the same email twice should fail."""
        email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(app) as client:
            # First registration
            client.post(
                "/api/auth/register",
                json={"name": "User1", "email": email, "password": "Pass123!"},
            )
            # Second registration with same email
            response = client.post(
                "/api/auth/register",
                json={"name": "User2", "email": email, "password": "Pass456!"},
            )
        assert response.status_code == 400

    def test_login_success(self):
        """Test login with correct credentials."""
        email = f"login-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(app) as client:
            # Register first
            client.post(
                "/api/auth/register",
                json={"name": "LoginUser", "email": email, "password": "MyP@ss123"},
            )
            # Login
            response = client.post(
                "/api/auth/login",
                json={"email": email, "password": "MyP@ss123"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    def test_login_wrong_password(self):
        """Test login with wrong password."""
        email = f"wrongpw-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(app) as client:
            client.post(
                "/api/auth/register",
                json={"name": "User", "email": email, "password": "CorrectPass123"},
            )
            response = client.post(
                "/api/auth/login",
                json={"email": email, "password": "WrongPass123"},
            )
        assert response.status_code == 401

    def test_login_nonexistent_user(self):
        """Test login with non-existent email."""
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login",
                json={"email": "nobody@example.com", "password": "pass"},
            )
        assert response.status_code == 401

    def test_create_user_legacy_endpoint(self):
        """Test the legacy /api/users POST endpoint."""
        with TestClient(app) as client:
            response = client.post(
                "/api/users",
                json={
                    "email": f"legacy-{uuid.uuid4().hex[:8]}@example.com",
                    "name": "Legacy User",
                    "skill_tags": ["python"],
                    "weekly_hours": 5,
                },
            )
        # Should succeed (may use fallback if DB is SQLite)
        assert response.status_code == 200


class TestCourseSkillsHelper:
    """Test _get_course_skills helper function."""

    def test_returns_empty_when_not_fitted(self, monkeypatch):
        monkeypatch.setattr(recommendations.recommender, "_is_fitted", False)
        assert _get_course_skills("course-1") == []

    def test_returns_empty_for_unknown_course(self, monkeypatch):
        monkeypatch.setattr(recommendations.recommender, "_is_fitted", True)
        monkeypatch.setattr(recommendations.recommender, "course_id_to_idx", {})
        assert _get_course_skills("unknown-course") == []

    def test_parses_skills_correctly(self, monkeypatch):
        monkeypatch.setattr(recommendations.recommender, "_is_fitted", True)
        monkeypatch.setattr(
            recommendations.recommender,
            "course_id_to_idx",
            {"course-1": 0},
        )
        monkeypatch.setattr(
            recommendations.recommender,
            "courses_df",
            pd.DataFrame([{"skills": "Python, SQL, Statistics"}]),
        )
        assert _get_course_skills("course-1") == ["python", "sql", "statistics"]

    def test_handles_empty_skills(self, monkeypatch):
        monkeypatch.setattr(recommendations.recommender, "_is_fitted", True)
        monkeypatch.setattr(
            recommendations.recommender,
            "course_id_to_idx",
            {"course-1": 0},
        )
        monkeypatch.setattr(
            recommendations.recommender,
            "courses_df",
            pd.DataFrame([{"skills": ""}]),
        )
        assert _get_course_skills("course-1") == []

    def test_handles_none_skills(self, monkeypatch):
        monkeypatch.setattr(recommendations.recommender, "_is_fitted", True)
        monkeypatch.setattr(
            recommendations.recommender,
            "course_id_to_idx",
            {"course-1": 0},
        )
        monkeypatch.setattr(
            recommendations.recommender,
            "courses_df",
            pd.DataFrame([{"skills": None}]),
        )
        assert _get_course_skills("course-1") == []


# ═══════════════════════════════════════════════════════════════
# ADVANCED / EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_recommender_empty_tags(self):
        """Recommender with empty tags should return empty results."""
        rec = ContentRecommender()
        df = pd.DataFrame([
            {"id": "c1", "name": "Test", "description": "test course", "skills": "python"},
        ])
        rec.fit(df)
        recs = rec.recommend_for_user(user_tags=[], top_n=5)
        # Empty tags result in empty query, should return empty or low-score results
        assert isinstance(recs, list)

    def test_recommender_single_course(self):
        """Recommender should handle single course dataset."""
        rec = ContentRecommender()
        df = pd.DataFrame([
            {"id": "c1", "name": "Python", "description": "python programming", "skills": "python"},
        ])
        rec.fit(df)
        recs = rec.recommend_for_user(user_tags=["python"], top_n=1)
        assert len(recs) <= 1

    def test_re_rank_empty_list(self):
        """Re-ranking empty list should return empty."""
        rec = ContentRecommender()
        df = pd.DataFrame([
            {"id": "c1", "name": "Test", "description": "test", "skills": "python"},
        ])
        rec.fit(df)
        result = rec.re_rank([], topic_weights={"python": 1.5})
        assert result == []

    def test_re_rank_empty_weights(self):
        """Re-ranking with no weights should preserve order."""
        rec = ContentRecommender()
        df = pd.DataFrame([
            {"id": "c1", "name": "Python", "description": "python programming", "skills": "python"},
            {"id": "c2", "name": "JavaScript", "description": "javascript web", "skills": "javascript"},
        ])
        rec.fit(df)
        base = rec.recommend_for_user(user_tags=["python"], top_n=2)
        re_ranked = rec.re_rank(base, topic_weights={})
        assert len(re_ranked) == len(base)

    def test_compute_final_score_all_zeros(self):
        assert compute_final_score(0.0, 0.0, 0.0) == 0.0

    def test_compute_recency_very_old(self):
        """Very old interaction should have very low recency."""
        past = datetime.now(timezone.utc) - timedelta(days=365)
        factor = compute_recency_factor(past)
        assert factor < 0.05

    def test_weight_delta_view_action(self):
        """View action should return 0 delta (not in deltas map)."""
        assert compute_weight_delta("view") == 0.0


class TestWebSocketManager:
    """Test the ConnectionManager without actual WebSocket connections."""

    def test_initial_state(self):
        from src.api.websocket.manager import ConnectionManager
        mgr = ConnectionManager()
        assert mgr.connection_count == 0
        assert mgr.user_count == 0

    def test_disconnect_nonexistent_user(self):
        from src.api.websocket.manager import ConnectionManager
        mgr = ConnectionManager()
        # Should not raise
        mgr.disconnect("nonexistent", MagicMock())
        assert mgr.user_count == 0


class TestEventHandling:
    """Test event handling helpers without Redis."""

    def test_get_course_skills_from_events(self):
        from src.engine.events import _get_course_skills as ev_skills
        # When not fitted, should return empty
        assert ev_skills("any-course") == []


# ═══════════════════════════════════════════════════════════════
# INTEGRATION-STYLE TESTS — Full auth + onboarding flow
# ═══════════════════════════════════════════════════════════════


class TestFullUserFlow:
    """Test a complete user journey: register → login → create profile."""

    def test_register_then_login_flow(self):
        email = f"flow-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(app) as client:
            # 1. Register
            reg_resp = client.post(
                "/api/auth/register",
                json={"name": "Flow User", "email": email, "password": "FlowP@ss1"},
            )
            assert reg_resp.status_code == 200
            reg_data = reg_resp.json()
            token = reg_data["access_token"]
            user_id = reg_data["user"]["id"]

            # 2. Login
            login_resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "FlowP@ss1"},
            )
            assert login_resp.status_code == 200
            assert "access_token" in login_resp.json()

            # 3. Health check (no auth needed)
            health_resp = client.get("/api/health")
            assert health_resp.status_code == 200

            # 4. Get onboarding questions
            q_resp = client.get("/api/onboarding/questions")
            assert q_resp.status_code == 200
            questions = q_resp.json()
            assert len(questions) >= 4


class TestLearningPathEndpoint:
    """Test learning path endpoint."""

    def test_learning_path_returns_empty_for_new_user(self):
        with TestClient(app) as client:
            response = client.get("/api/learning-path/nonexistent-user")
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["path"] is None
