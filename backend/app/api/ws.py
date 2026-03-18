"""WebSocket endpoint for broadcasting live updates to frontend."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    _instance: ConnectionManager | None = None

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    @classmethod
    def get_instance(cls) -> ConnectionManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to all connected clients."""
        data = json.dumps(event, default=str)
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


@router.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    manager = ConnectionManager.get_instance()
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; we push data via broadcast()
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
