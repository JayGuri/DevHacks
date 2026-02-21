# network/simulator.py — Realistic network impairment simulation for FL experiments
"""
NetworkSimulator injects configurable network conditions into the server's
update ingestion path:

  - Packet loss    : random drop with configurable probability
  - Variable latency: base RTT + Gaussian jitter per client
  - Bandwidth throttling: per-client bandwidth cap (simulated transfer time)
  - Network partitioning: isolated client groups that cannot reach the server

Usage in fl_server.py handle_websocket():
    if network_simulator is not None:
        update = await network_simulator.simulate_client_upload(update, client_id)
        if update is None:
            continue  # packet dropped, skip enqueue
"""

import asyncio
import logging
import random

logger = logging.getLogger("fedbuff.network.simulator")


class NetworkSimulator:
    """Simulates realistic network impairments for FL research experiments."""

    def __init__(
        self,
        packet_loss_prob: float = 0.0,
        min_latency_ms: float = 10.0,
        max_latency_ms: float = 500.0,
        bandwidth_kbps: dict = None,
        partition_enabled: bool = False,
        partition_clients: list = None,
    ):
        """
        Parameters
        ----------
        packet_loss_prob  : float in [0, 1] — probability any packet is dropped
        min_latency_ms    : float — lower bound of simulated RTT (ms)
        max_latency_ms    : float — upper bound of simulated RTT (ms)
        bandwidth_kbps    : dict {client_id: float} — per-client upload bandwidth cap.
                            Defaults to 10_000 kbps (10 Mbps) for unknown clients.
        partition_enabled : bool — when True, clients in partition_clients are isolated
        partition_clients : list[str] — client IDs in the isolated network partition
        """
        self.packet_loss_prob = packet_loss_prob
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms
        self.bandwidth_kbps = bandwidth_kbps or {}
        self.partition_enabled = partition_enabled
        self.partition_clients = set(partition_clients or [])

        self._stats = {
            "total_uploads": 0,
            "dropped_packets": 0,
            "total_latency_ms": 0.0,
        }

        logger.info(
            "NetworkSimulator: loss=%.2f%%, latency=[%.0f, %.0f]ms, "
            "partition=%s (%d clients)",
            packet_loss_prob * 100,
            min_latency_ms,
            max_latency_ms,
            partition_enabled,
            len(self.partition_clients),
        )

    def is_partitioned(self, client_id: str) -> bool:
        """Return True if the client is in an isolated network partition."""
        return self.partition_enabled and client_id in self.partition_clients

    def _simulate_latency_ms(self, client_id: str) -> float:
        """Ping-based latency: uniform sample in [min_latency_ms, max_latency_ms]."""
        return random.uniform(self.min_latency_ms, self.max_latency_ms)

    def _simulate_bandwidth_delay_ms(self, update_size_bytes: int, client_id: str) -> float:
        """Transfer time based on per-client or default bandwidth.

        transfer_time_s = (size_bytes * 8 bits) / (bandwidth_kbps * 1000 bits/s)
        """
        bw_kbps = self.bandwidth_kbps.get(client_id, 10_000.0)  # default 10 Mbps
        bw_kbps = max(bw_kbps, 1.0)  # guard against zero division
        transfer_time_s = (update_size_bytes * 8) / (bw_kbps * 1000)
        return transfer_time_s * 1000  # convert to ms

    async def simulate_client_upload(
        self, update: dict, client_id: str
    ):
        """Simulate network conditions for one update upload.

        Returns the update dict (possibly after a delay) or None if dropped.

        Drop conditions:
          1. Client is in an isolated partition
          2. Random packet loss (packet_loss_prob)

        Delay = latency + bandwidth transfer time
        """
        self._stats["total_uploads"] += 1

        # Check network partition first
        if self.is_partitioned(client_id):
            logger.info(
                "NetworkSimulator: client=%s is PARTITIONED, update dropped", client_id
            )
            self._stats["dropped_packets"] += 1
            return None

        # Random packet loss
        if random.random() < self.packet_loss_prob:
            logger.info(
                "NetworkSimulator: packet DROPPED for client=%s (loss_prob=%.2f)",
                client_id, self.packet_loss_prob,
            )
            self._stats["dropped_packets"] += 1
            return None

        # Estimate serialized size from the base64-encoded weights string
        weights_str = update.get("weights", "")
        update_size_bytes = len(weights_str) if isinstance(weights_str, (str, bytes)) else 1000

        latency_ms = self._simulate_latency_ms(client_id)
        bw_delay_ms = self._simulate_bandwidth_delay_ms(update_size_bytes, client_id)
        total_delay_ms = latency_ms + bw_delay_ms

        self._stats["total_latency_ms"] += total_delay_ms

        logger.debug(
            "NetworkSimulator: client=%s latency=%.1fms bw_delay=%.1fms total=%.1fms",
            client_id, latency_ms, bw_delay_ms, total_delay_ms,
        )

        await asyncio.sleep(total_delay_ms / 1000.0)
        return update

    def get_stats(self) -> dict:
        """Return simulation statistics."""
        total = self._stats["total_uploads"]
        return {
            "total_uploads": total,
            "dropped_packets": self._stats["dropped_packets"],
            "drop_rate": self._stats["dropped_packets"] / max(total, 1),
            "avg_latency_ms": self._stats["total_latency_ms"] / max(total, 1),
        }
