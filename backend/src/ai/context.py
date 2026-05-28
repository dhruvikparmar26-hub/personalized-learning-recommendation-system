"""
Context injection for Claude AI.

System prompt = user profile + current skills + goals + recommendations.
This grounds Claude's responses to the domain and prevents hallucinating fake courses.
"""


def build_chat_context(
    user_id: str,
    recommendations: list[dict] = None,
    topic_weights: dict[str, float] = None,
    conversation_history: list[dict] = None,
    user_profile: dict = None,
) -> str:
    """
    Build a context-rich system prompt for Claude chat.

    Injects:
        - User profile (skills, goals, experience)
        - Current recommendations with scores
        - Topic weights showing preferences
        - Recent interaction patterns
    """
    parts = ["You are a personalized learning assistant."]

    # User profile context
    if user_profile:
        parts.append("\n## User Profile")
        parts.append(f"- Name: {user_profile.get('name', 'Unknown')}")
        parts.append(f"- Experience: {user_profile.get('experience_level', 'Not specified')}")
        parts.append(f"- Goal: {user_profile.get('goal', 'Not specified')}")
        skills = user_profile.get('skill_tags', [])
        if skills:
            parts.append(f"- Skills: {', '.join(skills)}")
        parts.append(f"- Weekly hours: {user_profile.get('weekly_hours', 5)}")

    # Topic weights (preferences)
    if topic_weights:
        parts.append("\n## User Preferences (topic weights)")
        sorted_weights = sorted(topic_weights.items(), key=lambda x: x[1], reverse=True)
        strong = [f"{t} ({w:.1f})" for t, w in sorted_weights if w > 1.2]
        weak = [f"{t} ({w:.1f})" for t, w in sorted_weights if w < 0.8]
        if strong:
            parts.append(f"- Strong interest: {', '.join(strong)}")
        if weak:
            parts.append(f"- Low interest: {', '.join(weak)}")

    # Current recommendations
    if recommendations:
        parts.append(f"\n## Current Recommendations (top {min(5, len(recommendations))})")
        for r in recommendations[:5]:
            name = r.get("course_name", "Unknown")
            score = r.get("final_score", 0)
            skills = r.get("skills", "N/A")
            diff = r.get("difficulty", "N/A")
            rating = r.get("rating", "N/A")
            parts.append(f"- {name} (Difficulty: {diff}, Rating: {rating}, Match Score: {score:.2f})\n  Skills taught: {skills}")

    parts.append("\n## Instructions")
    parts.append("- Reference specific courses from the recommendations above.")
    parts.append("- Do NOT invent or hallucinate courses that aren't listed.")
    parts.append("- Explain recommendations using the user's profile and preferences.")
    parts.append("- Be concise, friendly, and actionable.")

    return "\n".join(parts)


def build_explanation_context(
    user_profile: dict = None,
    topic_weights: dict[str, float] = None,
) -> str:
    """Build context for recommendation explanations."""
    parts = ["You are a learning advisor explaining course recommendations."]

    if user_profile:
        skills = user_profile.get("skill_tags", [])
        goal = user_profile.get("goal", "general learning")
        parts.append(f"\nUser's skills: {', '.join(skills) if skills else 'not specified'}")
        parts.append(f"User's goal: {goal}")

    if topic_weights:
        sorted_w = sorted(topic_weights.items(), key=lambda x: x[1], reverse=True)
        top = [f"{t}" for t, w in sorted_w[:5] if w > 1.0]
        if top:
            parts.append(f"Topics they've shown interest in: {', '.join(top)}")

    parts.append("\nExplain why each course was selected based on their profile.")
    parts.append("Be specific — reference their skills, goals, and preferences.")
    return "\n".join(parts)
