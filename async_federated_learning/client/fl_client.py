# client/fl_client.py — Full client: FL loop, trainer, PrivacyEngine calls, WSClient
import os
import sys
import json
import glob
import asyncio
import argparse
import random
import time
import base64
from pathlib import Path
import logging
from datetime import datetime, timezone

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

import msgpack
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.cnn import get_model, VOCAB_SHAKESPEARE
from attacks.byzantine import MaliciousTrainer
from privacy.dp import PrivacyEngine
from privacy.secure_aggregation import SecureAggregationClient

logger = logging.getLogger("fedbuff.client")

# ============================================================================
# Data Loading — LEAF format
# ============================================================================


class LEAFLoader:
    """Loads LEAF benchmark data (FEMNIST or Shakespeare) with partitioning."""

    def __init__(self, dataset: str, node_index: int, total_nodes: int = 10,
                 batch_size: int = 32):
        self.dataset = dataset
        self.data_partition = node_index       # alias for internal use
        self.partition_count = total_nodes     # alias for internal use
        self.node_index = node_index
        self.total_nodes = total_nodes
        self.batch_size = batch_size

        # Data directories
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", dataset, "data",
        )
        self.train_dir = os.path.join(base_dir, "train")
        self.test_dir = os.path.join(base_dir, "test")

    def _load_all_shards(self, split_dir: str) -> dict:
        """Glob all *.json shards, sort filenames, merge users and user_data."""
        if not os.path.exists(split_dir):
            logger.warning("Data directory not found: %s", split_dir)
            return {"users": [], "user_data": {}}

        shard_files = sorted(glob.glob(os.path.join(split_dir, "*.json")))
        if not shard_files:
            logger.warning("No JSON shard files found in %s", split_dir)
            return {"users": [], "user_data": {}}

        all_users = []
        all_user_data = {}

        for shard_path in shard_files:
            try:
                with open(shard_path, "r") as f:
                    shard = json.load(f)
                users = shard.get("users", [])
                user_data = shard.get("user_data", {})
                all_users.extend(users)
                all_user_data.update(user_data)
            except Exception as e:
                logger.warning("Failed to load shard %s: %s", shard_path, e)

        logger.info("Loaded %d users from %s", len(all_users), split_dir)
        return {"users": all_users, "user_data": all_user_data}

    def _get_partition_users(self, all_users: list) -> list:
        """Divide users into partition_count chunks; return chunk[partition]."""
        if not all_users:
            return []

        # Sort for deterministic partitioning
        sorted_users = sorted(all_users)
        chunk_size = max(len(sorted_users) // self.partition_count, 1)
        start = self.data_partition * chunk_size
        end = start + chunk_size if self.data_partition < self.partition_count - 1 else len(sorted_users)
        partition_users = sorted_users[start:end]
        logger.info(
            "Partition %d/%d: %d users (indices %d-%d of %d total)",
            self.data_partition, self.partition_count,
            len(partition_users), start, end - 1, len(sorted_users),
        )
        return partition_users

    def _prepare_femnist(self, user_data: dict, users: list) -> tuple:
        """Prepare FEMNIST data as tensors."""
        all_x = []
        all_y = []

        for user in users:
            if user not in user_data:
                continue
            ud = user_data[user]
            x_data = ud.get("x", [])
            y_data = ud.get("y", [])

            for x_sample, y_sample in zip(x_data, y_data):
                # x: list of 784 floats -> reshape to (1, 28, 28)
                img = np.array(x_sample, dtype=np.float32).reshape(1, 28, 28)
                all_x.append(img)
                all_y.append(int(y_sample))

        if not all_x:
            return None, None

        x_tensor = torch.tensor(np.array(all_x), dtype=torch.float32)
        y_tensor = torch.tensor(np.array(all_y), dtype=torch.long)
        return x_tensor, y_tensor

    def _prepare_shakespeare(self, user_data: dict, users: list) -> tuple:
        """Prepare Shakespeare data as tensors."""
        all_x = []
        all_y = []

        char_to_idx = {ch: i for i, ch in enumerate(VOCAB_SHAKESPEARE)}

        for user in users:
            if user not in user_data:
                continue
            ud = user_data[user]
            x_data = ud.get("x", [])
            y_data = ud.get("y", [])

            for x_str, y_str in zip(x_data, y_data):
                x_indices = [char_to_idx.get(c, 0) for c in x_str[:80]]
                y_indices = [char_to_idx.get(c, 0) for c in y_str[:80]]

                # Pad to 80 if shorter
                while len(x_indices) < 80:
                    x_indices.append(0)
                while len(y_indices) < 80:
                    y_indices.append(0)

                all_x.append(x_indices[:80])
                all_y.append(y_indices[:80])

        if not all_x:
            return None, None

        x_tensor = torch.tensor(np.array(all_x), dtype=torch.long)
        y_tensor = torch.tensor(np.array(all_y), dtype=torch.long)
        return x_tensor, y_tensor

    def get_dataloader(self) -> DataLoader:
        """Assemble DataLoader. Falls back to synthetic if no data found."""
        shard_data = self._load_all_shards(self.train_dir)
        all_users = shard_data["users"]
        user_data = shard_data["user_data"]

        partition_users = self._get_partition_users(all_users)

        if not partition_users:
            logger.warning(
                "No partition users found for %s partition %d. Using synthetic fallback.",
                self.dataset, self.data_partition,
            )
            return self._synthetic_dataloader()

        if self.dataset == "femnist":
            x_tensor, y_tensor = self._prepare_femnist(user_data, partition_users)
        elif self.dataset == "shakespeare":
            x_tensor, y_tensor = self._prepare_shakespeare(user_data, partition_users)
        else:
            logger.warning("Unknown dataset: %s. Using synthetic fallback.", self.dataset)
            return self._synthetic_dataloader()

        if x_tensor is None or y_tensor is None:
            logger.warning(
                "No data assembled for %s partition %d. Using synthetic fallback.",
                self.dataset, self.data_partition,
            )
            return self._synthetic_dataloader()

        dataset = TensorDataset(x_tensor, y_tensor)
        logger.info(
            "DataLoader ready: %s, partition=%d, samples=%d",
            self.dataset, self.data_partition, len(dataset),
        )
        return DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

    def _synthetic_dataloader(self) -> DataLoader:
        """
        Fallback DataLoader when no LEAF JSON data is available.

        For Shakespeare: tries to load from the raw text file on disk via
        ShakespearePartitioner (gives real training signal).  Falls back to
        random tensors only if no text file can be found.
        For FEMNIST: returns random tensors (development/testing only).
        """
        if self.dataset == "shakespeare":
            return self._real_shakespeare_dataloader()

        logger.warning(
            "SYNTHETIC DATA: Generating fallback data for %s (partition %d). "
            "This is for development/testing only.",
            self.dataset, self.data_partition,
        )
        # FEMNIST: (256, 1, 28, 28) float32, labels [0, 61]
        x = torch.randn(256, 1, 28, 28, dtype=torch.float32)
        y = torch.randint(0, 62, (256,), dtype=torch.long)
        dataset = TensorDataset(x, y)
        return DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

    def _real_shakespeare_dataloader(self) -> DataLoader:
        """
        Load Shakespeare data from the raw text file using ShakespearePartitioner.

        Partitions the corpus with Dirichlet(alpha=0.5) into ``partition_count``
        shards and returns the DataLoader for shard ``data_partition``.
        Falls back to random tensors if no text file is found.
        """
        try:
            partitioner = ShakespearePartitioner(seq_length=80)
            text = partitioner.load_dataset()  # auto-finds data/raw/*.txt
            _, _, vocab_size = partitioner.build_vocabulary(text)

            # Use a fixed seed so all clients get consistent, non-overlapping shards
            shards = partitioner.partition_data(
                text, self.partition_count, alpha=0.5, seed=42
            )
            idx = min(self.data_partition, len(shards) - 1)
            shard = shards[idx]

            dataloader = partitioner.get_client_dataloader(
                shard, batch_size=self.batch_size
            )
            logger.info(
                "Shakespeare real data loaded: partition=%d, shard_len=%d chars, "
                "vocab_size=%d, batches=%d",
                self.data_partition, len(shard), vocab_size, len(dataloader),
            )
            return dataloader

        except FileNotFoundError as exc:
            logger.warning(
                "Shakespeare text file not found (%s). "
                "Falling back to random synthetic tensors.",
                exc,
            )
        except Exception as exc:
            logger.warning(
                "Failed to load real Shakespeare data (%s). "
                "Falling back to random synthetic tensors.",
                exc,
            )

        logger.warning(
            "SYNTHETIC DATA: Generating random fallback for shakespeare (partition %d).",
            self.data_partition,
        )
        x = torch.randint(0, 80, (256, 80), dtype=torch.long)
        y = torch.randint(0, 80, (256, 80), dtype=torch.long)
        dataset = TensorDataset(x, y)
        return DataLoader(dataset, batch_size=self.batch_size, shuffle=True)


# ============================================================================
# Honest Trainer — FedProx
# ============================================================================


class HonestTrainer:
    """Honest FedProx trainer for legitimate clients."""

    def __init__(self, model: nn.Module, global_weights: dict,
                 mu: float = 0.01, lr: float = 0.01, epochs: int = 5,
                 device: str = "cpu"):
        self.model = model
        self.global_weights = global_weights
        self.mu = mu
        self.lr = lr
        self.epochs = epochs
        self.device = device
        self.heartbeat_delay = (0.5, 3.0)

    def _run_epochs(self, data_loader) -> dict:
        """
        FedProx training loop (synchronous, run via asyncio.to_thread):
          loss = CrossEntropy(output, y) + (mu/2) * sum(||w_i - w0_i||^2)
        Returns {"loss": float, "weight_diff": dict_of_numpy, "num_samples": int}
        """
        self.model.to(self.device)
        self.model.train()

        # Load global weights into model
        global_tensors = {}
        for name, param in self.model.named_parameters():
            if name in self.global_weights:
                param.data.copy_(
                    torch.tensor(self.global_weights[name], dtype=param.dtype).to(self.device)
                )
            global_tensors[name] = param.data.clone()

        optimizer = torch.optim.SGD(self.model.parameters(), lr=self.lr)
        criterion = nn.CrossEntropyLoss()

        total_loss = 0.0
        total_samples = 0

        for epoch in range(self.epochs):
            for batch_x, batch_y in data_loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)

                optimizer.zero_grad()
                output = self.model(batch_x)

                # Handle Shakespeare output shape: (B, 80, 80) -> reshape for CE
                if output.dim() == 3:
                    output = output.view(-1, output.size(-1))
                    batch_y = batch_y.view(-1)

                ce_loss = criterion(output, batch_y)

                # FedProx proximal term
                prox_loss = 0.0
                for name, param in self.model.named_parameters():
                    if name in global_tensors:
                        prox_loss += torch.sum((param - global_tensors[name]) ** 2)
                prox_loss = (self.mu / 2.0) * prox_loss

                loss = ce_loss + prox_loss
                loss.backward()
                optimizer.step()

                total_loss += ce_loss.item() * batch_x.size(0)
                total_samples += batch_x.size(0)

        # Compute weight diff (local - global)
        weight_diff = {}
        for name, param in self.model.named_parameters():
            if name in self.global_weights:
                weight_diff[name] = (
                    param.data.cpu().numpy() - self.global_weights[name]
                )

        avg_loss = total_loss / max(total_samples, 1)
        return {
            "loss": avg_loss,
            "weight_diff": weight_diff,
            "num_samples": total_samples,
        }

    async def train(self, data_loader) -> dict:
        """
        Async wrapper: runs training in thread, then simulates heartbeat delay.
        """
        result = await asyncio.to_thread(self._run_epochs, data_loader)

        # Async heartbeat delay
        delay = random.uniform(*self.heartbeat_delay)
        await asyncio.sleep(delay)

        result["local_loss"] = result["loss"]
        return result


