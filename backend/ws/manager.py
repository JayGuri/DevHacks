# backend/ws/manager.py — WebSocket connection manager for frontend + FL clients
"""
Manages two classes of WebSocket connections:

  1. Frontend dashboard clients — subscribe to project training events.
     Events pushed:
       - round_complete:    RoundMetrics + Node[] + GanttBlock[]
       - node_flagged:      Byzantine detection alert
       - training_status:   running / paused / completed / error
       - trust_report:      Per-client trust scores + rejected lists (every round)
       - global_model:      Aggregated model weights broadcast (every round)

  2. FL training clients — send weight updates, receive model + reports.
     Events pushed:
       - global_model:      Aggregated weights after each round
       - trust_report:      Trust/staleness/rejection metadata
       - rejected:          Directed to the offending client (Layer 1 gatekeeper)
     Events received:
       - weight_update:     Local training result with base64-encoded weights
"""

import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger("arfl.ws")

# Hard limit on concurrent FL training clients per project (one per data chunk)
MAX_FL_CLIENTS = 10


class ConnectionManager:
    """Manages WebSocket connections grouped by project_id.

    Tracks two independent sets per project:
      _connections  — frontend/dashboard clients (receive broadcasts)
      _fl_clients   — FL training clients (bidirectional, capped at MAX_FL_CLIENTS)
    """

    def __init__(self):
        # { project_id: set of WebSocket connections } — dashboard viewers
        self._connections: Dict[str, Set[WebSocket]] = {}
        # { project_id: { client_id: WebSocket } } — FL training participants
        self._fl_clients: Dict[str, Dict[str, WebSocket]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Dashboard / broadcast connections
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket, project_id: str) -> None:
        """Accept and register a WebSocket connection for a project."""
        await websocket.accept()
        async with self._lock:
            if project_id not in self._connections:
                self._connections[project_id] = set()
            self._connections[project_id].add(websocket)
        logger.info(
            "WS connected: project=%s total=%d",
            project_id, len(self._connections.get(project_id, set())),
        )

    async def disconnect(self, websocket: WebSocket, project_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if project_id in self._connections:
                self._connections[project_id].discard(websocket)
                if not self._connections[project_id]:
                    del self._connections[project_id]
        logger.info("WS disconnected: project=%s", project_id)

    async def broadcast(self, project_id: str, event: str, data: dict) -> None:
        """Send an event to all connected dashboard clients for a project."""
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

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.get(project_id, set()).discard(ws)

    async def send_personal(self, websocket: WebSocket, event: str, data: dict) -> None:
        """Send an event to a single WebSocket."""
        try:
            await websocket.send_text(json.dumps({"event": event, "data": data}))
        except Exception as exc:
            logger.warning("send_personal failed: %s", exc)

    def get_connection_count(self, project_id: str) -> int:
        """Return the number of active dashboard connections for a project."""
        return len(self._connections.get(project_id, set()))

    # ------------------------------------------------------------------
    # FL training client connections
    # ------------------------------------------------------------------

    async def register_fl_client(
        self, client_id: str, project_id: str, websocket: WebSocket
    ) -> bool:
        """Register an FL training client.

        Returns False if the per-project client limit (MAX_FL_CLIENTS) is reached,
        in which case the caller should close the connection with code 1008.
        """
        async with self._lock:
            if project_id not in self._fl_clients:
                self._fl_clients[project_id] = {}
            if len(self._fl_clients[project_id]) >= MAX_FL_CLIENTS:
                logger.warning(
                    "FL client limit reached: project=%s limit=%d client=%s",
                    project_id, MAX_FL_CLIENTS, client_id,
                )
                return False
            self._fl_clients[project_id][client_id] = websocket
        logger.info(
            "FL client registered: project=%s client=%s total=%d",
            project_id, client_id, len(self._fl_clients.get(project_id, {})),
        )
        return True

    async def unregister_fl_client(self, client_id: str, project_id: str) -> None:
        """Remove an FL training client connection."""
        async with self._lock:
            if project_id in self._fl_clients:
                self._fl_clients[project_id].pop(client_id, None)
                if not self._fl_clients[project_id]:
                    del self._fl_clients[project_id]
        logger.info("FL client unregistered: project=%s client=%s", project_id, client_id)

    async def send_to_fl_client(
        self, client_id: str, project_id: str, data: dict
    ) -> bool:
        """Send a directed message to a specific FL client.

        Returns True on success, False if the client is not found or send fails.
        Used to deliver `rejected` messages directly to the offending client.
        """
        ws = self._fl_clients.get(project_id, {}).get(client_id)
        if not ws:
            return False
        try:
            await ws.send_text(json.dumps(data))
            return True
        except Exception as exc:
            logger.warning(
                "send_to_fl_client failed: project=%s client=%s err=%s",
                project_id, client_id, exc,
            )
            return False

    def get_fl_client_count(self, project_id: str) -> int:
        """Return the number of active FL client connections for a project."""
        return len(self._fl_clients.get(project_id, {}))


# Singleton instance used across the application
ws_manager = ConnectionManager()
