"""
Cold start handling for new users.

Decision tree:
    1. User has quiz data -> use quiz tags as pseudo-profile
    2. No quiz data -> fall back to default tags
    3. No data at all -> return popularity-weighted courses
"""

import logging
from src.engine.recommender import recommender

logger = logging.getLogger(__name__)

ONBOARDING_QUESTIONS = [
    {
        "question_id": 1,
        "question_text": "What's your current experience level?",
        "options": ["Complete Beginner", "Some Experience", "Intermediate", "Advanced"],
        "skill_tags_map": {
            "Complete Beginner": ["beginner", "fundamentals", "introduction"],
            "Some Experience": ["intermediate", "practical"],
            "Intermediate": ["intermediate", "applied", "project-based"],
            "Advanced": ["advanced", "specialized", "research"],
        },
    },
    {
        "question_id": 2,
        "question_text": "Which area interests you the most?",
        "options": ["Data Science & ML", "Web Development", "Mobile App Development", "UI/UX Design", "Game Development", "Finance & Blockchain", "Business & Management", "Computer Science Fundamentals", "Cloud & DevOps"],
        "skill_tags_map": {
            "Data Science & ML": ["data science", "machine learning", "python", "statistics"],
            "Web Development": ["web development", "javascript", "html", "css", "react"],
            "Mobile App Development": ["mobile", "ios", "android", "swift", "react native"],
            "UI/UX Design": ["design", "ui", "ux", "figma", "user experience"],
            "Game Development": ["game development", "unity", "c#", "unreal engine"],
            "Finance & Blockchain": ["finance", "blockchain", "crypto", "smart contracts", "fintech"],
            "Business & Management": ["business", "management", "leadership", "strategy"],
            "Computer Science Fundamentals": ["algorithms", "data structures", "programming", "computer science"],
            "Cloud & DevOps": ["cloud computing", "aws", "docker", "devops", "kubernetes"],
        },
    },
    {
        "question_id": 3,
        "question_text": "What's your primary learning goal?",
        "options": ["Career change", "Skill upgrade for current role", "Academic learning", "Personal interest / hobby"],
        "skill_tags_map": {
            "Career change": ["career", "professional", "certification"],
            "Skill upgrade for current role": ["professional development", "applied"],
            "Academic learning": ["theory", "research", "academic"],
            "Personal interest / hobby": ["exploration", "creative", "self-paced"],
        },
    },
    {
        "question_id": 4,
        "question_text": "How much time can you dedicate per week?",
        "options": ["1-3 hours", "3-5 hours", "5-10 hours", "10+ hours"],
        "skill_tags_map": {
            "1-3 hours": ["short", "micro-learning"],
            "3-5 hours": ["moderate", "structured"],
            "5-10 hours": ["intensive", "comprehensive"],
            "10+ hours": ["full-time", "immersive", "bootcamp"],
        },
    },
    {
        "question_id": 5,
        "question_text": "Which specific skills do you want to learn?",
        "options": ["Python", "SQL & Databases", "Machine Learning", "JavaScript / React", "Swift / iOS", "Figma / Design", "Unity / C#", "Blockchain / Crypto", "Data Analysis", "Project Management"],
        "skill_tags_map": {
            "Python": ["python", "programming", "automation"],
            "SQL & Databases": ["sql", "database", "data management"],
            "Machine Learning": ["machine learning", "deep learning", "neural networks", "ai"],
            "JavaScript / React": ["javascript", "react", "frontend", "web development"],
            "Swift / iOS": ["swift", "ios", "mobile", "app development"],
            "Figma / Design": ["figma", "design", "ui", "ux"],
            "Unity / C#": ["unity", "c#", "game development"],
            "Blockchain / Crypto": ["blockchain", "crypto", "solidity", "web3"],
            "Data Analysis": ["data analysis", "visualization", "pandas", "excel"],
            "Project Management": ["project management", "agile", "scrum", "leadership"],
        },
    },
]

DEFAULT_FALLBACK_TAGS = ["programming", "data science", "beginner", "python"]


def get_onboarding_questions() -> list[dict]:
    return ONBOARDING_QUESTIONS


def extract_tags_from_answers(answers: list[dict]) -> list[str]:
    tags = set()
    questions_map = {q["question_id"]: q for q in ONBOARDING_QUESTIONS}
    for ans in answers:
        q_id = ans.get("question_id")
        answer = ans.get("answer")
        question = questions_map.get(q_id)
        if question and answer in question["skill_tags_map"]:
            tags.update(question["skill_tags_map"][answer])
    return list(tags)


def generate_cold_start_recommendations(
    user_tags: list[str] = None,
    exclude_ids: set[str] = None,
    top_n: int = 10,
) -> tuple[list[dict], bool]:
    if user_tags and len(user_tags) > 0:
        effective_tags = user_tags
    else:
        effective_tags = DEFAULT_FALLBACK_TAGS

    try:
        recommendations = recommender.recommend_for_user(
            user_tags=effective_tags, top_n=top_n, exclude_ids=exclude_ids,
        )
    except RuntimeError:
        logger.error("Recommender not fitted during cold start")
        recommendations = []

    return recommendations, True