# ============================================================================
# WebSocket Client
# ============================================================================


def serialize_weights(weights: dict) -> str:
    """numpy arrays -> lists -> msgpack bytes -> zlib compress -> base64 string."""
    import zlib
    serializable = {}
    for key, val in weights.items():
        serializable[key] = val.tolist()
    packed = msgpack.packb(serializable, use_bin_type=True)
    compressed = zlib.compress(packed, level=6)
    return base64.b64encode(compressed).decode("utf-8")


def deserialize_weights(b64_str: str) -> dict:
    """Reverses serialize_weights. Auto-detects zlib compression."""
    import zlib
    raw = base64.b64decode(b64_str)
    # Auto-detect zlib compression (magic byte 0x78)
    try:
        raw = zlib.decompress(raw)
    except zlib.error:
        pass  # Not compressed — treat as raw msgpack
    unpacked = msgpack.unpackb(raw, raw=False)
    weights = {}
    for key, val in unpacked.items():
        k = key if isinstance(key, str) else key.decode("utf-8")
        weights[k] = np.array(val, dtype=np.float32)
    return weights


class WSClient:
    """WebSocket client for communicating with the FedBuff server."""

    def __init__(self, uri: str, auth_token: str, client_id: str, participant: str, task: str, role: str, config):
        self.uri = uri
        self.auth_token = auth_token
        self.client_id = client_id
        self.participant = participant
        self.task = task
        self.role = role
        self.config = config
        self.ws = None
        self._connected = False
        self._disconnect_event = asyncio.Event()  # Signalled when connection is lost
        self.event_handlers = {}
        self.current_round = 0 # Track current global round for SA
        self._global_model_chunks = None
        self._last_chunk_time = 0.0  # monotonic timestamp of last chunk receipt — used for chunk-aware timeout

        # ── Setup Secure Aggregation Client ──
        # Extract integer ID for Diffie-Hellman if possible
        try:
            numeric_id = int(client_id.replace("client_", ""))
        except ValueError:
            numeric_id = abs(hash(client_id)) % (10 ** 8)
            
        use_sa = getattr(config, 'USE_SECURE_AGGREGATION', False)
        self.sa_client = SecureAggregationClient(client_id=numeric_id, enabled=use_sa)
        self.numeric_id = numeric_id

    def on(self, event_name: str, handler):
        """Register an event handler."""
        self.event_handlers[event_name] = handler

    async def _fire_event(self, event_name: str, *args, **kwargs):
        """Fire an event, calling its registered handler."""
        handler = self.event_handlers.get(event_name)
        if handler:
            await handler(*args, **kwargs)
        else:
            logger.warning("No handler registered for event: %s", event_name)

    def _serialize_weights(self, weights: dict) -> str:
        """numpy arrays -> lists -> msgpack bytes -> zlib compress -> base64 string."""
        import zlib
        serializable = {}
        for key, val in weights.items():
            serializable[key] = val.tolist()
        packed = msgpack.packb(serializable, use_bin_type=True)
        compressed = zlib.compress(packed, level=6)
        return base64.b64encode(compressed).decode("utf-8")

    def _deserialize_weights(self, b64_str: str) -> dict:
        """Reverses serialize_weights. Auto-detects zlib compression."""
        import zlib
        raw = base64.b64decode(b64_str)
        # Auto-detect zlib compression (magic byte 0x78)
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass  # Not compressed — treat as raw msgpack
        unpacked = msgpack.unpackb(raw, raw=False)
        weights = {}
        for key, val in unpacked.items():
            k = key if isinstance(key, str) else key.decode("utf-8")
            weights[k] = np.array(val, dtype=np.float32)
        return weights

    async def connect(self, max_retries: int = 10) -> asyncio.Task:
        """Connect to server with exponential backoff retry: [2, 4, 8, 16, 32] seconds.

        Args:
            max_retries: Maximum number of connection attempts before giving up.
        """
        import websockets

        url = f"{self.uri}?client_id={self.client_id}&task={self.task}&role={self.role}&participant={self.participant}"
        if self.auth_token:
            url += f"&token={self.auth_token}"

        backoff_delays = [2, 4, 8, 16, 32]
        attempt = 0

        while attempt < max_retries:
            try:
                self.ws = await websockets.connect(
                    url,
                    ping_interval=None,  # Disabled — client pings cause concurrent-write crashes in server's legacy websockets protocol during chunk delivery
                    ping_timeout=None,   # Disabled — no pings to timeout
                    max_size=100 * 1024 * 1024,  # 100MB max message
                )
                self._connected = True
                logger.info(
                    "Connected to server: %s (client=%s, task=%s)",
                    self.uri, self.client_id, self.task,
                )

                # Send public key if secure aggregation is enabled
                if self.sa_client.enabled:
                    pub_key = self.sa_client.get_public_key()
                    if pub_key:
                        await self.ws.send(json.dumps({
                            "type": "public_key",
                            "client_id": self.client_id,
                            "task": self.task,
                            "public_key": pub_key
                        }))
                        logger.info("Sent public key for secure aggregation.")

                # Start message listener loop
                return asyncio.create_task(self.listen_loop())
            except Exception as e:
                delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                logger.warning(
                    "Connection failed (attempt %d/%d): %s. Retrying in %ds...",
                    attempt + 1, max_retries, e, delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

        # Exhausted all retries
        self._disconnect_event.set()
        raise ConnectionError(
            f"Failed to connect to {self.uri} after {max_retries} attempts"
        )

    async def send_update(self, update_dict: dict):
        """Send weight update + loss to the server."""
        if self.ws is None or not self._connected:
            logger.warning("Cannot send update: not connected")
            return

        # Prepare payload
        payload = dict(update_dict)
        payload["type"] = "weight_update"
        payload["client_id"] = self.client_id
        payload["task"] = self.task
        
        # Apply Secure Aggregation Masking if enabled
        if self.sa_client.enabled and "weights" in payload:
            raw_weights = payload["weights"]
            # To mask, SA needs a list of all client IDs currently paired. We'll extract them from generated keys
            if hasattr(self.sa_client, "key_manager") and self.sa_client.key_manager:
                all_ids = list(self.sa_client.key_manager.pairwise_keys.keys()) + [self.sa_client.client_id]
                rnd = payload.get("round_num", 0)
                payload["weights"] = self.sa_client.mask_update(raw_weights, all_ids, rnd)

        # Base64 encode weights
        if "weights" in payload:
            payload["weights"] = self._serialize_weights(payload["weights"])

        payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        try:
            await self.ws.send(json.dumps(payload))
            logger.debug("Sent weight update: round=%d", payload.get("round_num", 0))
        except Exception as e:
            logger.error("Failed to send update: %s", e)
            self._connected = False

    async def listen_loop(self) -> None:
        """Dispatches received messages."""
        if not self.ws:
            return

        try:
            async for message in self.ws:
                try:
                    logger.info("Received raw message string of length %d", len(message))
                    data = json.loads(message)
                    if isinstance(data, str):
                        data = json.loads(data)
                        
                    msg_type = data.get("type", "") if isinstance(data, dict) else ""
                    logger.info("Decoded message type: %s", msg_type)

                    async def _apply_global_model_payload(payload: dict):
                        global_round = payload.get("round_num", 0)
                        self.current_round = global_round
                        logger.info(
                            "Received global model: task=%s, round=%d",
                            payload.get("task", ""), global_round,
                        )
                        if "weights" in payload:
                            weights_dict = self._deserialize_weights(payload["weights"])
                            await self._fire_event(
                                "global_model",
                                global_round,
                                weights_dict,
                                payload.get("assigned_chunk"),
                            )

                    if msg_type == "global_model":
                        await _apply_global_model_payload(data)

                    elif msg_type == "global_model_start":
                        total_chunks = int(data.get("total_chunks", 0))
                        if total_chunks <= 0:
                            logger.warning("Invalid global_model_start: total_chunks=%s", data.get("total_chunks"))
                            self._global_model_chunks = None
                        else:
                            self._global_model_chunks = {
                                "meta": {
                                    "task": data.get("task", self.task),
                                    "round_num": data.get("round_num", 0),
                                    "version": data.get("version", ""),
                                    "timestamp": data.get("timestamp", ""),
                                    "assigned_chunk": data.get("assigned_chunk"),
                                },
                                "total": total_chunks,
                                "parts": [None] * total_chunks,
                            }

                    elif msg_type == "global_model_chunk":
                        self._last_chunk_time = time.monotonic()
                        assembly = self._global_model_chunks
                        if assembly is None:
                            continue
                        idx = int(data.get("chunk_index", -1))
                        total = int(data.get("total_chunks", assembly["total"]))
                        if total != assembly["total"]:
                            logger.warning("Chunk total mismatch during global model assembly; dropping partial model.")
                            self._global_model_chunks = None
                            continue
                        if 0 <= idx < assembly["total"]:
                            assembly["parts"][idx] = data.get("data", "")

                    elif msg_type == "global_model_end":
                        assembly = self._global_model_chunks
                        if assembly is None:
                            continue
                        missing = [i for i, part in enumerate(assembly["parts"]) if part is None]
                        if missing:
                            logger.warning(
                                "global_model_end received with missing chunks: %d missing (first=%s)",
                                len(missing), missing[0],
                            )
                            self._global_model_chunks = None
                            continue
                        joined = "".join(assembly["parts"])
                        payload = dict(assembly["meta"])
                        payload["weights"] = joined
                        await _apply_global_model_payload(payload)
                        self._global_model_chunks = None
                            
                    elif msg_type == "key_broadcast":
                        # Setup secure aggregation round when keys are broadcasted
                        if self.sa_client.enabled:
                            public_keys = data.get("public_keys", {})
                            # Convert string keys back to int for SA module if necessary, or hash string
                            parsed_keys = {}
                            for cid, pkey in public_keys.items():
                                try:
                                    num_cid = int(cid.replace("client_", ""))
                                except ValueError:
                                    num_cid = abs(hash(cid)) % (10 ** 8)
                                parsed_keys[num_cid] = pkey
                                
                            self.sa_client.setup_round(parsed_keys, round_number=self.current_round)
                            logger.info("Secure aggregation keys received and round setup for round %d", self.current_round)

                    elif msg_type == "rejected":
                        logger.warning(
                            "Update rejected by server: reason=%s, round=%d",
                            data.get("reason", "unknown"), data.get("round_num", 0),
                        )
                        await self._fire_event("rejected", data)

                    elif msg_type == "status":
                        logger.info(
                            "Status broadcast: event=%s, task=%s",
                            data.get("event", ""), data.get("task", ""),
                        )

                    elif msg_type == "trust_report":
                        my_score = data.get("trust_scores", {}).get(self.client_id)
                        my_staleness = data.get("staleness_values", {}).get(self.client_id)
                        rejected = data.get("rejected_clients", [])
                        gk_rejected = data.get("gatekeeper_rejected", [])
                        logger.info(
                            "Trust report: round=%d, my_trust_score=%s, "
                            "my_staleness=%s, rejected=%s, gatekeeper_rejected=%s",
                            data.get("round", 0),
                            my_score,
                            my_staleness,
                            rejected,
                            gk_rejected,
                        )
                        if my_score is not None and my_score == 0.0:
                            logger.warning(
                                "⚠ My trust score is 0.0 — my update was flagged as suspicious!"
                            )

                    elif msg_type == "pong":
                        logger.debug("Pong received")

                    else:
                        logger.debug("Unknown message type: %s", msg_type)

                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received from server")
                except Exception as e:
                    logger.error("Error processing server message: %s", e)

        except Exception as e:
            logger.info("WebSocket receive loop ended: %s", e)
            self._connected = False
            self._disconnect_event.set()

    async def reconnect(self, max_retries: int = 5) -> asyncio.Task:
        """Tear down current connection and establish a new one.

        Resets internal state (_connected, _disconnect_event, partial chunk
        buffers) and calls connect() again. Returns a new listen_task.
        """
        # Tear down old connection
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
        self._connected = False
        self._disconnect_event = asyncio.Event()  # fresh event
        self._global_model_chunks = None
        self.ws = None
        return await self.connect(max_retries=max_retries)

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self._connected = False
            self._disconnect_event.set()


# ============================================================================
# Main FL Loop
# ============================================================================


async def main():
    """Main FL client loop."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="FedBuff FL Client")
    parser.add_argument("--env", type=str, default=None, help="Path to .env file")
    parser.add_argument(
        "--demo-speed", action="store_true",
        help="Demo mode: LOCAL_EPOCHS=1, heartbeat delay=0.0",
    )
    args = parser.parse_args()

    # Load environment variables
    root_env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(args.env or str(root_env_path), override=True)

    # Read configuration from environment
    client_id = os.environ.get("CLIENT_ID", "unknown-client")
    client_role = os.environ.get("CLIENT_ROLE", "legitimate_client")
    display_name = os.environ.get("DISPLAY_NAME", client_id)
    participant = os.environ.get("PARTICIPANT", "Unknown")
    server_url = os.environ.get("SERVER_URL", "ws://localhost:8765/ws/fl")
    auth_token = os.environ.get("AUTH_TOKEN", "")
    dataset = os.environ.get("DATASET", "femnist")
    if not auth_token:
        import urllib.request, json  # NB: do NOT import time here — it shadows the module-level import and causes UnboundLocalError later
        rest_url = server_url.replace("ws://", "http://").replace("wss://", "https://").replace("/ws/fl", "/nodes/register")
        data = json.dumps({
            "role": client_role,
            "display_name": display_name,
            "participant": participant,
            "task": dataset
        }).encode("utf-8")
        req = urllib.request.Request(rest_url, data=data, headers={"Content-Type": "application/json"})
        
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    auth_token = resp_data.get("token", "")
                    if client_id == "unknown-client":
                        client_id = resp_data.get("node_id", client_id)
                break  # Success
            except Exception as e:
                print(f"Attempt {attempt+1} auto-registration failed: {e}. Retrying...")
                time.sleep(2)
        else:
            print("Auto-registration failed after all attempts.")
    data_partition = int(os.environ.get("NODE_INDEX", os.environ.get("DATA_PARTITION", "0")))
    total_nodes = int(os.environ.get("TOTAL_NODES", "10"))
    local_epochs = int(os.environ.get("LOCAL_EPOCHS", "5"))
    learning_rate = float(os.environ.get("LEARNING_RATE", "0.01"))
    mu = float(os.environ.get("MU", "0.01"))
    dp_max_grad_norm = float(os.environ.get("DP_MAX_GRAD_NORM", "1.0"))
    dp_noise_multiplier = float(os.environ.get("DP_NOISE_MULTIPLIER", "1.1"))
    attack_scale = float(os.environ.get("ATTACK_SCALE", "-5.0"))
    attack_type = os.environ.get("ATTACK_TYPE", "sign_flip_amplified")

    # Demo speed overrides
    if args.demo_speed:
        local_epochs = 1
        heartbeat_delay = (0.0, 0.0)
        dp_noise_multiplier = 0.0  # Disable DP noise for demo as it causes NaN gradients on 1 epoch
    else:
        heartbeat_delay = (0.5, 3.0)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [{client_id}] [{dataset}] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logger.info(
        "Starting FL client: id=%s, role=%s, dataset=%s, node_index=%d/%d",
        client_id, client_role, dataset, data_partition, total_nodes,
    )

    # Step 1: Initialize data structures (but defer data loading until chunk is assigned)
    data_loader = None
    assigned_chunk_id = None


    # Step 2: Create model
    model = get_model(dataset)

    # Step 3: Privacy engine
    privacy_engine = PrivacyEngine(
        max_grad_norm=dp_max_grad_norm,
        noise_multiplier=dp_noise_multiplier,
    )

    # Shared state
    current_global_weights = {}
    current_global_round = 0
    local_round = 0
    new_model_event = asyncio.Event()

    # Extract initial weights from model
    for name, param in model.named_parameters():
        current_global_weights[name] = param.data.cpu().numpy().copy()

    # Callbacks
    async def on_global_model(round_num: int, weights_dict: dict, assigned_chunk: int = None):
        nonlocal current_global_weights, current_global_round, data_loader, assigned_chunk_id
        
        logger.info("on_global_model started!")
        # Initialize DataLoader if not already done using the server-assigned chunk
        if data_loader is None and assigned_chunk is not None:
            assigned_chunk_id = assigned_chunk
            
            # Re-read from environ to avoid Python scoping closure issues
            _mongo_uri = os.environ.get("MONGO_URI", "")
            if _mongo_uri:
                from client.mongo_loader import MongoPartitionLoader
                loader = MongoPartitionLoader(
                    mongo_uri=_mongo_uri,
                    partition_id=assigned_chunk_id,
                    batch_size=32,
                )
                data_loader = await asyncio.to_thread(loader.get_dataloader)
                logger.info("Data loaded via MongoPartitionLoader using assigned chunk %d", assigned_chunk_id)
            else:
                leaf_loader = LEAFLoader(dataset, node_index=assigned_chunk_id, total_nodes=total_nodes, batch_size=32)
                data_loader = await asyncio.to_thread(leaf_loader.get_dataloader)
                logger.info("Data loaded via LEAFLoader using assigned chunk %d", assigned_chunk_id)
        
        new_global = weights_dict
        alpha = 0.0 # TODO: support Personalization alpha later if provided natively
        if alpha > 0.0 and current_global_weights:
            # Personalized blend: keep some local knowledge from previous round
            current_global_weights = {
                k: (1.0 - alpha) * new_global[k] + alpha * current_global_weights.get(k, new_global[k])
                for k in new_global
            }
        else:
            current_global_weights = new_global
        current_global_round = round_num
        new_model_event.set()

    async def on_rejected(data: dict):
        logger.warning(
            "Update rejected: reason=%s, round=%d",
            data.get("reason", "unknown"), data.get("round_num", 0),
        )

    # Step 4: Create WebSocket client
    import config as _config
    config = _config.settings
    
    ws_client = WSClient(
        uri=server_url, 
        auth_token=auth_token,
        client_id=client_id, 
        participant="unknown", 
        task=dataset, 
        role=client_role, 
        config=config
    )
    ws_client.on("global_model", on_global_model)
    ws_client.on("rejected", on_rejected)

    # Connect (with retries and key broadcast handling internal to listen_loop/connect)
    listen_task = await ws_client.connect()

    # Wait for initial global model — chunk-aware: keep waiting while chunks are arriving
    MAX_MODEL_RECONNECTS = 3
    CHUNK_IDLE_TIMEOUT = 30.0  # seconds to wait with no chunk activity before giving up
    for _model_attempt in range(MAX_MODEL_RECONNECTS + 1):
        logger.info("Waiting for initial global model from server...")
        _deadline_inactive = time.monotonic() + 90.0  # 90s if no chunks ever arrive
        while True:
            # How long until we consider the transfer stalled?
            now = time.monotonic()
            if ws_client._last_chunk_time > 0:
                # Chunks are flowing — extend deadline relative to last chunk
                remaining = (ws_client._last_chunk_time + CHUNK_IDLE_TIMEOUT) - now
            else:
                # No chunks yet — use the initial deadline
                remaining = _deadline_inactive - now

            if remaining <= 0:
                break  # Timed out

            model_task = asyncio.create_task(new_model_event.wait())
            disconnect_task = asyncio.create_task(ws_client._disconnect_event.wait())
            done, pending = await asyncio.wait(
                [model_task, disconnect_task],
                timeout=min(remaining, 5.0),  # Check every 5s so we can re-evaluate chunk activity
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()

            if new_model_event.is_set():
                break
            if ws_client._disconnect_event.is_set():
                break

        if new_model_event.is_set():
            break  # Got the model successfully

        # Connection dropped before model arrived — try reconnecting
        if ws_client._disconnect_event.is_set() and _model_attempt < MAX_MODEL_RECONNECTS:
            logger.warning(
                "Connection lost during model download. Reconnecting (%d/%d)...",
                _model_attempt + 1, MAX_MODEL_RECONNECTS,
            )
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass
            new_model_event.clear()
            listen_task = await ws_client.reconnect()
            continue

        logger.warning("Timeout waiting for initial global model. Using local init.")
        break
        
    if data_loader is None:
        logger.info("Initializing local data loader due to missing or delayed server chunk assignment...")
        assigned_chunk_id = assigned_chunk_id if assigned_chunk_id is not None else data_partition
        _mongo_uri = os.environ.get("MONGO_URI", "")
        if _mongo_uri:
            from client.mongo_loader import MongoPartitionLoader
            loader = MongoPartitionLoader(mongo_uri=_mongo_uri, partition_id=assigned_chunk_id, batch_size=32)
            data_loader = await asyncio.to_thread(loader.get_dataloader)
        else:
            leaf_loader = LEAFLoader(dataset, node_index=assigned_chunk_id, total_nodes=total_nodes, batch_size=32)
            data_loader = await asyncio.to_thread(leaf_loader.get_dataloader)

    new_model_event.clear()

    # Step 5: Main FL training loop
    reconnect_budget = 3  # Allow a few reconnects during training
    try:
        while True:
            # ── Check for disconnection before each round ──
            if not ws_client._connected and listen_task.done():
                if reconnect_budget > 0:
                    reconnect_budget -= 1
                    logger.warning(
                        "Server connection lost. Attempting reconnect (%d left)...",
                        reconnect_budget,
                    )
                    listen_task.cancel()
                    try:
                        await listen_task
                    except asyncio.CancelledError:
                        pass
                    try:
                        listen_task = await ws_client.reconnect()
                    except ConnectionError:
                        logger.error("Reconnect failed. Exiting training loop.")
                        break
                    # Wait briefly for a fresh global model after reconnect
                    new_model_event.clear()
                    try:
                        await asyncio.wait_for(new_model_event.wait(), timeout=90.0)
                    except asyncio.TimeoutError:
                        logger.warning("No global model after reconnect — continuing with current weights.")
                    new_model_event.clear()
                    continue
                else:
                    logger.info("Server connection lost. No reconnect budget remaining. Exiting.")
                    break

            local_round += 1

            # Create trainer with current global weights
            if client_role == "malicious_client":
                trainer = MaliciousTrainer(
                    model=model,
                    global_weights=current_global_weights,
                    mu=mu,
                    lr=learning_rate,
                    epochs=local_epochs,
                    device="cpu",
                    attack_scale=attack_scale,
                )
            else:
                trainer = HonestTrainer(
                    model=model,
                    global_weights=current_global_weights,
                    mu=mu,
                    lr=learning_rate,
                    epochs=local_epochs,
                    device="cpu",
                )

            # Override heartbeat delay for demo speed
            trainer.heartbeat_delay = heartbeat_delay

            # Train
            result = await trainer.train(data_loader)

            staleness_delay = float(os.environ.get("STALENESS_DELAY", "0.0"))
            if staleness_delay > 0:
                logger.info("[%s] Simulating staleness: sleeping for %ss", client_id, staleness_delay)
                await asyncio.sleep(staleness_delay)

            # Apply DP
            processed_diff = privacy_engine.process(result["weight_diff"])
            budget = privacy_engine.get_privacy_budget()

            # Send to server
            await ws_client.send_update({
                "round_num": local_round,
                "global_round_received": current_global_round,
                "weights": processed_diff,
                "num_samples": result["num_samples"],
                "local_loss": result.get("local_loss", result.get("loss", 0.0)),
                "privacy_budget": budget,
            })

            logger.info(
                "[%s] Chunk %d | Round %d | Loss %.6f | Samples %d | Epsilon %.4f",
                client_id, assigned_chunk_id if assigned_chunk_id is not None else data_partition, local_round,
                result.get("local_loss", result.get("loss", 0.0)),
                result["num_samples"], budget["epsilon"],
            )

            # Wait for new global model, disconnect signal, or timeout
            new_model_event.clear()
            try:
                # Race: wait for either new model or disconnect
                done, _ = await asyncio.wait(
                    [
                        asyncio.create_task(new_model_event.wait()),
                        asyncio.create_task(ws_client._disconnect_event.wait()),
                    ],
                    timeout=120.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                # Cancel pending tasks
                for t in _:
                    t.cancel()
                if ws_client._disconnect_event.is_set():
                    logger.info("Disconnect detected while waiting for global model. Exiting.")
                    break
                if not done:
                    logger.info("No new global model received in 120s, continuing training")
            except asyncio.TimeoutError:
                logger.info("No new global model received in 120s, continuing training")

            new_model_event.clear()

    except KeyboardInterrupt:
        logger.info("Client shutting down (keyboard interrupt)")
    except Exception as e:
        logger.exception("Client error: %s", e)
    finally:
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass
        await ws_client.close()
        logger.info("Client %s stopped.", client_id)


if __name__ == "__main__":
    asyncio.run(main())
