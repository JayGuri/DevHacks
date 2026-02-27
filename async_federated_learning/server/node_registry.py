# server/node_registry.py — Dynamic node registry for federated learning
import json
import logging
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

# Ensure repo root is on sys.path for core.jwt_auth
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from core.jwt_auth import create_token as _core_create_token  # noqa: E402

logger = logging.getLogger("fedbuff.node_registry")


class NodeRegistry:
    """Manages dynamic FL node registration with persistent storage.

    Nodes are assigned a sequential node_index per task (0, 1, 2, ...).
    Data is pre-divided into max_nodes_per_task fixed partitions, so each
    node_index maps to a stable, non-overlapping data slice. LEAF user
    ordering provides natural non-IID distribution.
    """

    def __init__(self, registry_file: str, jwt_secret: str = "", max_nodes_per_task: int = 10):
        self.registry_file = registry_file
        # jwt_secret param kept for backward compat; ignored — core.jwt_auth reads env
        self.jwt_secret = jwt_secret
        self.max_nodes_per_task = max_nodes_per_task
        # {node_id: {task, role, display_name, node_index, created_at, attack_type, attack_scale}}
        self._nodes: dict = {}
        # {task: current_count}
        self._task_counts: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(
        self,
        task: str,
        role: str,
        display_name: str,
        attack_type: Optional[str] = None,
        attack_scale: Optional[float] = None,
    ) -> dict:
        """Register a new node and return its credentials.

        Returns:
            {node_id, node_index, total_nodes, token, task, display_name, role}

        Raises:
            ValueError: if the task already has max_nodes_per_task registered.
        """
        current_count = self._task_counts.get(task, 0)
        if current_count >= self.max_nodes_per_task:
            raise ValueError(
                f"Task '{task}' already has {current_count}/{self.max_nodes_per_task} nodes registered. "
                f"Increase MAX_NODES_PER_TASK to add more."
            )

        node_index = current_count
        node_id = f"node-{task[:3]}-{node_index:03d}-{uuid.uuid4().hex[:6]}"

        # Mint JWT via shared core auth
        extra_claims = {
            "display_name": display_name,
            "task": task,
            "node_index": node_index,
            "total_nodes": self.max_nodes_per_task,
        }
        token = _core_create_token(
            sub=node_id,
            role=role,
            extra_claims=extra_claims,
            expiry_hours=30 * 24,  # 30 days
        )

        # Store node info
        node_info = {
            "node_id": node_id,
            "display_name": display_name,
            "role": role,
            "task": task,
            "node_index": node_index,
            "total_nodes": self.max_nodes_per_task,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if attack_type:
            node_info["attack_type"] = attack_type
        if attack_scale is not None:
            node_info["attack_scale"] = attack_scale

        self._nodes[node_id] = node_info
        self._task_counts[task] = node_index + 1
        self._save()

        logger.info(
            "Registered node: %s (task=%s, index=%d/%d, role=%s)",
            node_id, task, node_index, self.max_nodes_per_task, role,
        )

        return {
            "node_id": node_id,
            "display_name": display_name,
            "role": role,
            "task": task,
            "node_index": node_index,
            "total_nodes": self.max_nodes_per_task,
            "token": token,
        }

    def list_nodes(self, task: Optional[str] = None) -> list:
        """Return all registered nodes, optionally filtered by task."""
        nodes = list(self._nodes.values())
        if task:
            nodes = [n for n in nodes if n["task"] == task]
        return nodes

    def get_count(self, task: str) -> int:
        """Return number of registered nodes for a task."""
        return self._task_counts.get(task, 0)

    def remove_node(self, node_id: str) -> bool:
        """Remove a node from the registry. Returns True if found and removed."""
        if node_id not in self._nodes:
            return False
        task = self._nodes[node_id]["task"]
        del self._nodes[node_id]
        # Recompute task count (count remaining nodes for this task)
        self._task_counts[task] = sum(
            1 for n in self._nodes.values() if n["task"] == task
        )
        self._save()
        logger.info("Removed node: %s", node_id)
        return True

    def clear_all(self) -> int:
        """Remove ALL nodes from the registry and reset task counts.

        Useful on server startup to prevent stale registrations from
        previous sessions from permanently consuming node slots.

        Returns:
            Number of nodes that were cleared.
        """
        count = len(self._nodes)
        self._nodes = {}
        self._task_counts = {}
        self._save()
        if count:
            logger.info("Cleared %d stale node(s) from registry on startup.", count)
        return count

    def clear_task(self, task: str) -> int:
        """Remove all nodes for a specific task. Returns count removed."""
        to_remove = [nid for nid, info in self._nodes.items() if info["task"] == task]
        for nid in to_remove:
            del self._nodes[nid]
        self._task_counts[task] = 0
        self._save()
        if to_remove:
            logger.info("Cleared %d node(s) for task=%s.", len(to_remove), task)
        return len(to_remove)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        data = {
            "max_nodes_per_task": self.max_nodes_per_task,
            "task_counts": self._task_counts,
            "nodes": self._nodes,
        }
        with open(self.registry_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        try:
            with open(self.registry_file, "r") as f:
                data = json.load(f)
            self._nodes = data.get("nodes", {})
            self._task_counts = data.get("task_counts", {})
            logger.info(
                "Loaded node registry: %d nodes from %s",
                len(self._nodes), self.registry_file,
            )
        except FileNotFoundError:
            logger.info("No node registry file found at %s — starting fresh.", self.registry_file)
            self._nodes = {}
            self._task_counts = {}
        except Exception as e:
            logger.error("Failed to load node registry: %s — starting fresh.", e)
            self._nodes = {}
            self._task_counts = {}
