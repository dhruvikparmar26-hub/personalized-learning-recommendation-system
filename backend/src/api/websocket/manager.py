"""
WebSocket connection manager.

Tracks active connections per user. When re-ranking fires,
pushes the updated recommendation list to that user's open connections.

This is essential for a real product — without it, there's no way
to push server-initiated updates to specific users.
"""

import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket and SSE connections per user.
    
    Usage:
        manager = ConnectionManager()
        await manager.connect("user123", websocket)
        await manager.send_to_user("user123", {"type": "recommendation_update", ...})
        manager.disconnect("user123", websocket)
    """

    def __init__(self):
        # WebSocket connections: {user_id: [websocket1, websocket2, ...]}
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # SSE callback functions: {user_id: [callback1, callback2, ...]}
        self.sse_callbacks: Dict[str, List] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """Accept and register a WebSocket connection for a user."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(
            f"WebSocket connected: {user_id} "
            f"(total: {len(self.active_connections[user_id])})"
        )

    def disconnect(self, user_id: str, websocket: WebSocket):
        """Remove a WebSocket connection for a user."""
        if user_id in self.active_connections:
            self.active_connections[user_id] = [
                ws for ws in self.active_connections[user_id] if ws != websocket
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket disconnected: {user_id}")

    def register_sse(self, user_id: str, callback):
        """Register an SSE callback for recommendation updates."""
        if user_id not in self.sse_callbacks:
            self.sse_callbacks[user_id] = []
        self.sse_callbacks[user_id].append(callback)

    def unregister_sse(self, user_id: str, callback):
        """Remove an SSE callback."""
        if user_id in self.sse_callbacks:
            self.sse_callbacks[user_id] = [
                cb for cb in self.sse_callbacks[user_id] if cb != callback
            ]
            if not self.sse_callbacks[user_id]:
                del self.sse_callbacks[user_id]

    async def send_to_user(self, user_id: str, data: dict):
        """Send data to all of a user's WebSocket connections."""
        if user_id not in self.active_connections:
            return

        dead = []
        for ws in self.active_connections[user_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(user_id, ws)

    async def send_recommendations(self, user_id: str, recommendations: list):
        """Push updated recommendations to a user via WebSocket and SSE."""
        payload = {
            "type": "recommendation_update",
            "recommendations": recommendations,
        }

        # WebSocket push
        await self.send_to_user(user_id, payload)

        # SSE callbacks
        if user_id in self.sse_callbacks:
            dead = []
            for callback in self.sse_callbacks[user_id]:
                try:
                    await callback(recommendations)
                except Exception:
                    dead.append(callback)
            for cb in dead:
                self.unregister_sse(user_id, cb)

    async def broadcast(self, data: dict):
        """Send data to all connected users."""
        for user_id in list(self.active_connections.keys()):
            await self.send_to_user(user_id, data)

    @property
    def connection_count(self) -> int:
        """Total number of active WebSocket connections."""
        return sum(len(conns) for conns in self.active_connections.values())

    @property
    def user_count(self) -> int:
        """Number of users with active connections."""
        return len(self.active_connections)


# Singleton
connection_manager = ConnectionManager()
