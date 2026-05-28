"""
Claude AI streaming integration.

Three core functions:
    1. stream_chat_response — WebSocket chat, tokens streamed back
    2. stream_explanation — SSE explanation of recommendations
    3. generate_learning_path — streaming 30-day plan

All use AsyncAnthropic with client.messages.stream() for non-blocking streaming.
"""

import logging
import os
from typing import AsyncGenerator

import anthropic

from src.config import settings

logger = logging.getLogger(__name__)

# Load prompt templates
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "prompts")


def _load_prompt(filename: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"Prompt file not found: {path}")
        return ""


def _get_client() -> anthropic.AsyncAnthropic:
    """Get async Anthropic client. Returns None if no API key."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    return anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def stream_chat_response(
    system_prompt: str,
    user_message: str,
    history: list[dict] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream a chat response from Claude.

    Args:
        system_prompt: Context-injected system prompt
        user_message: The user's message
        history: Previous conversation messages

    Yields:
        Text tokens as they arrive from Claude
    """
    client = _get_client()
    if not client:
        yield "AI assistant is not configured. Please set ANTHROPIC_API_KEY."
        return

    messages = []
    if history:
        for msg in history[-10:]:  # Last 10 messages for context
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
    messages.append({"role": "user", "content": user_message})

    chat_system = _load_prompt("chat_system.txt")
    full_system = f"{chat_system}\n\n{system_prompt}" if chat_system else system_prompt

    try:
        async with client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            system=full_system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        yield "I'm having trouble connecting right now. Please try again."
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield "An unexpected error occurred."


async def stream_explanation(
    system_prompt: str,
    recommendations: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Stream an explanation of why courses were recommended.

    Args:
        system_prompt: Context with user profile
        recommendations: Current recommendation list

    Yields:
        Explanation tokens
    """
    client = _get_client()
    if not client:
        yield "AI explanations require ANTHROPIC_API_KEY configuration."
        return

    explanation_prompt = _load_prompt("explanation.txt")
    recs_text = "\n".join(
        f"- {r.get('course_name', 'Unknown')} (score: {r.get('final_score', 0):.2f}, "
        f"skills: {r.get('skills', 'N/A')})"
        for r in recommendations[:5]
    )

    user_content = f"{explanation_prompt}\n\nCurrent recommendations:\n{recs_text}"

    try:
        async with client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        logger.error(f"Explanation streaming error: {e}")
        yield "Unable to generate explanation right now."


async def generate_learning_path(
    system_prompt: str,
    top_courses: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Stream a 30-day learning path from Claude.

    Args:
        system_prompt: Context with user profile and goals
        top_courses: Courses to sequence into a path

    Yields:
        Learning path text tokens
    """
    client = _get_client()
    if not client:
        yield "Learning path generation requires ANTHROPIC_API_KEY."
        return

    path_prompt = _load_prompt("learning_path.txt")
    courses_text = "\n".join(
        f"- {c.get('course_name', 'Unknown')} ({c.get('difficulty', 'N/A')}, "
        f"rating: {c.get('rating', 0)}/5)"
        for c in top_courses[:8]
    )

    user_content = f"{path_prompt}\n\nAvailable courses:\n{courses_text}"

    try:
        async with client.messages.stream(
            model=settings.CLAUDE_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        logger.error(f"Learning path generation error: {e}")
        yield "Unable to generate learning path right now."
