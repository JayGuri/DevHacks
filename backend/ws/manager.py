# backend/ws/manager.py — WebSocket connection manager for frontend clients
"""
Manages WebSocket connections from the React frontend.
Each connection subscribes to a specific project's training events.

Events pushed to clients:
  - round_complete:    RoundMetrics + Node[] + GanttBlock[]
  - node_flagged:      Byzantine detection alert
  - training_status:   running / paused / completed / error
  - notification:      Real-time notification push
"""

import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger("arfl.ws")


class ConnectionManager:
    """Manages WebSocket connections grouped by project_id."""

    def __init__(self):
        # { project_id: set of WebSocket connections }
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, project_id: str) -> None:
        """Accept and register a WebSocket connection for a project."""
        await websocket.accept()
        async with self._lock:
            if project_id not in self._connections:
                self._connections[project_id] = set()
            self._connections[project_id].add(websocket)
        logger.info("WS connected: project=%s, total=%d", project_id, len(self._connections.get(project_id, set())))

    async def disconnect(self, websocket: WebSocket, project_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if project_id in self._connections:
                self._connections[project_id].discard(websocket)
                if not self._connections[project_id]:
                    del self._connections[project_id]
        logger.info("WS disconnected: project=%s", project_id)

    async def broadcast(self, project_id: str, event: str, data: dict) -> None:
        """Send an event to all connected clients for a project."""
        message = json.dumps({"event": event, "projectId": project_id, "data": data})
        connections = self._connections.get(project_id, set()).copy()
        if not connections:
            return

        dead = []
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.get(project_id, set()).discard(ws)

    async def send_personal(self, websocket: WebSocket, event: str, data: dict) -> None:
        """Send an event to a single WebSocket."""
        try:
            await websocket.send_text(json.dumps({"event": event, "data": data}))
        except Exception as e:
            logger.warning("Failed to send personal WS message: %s", e)

    def get_connection_count(self, project_id: str) -> int:
        """Return the number of active connections for a project."""
        return len(self._connections.get(project_id, set()))


# Singleton instance
ws_manager = ConnectionManager()
