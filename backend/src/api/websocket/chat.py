"""
WebSocket chat endpoint with Claude streaming.

ws://api/chat/{user_id} — persistent connection for AI chat assistant.
Messages flow both ways without polling.

Flow:
    1. Client connects via WebSocket
    2. Client sends message: {"message": "Why was Python recommended?"}
    3. Server injects context (profile + recommendations + history)
    4. Server calls Claude with streaming
    5. Tokens stream back over WebSocket as they arrive
    6. Client renders typewriter effect
"""

import json
import logging
import asyncio
import random
from fastapi import WebSocket, WebSocketDisconnect

from src.api.websocket.manager import connection_manager
from src.ai.assistant import stream_chat_response
from src.ai.context import build_chat_context
from src.db.redis_client import redis_client

logger = logging.getLogger(__name__)

async def broadcast_live_events(websocket: WebSocket):
    """Periodically broadcasts fake 'live events' to the client to make the platform feel alive."""
    events = [
        "🔥 14 students are currently viewing 'Python for Everybody'",
        "✨ A user just completed 'UI / UX Design Specialization'",
        "📈 'Machine Learning' is trending in your region today",
        "🎉 Someone just enrolled in 'iOS App Development with Swift'",
        "💡 3 new peers joined the 'Game Development' community",
    ]
    try:
        while True:
            await asyncio.sleep(random.randint(15, 30))
            event_msg = random.choice(events)
            await websocket.send_json({
                "type": "live_event",
                "message": event_msg
            })
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Live event broadcast error: {e}")


async def websocket_chat_endpoint(websocket: WebSocket, user_id: str):
    """
    Handle a WebSocket chat session for a user.
    
    Protocol:
        Client -> Server: {"message": "user text", "history": [...]}
        Server -> Client: {"type": "token", "content": "word"}
        Server -> Client: {"type": "done", "full_response": "..."}
        Server -> Client: {"type": "error", "message": "..."}
    """
    await connection_manager.connect(user_id, websocket)

    # Start background event broadcaster
    live_event_task = asyncio.create_task(broadcast_live_events(websocket))

    try:
        while True:
            # Receive message from client
            raw = await websocket.receive_text()

            # FIX [SECURITY] — limit message size to prevent DoS via massive payloads
            if len(raw) > 10_000:
                await websocket.send_json({
                    "type": "error",
                    "message": "Message too long (max 10KB)"
                })
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })
                continue

            user_message = data.get("message", "")
            history = data.get("history", [])

            if not user_message.strip():
                await websocket.send_json({
                    "type": "error",
                    "message": "Empty message"
                })
                continue

            # Build context with user profile and recommendations
            try:
                cached_recs = await redis_client.get_cached_recommendations(user_id)
            except Exception:
                cached_recs = []

            try:
                user_weights = await redis_client.get_user_weights(user_id)
            except Exception:
                user_weights = {}

            context = build_chat_context(
                user_id=user_id,
                recommendations=cached_recs or [],
                topic_weights=user_weights,
                conversation_history=history,
            )

            # Stream Claude response token by token
            full_response = ""
            try:
                async for token in stream_chat_response(
                    system_prompt=context,
                    user_message=user_message,
                    history=history,
                ):
                    full_response += token
                    await websocket.send_json({
                        "type": "token",
                        "content": token,
                    })

                await websocket.send_json({
                    "type": "done",
                    "full_response": full_response,
                })
            except Exception as e:
                logger.error(f"Claude streaming error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "AI assistant temporarily unavailable",
                })

    except WebSocketDisconnect:
        live_event_task.cancel()
        connection_manager.disconnect(user_id, websocket)
        logger.info(f"Chat WebSocket disconnected: {user_id}")
    except Exception as e:
        live_event_task.cancel()
        logger.error(f"WebSocket error for {user_id}: {e}")
        connection_manager.disconnect(user_id, websocket)
