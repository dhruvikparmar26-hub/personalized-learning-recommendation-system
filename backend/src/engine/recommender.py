"""
Content-based recommendation engine using TF-IDF and cosine similarity.

Architecture:
    1. Pre-compute: Fit TF-IDF on all course descriptions + skills → similarity matrix
    2. Recommend: For a user profile, find most similar courses
    3. Re-rank: Apply topic weights and recency to re-order recommendations in real-time

Why TF-IDF?
    - Fast and explainable
    - Works without interaction history (perfect for cold start)
    - Pre-computation means recommendations are sub-millisecond lookups
    - The "first-session recommender" — works from the moment a user signs up

Why re-ranking instead of retraining?
    - Retraining the TF-IDF model takes minutes (re-fitting vectorizer)
    - Re-ranking = multiply three floats and sort = milliseconds
    - For real-time UX, this is the correct engineering choice
"""

import pandas as pd
import joblib
import os
import logging
import re
from typing import Optional
from datetime import datetime

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover - optional dependency in local test env
    TfidfVectorizer = None
    cosine_similarity = None

from src.config import settings
from src.engine.scorer import compute_final_score, compute_recency_factor

logger = logging.getLogger(__name__)


class ContentRecommender:
    """
    Content-based recommendation engine.
    
    Usage:
        recommender = ContentRecommender()
        recommender.fit(courses_df)  # Once, during pre-computation
        
        # Get similar courses
        similar = recommender.get_similar("course_id_123", top_n=10)
        
        # Get recommendations for a user profile
        recs = recommender.recommend_for_user(
            user_tags=["python", "machine learning"],
            top_n=10
        )
        
        # Re-rank with feedback weights (real-time)
        re_ranked = recommender.re_rank(
            current_list=recs,
            topic_weights={"python": 1.4, "statistics": 0.7},
            interaction_times={"python": datetime(...)}
        )
    """

    def __init__(self):
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.similarity_matrix = None
        self.courses_df: Optional[pd.DataFrame] = None
        self.course_id_to_idx: dict = {}
        self.idx_to_course_id: dict = {}
        self._fallback_mode = False
        self._fallback_tokens: list[set[str]] = []
        self._is_fitted = False

    def fit(self, courses_df: pd.DataFrame):
        """
        Fit TF-IDF vectorizer on course catalog.
        
        Args:
            courses_df: DataFrame with columns: id, name, description, skills
                        'description' and 'skills' are combined for vectorization.
        """
        self.courses_df = courses_df.copy()

        # Combine description + skills into a single text field
        self.courses_df["combined_text"] = (
            self.courses_df["description"].fillna("")
            + " "
            + self.courses_df["skills"].fillna("")
            + " "
            + self.courses_df["name"].fillna("")
        ).str.lower().str.strip()

        # Build index mappings
        self.course_id_to_idx = {
            cid: idx for idx, cid in enumerate(self.courses_df["id"])
        }
        self.idx_to_course_id = {
            idx: cid for cid, idx in self.course_id_to_idx.items()
        }

        if TfidfVectorizer is None or cosine_similarity is None:
            self._fallback_mode = True
            self.vectorizer = None
            self.tfidf_matrix = None
            self.similarity_matrix = None
            self._fallback_tokens = [
                self._tokenize_text(text)
                for text in self.courses_df["combined_text"]
            ]
            self._is_fitted = True
            logger.info(f"Fitted fallback text model on {len(courses_df)} courses.")
            return

        # Fit TF-IDF
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=settings.TFIDF_MAX_FEATURES,
            ngram_range=(1, 2),  # Unigrams + bigrams for better matching
            min_df=2,
            max_df=0.95,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(
            self.courses_df["combined_text"]
        )

        # Pre-compute full similarity matrix
        # For Coursera dataset (~3000 courses), this is ~70MB — fits in memory
        self.similarity_matrix = cosine_similarity(self.tfidf_matrix)

        self._is_fitted = True
        logger.info(
            f"Fitted TF-IDF on {len(courses_df)} courses. "
            f"Matrix shape: {self.tfidf_matrix.shape}. "
            f"Vocabulary size: {len(self.vectorizer.vocabulary_)}"
        )

    def get_similar(self, course_id: str, top_n: int = 20) -> list[dict]:
        """
        Get most similar courses to a given course.
        Pure content similarity — no personalization.
        
        Args:
            course_id: ID of the reference course
            top_n: Number of similar courses to return
            
        Returns:
            List of {course_id, similarity_score, ...course_data}
        """
        self._check_fitted()

        if course_id not in self.course_id_to_idx:
            logger.warning(f"Course {course_id} not found in index")
            return []

        idx = self.course_id_to_idx[course_id]
        if self._fallback_mode:
            ref_tokens = self._fallback_tokens[idx]
            sim_scores = [
                (other_idx, self._token_similarity(ref_tokens, tokens))
                for other_idx, tokens in enumerate(self._fallback_tokens)
            ]
        else:
            sim_scores = list(enumerate(self.similarity_matrix[idx]))
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)

        # Skip self (index 0) and take top_n
        results = []
        for other_idx, score in sim_scores[1 : top_n + 1]:
            course_data = self._get_course_data(other_idx)
            course_data["similarity_score"] = round(float(score), 4)
            results.append(course_data)

        return results

    def recommend_for_user(
        self,
        user_tags: list[str],
        top_n: int = None,
        exclude_ids: set[str] = None,
    ) -> list[dict]:
        """
        Generate recommendations based on user skill tags.
        Used for initial recommendations and cold start.
        
        Strategy:
            1. Create a pseudo-document from user's skill tags
            2. Transform it using the fitted vectorizer
            3. Compute similarity against all courses
            4. Return top_n most similar
        
        Args:
            user_tags: List of skill tags from profile/quiz
            top_n: Number of recommendations (default from settings)
            exclude_ids: Course IDs to exclude (already completed/skipped)
            
        Returns:
            List of {course_id, similarity_score, ...course_data}
        """
        self._check_fitted()
        top_n = top_n or settings.RECOMMENDATION_TOP_N
        exclude_ids = exclude_ids or set()

        # Create pseudo-document from tags
        user_text = " ".join(user_tags).lower()
        if self._fallback_mode:
            user_tokens = self._tokenize_text(user_text)
            similarities = [
                self._token_similarity(user_tokens, tokens)
                for tokens in self._fallback_tokens
            ]
        else:
            user_vector = self.vectorizer.transform([user_text])

            # Compute similarity against all courses
            similarities = cosine_similarity(user_vector, self.tfidf_matrix).flatten()

        # Rank and filter
        scored = list(enumerate(similarities))
        scored = sorted(scored, key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scored:
            course_id = self.idx_to_course_id[idx]
            if course_id in exclude_ids:
                continue
            if score <= 0:
                continue

            course_data = self._get_course_data(idx)
            course_data["similarity_score"] = round(float(score), 4)
            course_data["topic_weight"] = 1.0  # Default for new users
            course_data["recency_factor"] = 1.0  # No interactions yet
            course_data["final_score"] = round(float(score), 4)
            results.append(course_data)

            if len(results) >= top_n:
                break

        return results

    def re_rank(
        self,
        current_list: list[dict],
        topic_weights: dict[str, float],
        interaction_times: dict[str, datetime] = None,
    ) -> list[dict]:
        """
        Re-rank a recommendation list using topic weights and recency.
        
        THIS IS THE REAL-TIME OPERATION.
        Called when a user likes/skips a course.
        Takes milliseconds instead of the minutes needed for retraining.
        
        Formula: final_score = similarity_score × topic_weight × recency_factor
        
        Args:
            current_list: Existing recommendation list with similarity scores
            topic_weights: {topic: weight} from user feedback
            interaction_times: {topic: last_interaction_datetime} for recency
            
        Returns:
            Re-ranked list sorted by final_score
        """
        interaction_times = interaction_times or {}
        re_ranked = []

        for item in current_list:
            sim_score = item.get("similarity_score", 0.0)

            # Aggregate topic weight for this course's skills
            course_skills = self._extract_skills(item)
            if course_skills and topic_weights:
                weights = [
                    topic_weights.get(skill, 1.0)
                    for skill in course_skills
                ]
                avg_weight = sum(weights) / len(weights)
            else:
                avg_weight = 1.0

            # Compute recency from most recent interaction with these topics
            recency = 1.0
            if interaction_times:
                times = [
                    interaction_times[skill]
                    for skill in course_skills
                    if skill in interaction_times
                ]
                if times:
                    most_recent = max(times)
                    recency = compute_recency_factor(most_recent)

            # Apply the formula
            final = compute_final_score(sim_score, avg_weight, recency)

            updated_item = item.copy()
            updated_item["topic_weight"] = round(avg_weight, 4)
            updated_item["recency_factor"] = round(recency, 4)
            updated_item["final_score"] = round(final, 4)
            re_ranked.append(updated_item)

        # Sort by final score descending
        re_ranked.sort(key=lambda x: x["final_score"], reverse=True)
        return re_ranked

    def save(self, path: str = "data/processed"):
        """Save fitted model to disk."""
        self._check_fitted()
        os.makedirs(path, exist_ok=True)
        joblib.dump(self.vectorizer, os.path.join(path, "tfidf_vectorizer.pkl"))
        joblib.dump(self.tfidf_matrix, os.path.join(path, "tfidf_matrix.pkl"))
        joblib.dump(self.similarity_matrix, os.path.join(path, "similarity_matrix.pkl"))
        self.courses_df.to_pickle(os.path.join(path, "courses_df.pkl"))
        logger.info(f"Model saved to {path}")

    def load(self, path: str = "data/processed"):
        """Load a previously fitted model from disk."""
        self.courses_df = pd.read_pickle(os.path.join(path, "courses_df.pkl"))

        if TfidfVectorizer is None or cosine_similarity is None:
            self.vectorizer = None
            self.tfidf_matrix = None
            self.similarity_matrix = None
            self._fallback_mode = True
            combined_text = self.courses_df.get("combined_text")
            if combined_text is None:
                combined_text = (
                    self.courses_df["description"].fillna("")
                    + " "
                    + self.courses_df["skills"].fillna("")
                    + " "
                    + self.courses_df["name"].fillna("")
                ).str.lower().str.strip()
            self._fallback_tokens = [
                self._tokenize_text(text) for text in combined_text
            ]
        else:
            self.vectorizer = joblib.load(os.path.join(path, "tfidf_vectorizer.pkl"))
            self.tfidf_matrix = joblib.load(os.path.join(path, "tfidf_matrix.pkl"))
            self.similarity_matrix = joblib.load(os.path.join(path, "similarity_matrix.pkl"))
            self._fallback_mode = False

        self.course_id_to_idx = {
            cid: idx for idx, cid in enumerate(self.courses_df["id"])
        }
        self.idx_to_course_id = {
            idx: cid for cid, idx in self.course_id_to_idx.items()
        }
        self._is_fitted = True
        logger.info(f"Model loaded from {path}. {len(self.courses_df)} courses.")

    # ── Private helpers ─────────────────────────────────────────

    def _check_fitted(self):
        if not self._is_fitted:
            raise RuntimeError(
                "Recommender not fitted. Call fit() or load() first."
            )

    def _get_course_data(self, idx: int) -> dict:
        """Extract course data from DataFrame by index."""
        row = self.courses_df.iloc[idx]
        return {
            "course_id": row["id"],
            "course_name": row["name"],
            "university": row.get("university"),
            "difficulty": row.get("difficulty"),
            "rating": float(row.get("rating", 0)),
            "skills": row.get("skills"),
            "url": row.get("url"),
        }

    def _extract_skills(self, item: dict) -> list[str]:
        """Extract skill tags from a recommendation item."""
        skills_str = item.get("skills", "")
        if not skills_str:
            return []
        return [s.strip().lower() for s in str(skills_str).split(",") if s.strip()]

    def _tokenize_text(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", str(text).lower()))

    def _token_similarity(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        if not intersection:
            return 0.0
        return intersection / ((len(left) * len(right)) ** 0.5)


# Singleton instance — loaded once during app startup
recommender = ContentRecommender()
