# backend/training/node_manager.py — Stateful tracker for simulated FL nodes
"""
Manages the per-node state for a training session.
Each node tracks: trust, cosineDistance, staleness, status, etc.

Provides methods to:
- Initialize nodes from project config (mix of honest/byzantine/slow)
- Update node state after each training round
- Handle dynamic join/drop/block/unblock
- Determine node status based on cosineDistance + trust thresholds
"""

import random
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("arfl.node_manager")


class NodeState:
    """In-memory state for a single FL node."""

    def __init__(
        self,
        node_id: str,
        display_id: str,
        client_idx: int,
        is_byzantine: bool = False,
        is_slow: bool = False,
        user_id: Optional[str] = None,
    ):
        self.node_id = node_id
        self.display_id = display_id
        self.client_idx = client_idx
        self.user_id = user_id

        # Behaviour flags (set at creation, define ground truth)
        self.is_byzantine = is_byzantine
        self.is_slow = is_slow
        self.is_blocked = False
        self.is_dropped = False  # Simulates client going offline

        # Per-round metrics (updated by coordinator)
        self.trust = 1.0
        self.cosine_distance = 0.0
        self.staleness = 0
        self.rounds_contributed = 0

        # Derived status
        self.status = "ACTIVE"

    def update_status(self) -> None:
        """Determine node status from current metrics and flags."""
        if self.is_blocked:
            self.status = "BLOCKED"
        elif self.is_dropped:
            self.status = "BLOCKED"  # treat dropped as blocked for display
        elif self.cosine_distance > 0.45 or (self.is_byzantine and self.trust < 0.4):
            self.status = "BYZANTINE"
        elif self.is_slow:
            self.status = "SLOW"
        else:
            self.status = "ACTIVE"

    def to_dict(self) -> dict:
        """Serialize to the exact schema the frontend expects."""
        return {
            "nodeId": self.node_id,
            "displayId": self.display_id,
            "userId": self.user_id,
            "status": self.status,
            "trust": round(self.trust, 4),
            "cosineDistance": round(self.cosine_distance, 4),
            "staleness": self.staleness,
            "roundsContributed": self.rounds_contributed,
            "isByzantine": self.is_byzantine and self.status == "BYZANTINE",
            "isSlow": self.is_slow,
            "isBlocked": self.is_blocked,
        }


class NodeManager:
    """Manages all nodes for a single project's training session."""

    def __init__(self):
        self.nodes: Dict[str, NodeState] = {}
        self._next_idx: int = 0

    def initialize_nodes(self, num_clients: int, byzantine_fraction: float) -> List[NodeState]:
        """Create initial node pool with the configured number of clients.

        Args:
            num_clients: Total number of nodes
            byzantine_fraction: Fraction of nodes that are byzantine (0.0-1.0)

        Returns:
            List of initialized NodeState objects
        """
        self.nodes.clear()
        self._next_idx = 0

        num_byzantine = int(num_clients * byzantine_fraction)
        # Randomly assign ~10% as slow (non-byzantine)
        num_slow = max(1, int((num_clients - num_byzantine) * 0.1))

        # Assign roles: first num_byzantine are byzantine, next num_slow are slow, rest are honest
        indices = list(range(num_clients))
        random.shuffle(indices)

        byzantine_indices = set(indices[:num_byzantine])
        slow_indices = set(indices[num_byzantine:num_byzantine + num_slow])

        for i in range(num_clients):
            node_id = f"node-{i}"
            row = chr(65 + (i // 4))  # A, B, C, D...
            col = (i % 4) + 1
            display_id = f"NODE_{row}{col}"

            node = NodeState(
                node_id=node_id,
                display_id=display_id,
                client_idx=i,
                is_byzantine=(i in byzantine_indices),
                is_slow=(i in slow_indices),
            )
            self.nodes[node_id] = node
            self._next_idx = i + 1

        logger.info(
            "Initialized %d nodes: %d byzantine, %d slow, %d honest",
            num_clients, num_byzantine, num_slow,
            num_clients - num_byzantine - num_slow,
        )
        return list(self.nodes.values())

    def update_node_metrics(
        self,
        node_id: str,
        trust: float,
        cosine_distance: float,
        contributed: bool = True,
    ) -> None:
        """Update a node's per-round metrics after aggregation."""
        node = self.nodes.get(node_id)
        if not node:
            return

        node.trust = trust
        node.cosine_distance = cosine_distance

        if contributed and not node.is_blocked and not node.is_dropped:
            node.rounds_contributed += 1
            node.staleness = 0
        else:
            node.staleness += 1

        node.update_status()

    def block_node(self, node_id: str) -> Optional[dict]:
        """Admin blocks a node. Returns updated node dict or None."""
        node = self.nodes.get(node_id)
        if not node:
            return None
        node.is_blocked = True
        node.update_status()
        logger.info("Node blocked: %s (%s)", node_id, node.display_id)
        return node.to_dict()

    def unblock_node(self, node_id: str) -> Optional[dict]:
        """Admin unblocks a node. Returns updated node dict or None."""
        node = self.nodes.get(node_id)
        if not node:
            return None
        node.is_blocked = False
        node.update_status()
        logger.info("Node unblocked: %s (%s)", node_id, node.display_id)
        return node.to_dict()

    def add_node(self, is_byzantine: bool = False, is_slow: bool = False) -> NodeState:
        """Dynamically add a new node mid-training."""
        i = self._next_idx
        node_id = f"node-{i}"
        row = chr(65 + (i // 4))
        col = (i % 4) + 1
        display_id = f"NODE_{row}{col}"

        node = NodeState(
            node_id=node_id,
            display_id=display_id,
            client_idx=i,
            is_byzantine=is_byzantine,
            is_slow=is_slow,
        )
        self.nodes[node_id] = node
        self._next_idx = i + 1
        logger.info("Dynamic node added: %s (%s, byzantine=%s)", node_id, display_id, is_byzantine)
        return node

    def drop_node(self, node_id: str) -> Optional[dict]:
        """Simulate a client going offline (dropout)."""
        node = self.nodes.get(node_id)
        if not node:
            return None
        node.is_dropped = True
        node.update_status()
        logger.info("Node dropped (offline): %s (%s)", node_id, node.display_id)
        return node.to_dict()

    def rejoin_node(self, node_id: str) -> Optional[dict]:
        """Simulate a dropped client coming back online."""
        node = self.nodes.get(node_id)
        if not node:
            return None
        node.is_dropped = False
        node.staleness = 0
        node.update_status()
        logger.info("Node rejoined: %s (%s)", node_id, node.display_id)
        return node.to_dict()

    def simulate_random_events(self, round_num: int) -> List[dict]:
        """Randomly simulate client join/drop/sleep events each round.

        Returns list of event dicts for logging.
        """
        events = []
        active_nodes = [n for n in self.nodes.values() if not n.is_blocked and not n.is_dropped]

        # ~5% chance a random honest active node goes offline
        if active_nodes and random.random() < 0.05:
            honest_active = [n for n in active_nodes if not n.is_byzantine]
            if honest_active:
                drop_node = random.choice(honest_active)
                self.drop_node(drop_node.node_id)
                events.append({
                    "type": "node_dropped",
                    "nodeId": drop_node.node_id,
                    "displayId": drop_node.display_id,
                    "round": round_num,
                })

        # ~3% chance a dropped node rejoins
        dropped = [n for n in self.nodes.values() if n.is_dropped and not n.is_blocked]
        if dropped and random.random() < 0.03:
            rejoin_node = random.choice(dropped)
            self.rejoin_node(rejoin_node.node_id)
            events.append({
                "type": "node_rejoined",
                "nodeId": rejoin_node.node_id,
                "displayId": rejoin_node.display_id,
                "round": round_num,
            })

        # ~2% chance to add a new node (up to 2x original size)
        if len(self.nodes) < self._next_idx + 5 and random.random() < 0.02:
            # 20% chance new node is malicious
            new_node = self.add_node(
                is_byzantine=(random.random() < 0.2),
                is_slow=(random.random() < 0.1),
            )
            events.append({
                "type": "node_added",
                "nodeId": new_node.node_id,
                "displayId": new_node.display_id,
                "round": round_num,
            })

        # Make some nodes occasionally slow
        for node in active_nodes:
            if not node.is_byzantine and not node.is_slow and random.random() < 0.02:
                node.is_slow = True
                events.append({
                    "type": "node_slowed",
                    "nodeId": node.node_id,
                    "displayId": node.display_id,
                    "round": round_num,
                })
            elif node.is_slow and not node.is_byzantine and random.random() < 0.1:
                # Slow nodes can recover
                node.is_slow = False
                events.append({
                    "type": "node_recovered",
                    "nodeId": node.node_id,
                    "displayId": node.display_id,
                    "round": round_num,
                })

        return events

    def get_active_nodes(self) -> List[NodeState]:
        """Return all non-blocked, non-dropped nodes."""
        return [n for n in self.nodes.values() if not n.is_blocked and not n.is_dropped]

    def get_all_nodes_dict(self) -> List[dict]:
        """Return all nodes in frontend-expected format."""
        return [n.to_dict() for n in self.nodes.values()]
