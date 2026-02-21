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
from privacy.dp import PrivacyEngine
from attacks.byzantine import MaliciousTrainer

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
    """numpy arrays -> lists -> msgpack bytes -> base64 string."""
    serializable = {}
    for key, val in weights.items():
        serializable[key] = val.tolist()
    packed = msgpack.packb(serializable, use_bin_type=True)
    return base64.b64encode(packed).decode("utf-8")


def deserialize_weights(b64_str: str) -> dict:
    """Reverses serialize_weights. Returns dict of numpy arrays."""
    packed = base64.b64decode(b64_str)
    unpacked = msgpack.unpackb(packed, raw=False)
    weights = {}
    for key, val in unpacked.items():
        k = key if isinstance(key, str) else key.decode("utf-8")
        weights[k] = np.array(val, dtype=np.float32)
    return weights


class WSClient:
    """WebSocket client for communicating with the FedBuff server."""

    def __init__(self, server_url: str, auth_token: str, client_id: str,
                 task: str, on_global_model, on_rejected):
        self.server_url = server_url
        self.auth_token = auth_token
        self.client_id = client_id
        self.task = task
        self.on_global_model = on_global_model
        self.on_rejected = on_rejected
        self.ws = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to server with exponential backoff retry: [2, 4, 8, 16, 32] seconds."""
        import websockets

        url = f"{self.server_url}?token={self.auth_token}&task={self.task}"
        backoff_delays = [2, 4, 8, 16, 32]
        attempt = 0

        while True:
            try:
                self.ws = await websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=100 * 1024 * 1024,  # 100MB max message
                )
                self._connected = True
                logger.info(
                    "Connected to server: %s (client=%s, task=%s)",
                    self.server_url, self.client_id, self.task,
                )
                return
            except Exception as e:
                delay = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                logger.warning(
                    "Connection failed (attempt %d): %s. Retrying in %ds...",
                    attempt + 1, e, delay,
                )
                await asyncio.sleep(delay)
                attempt += 1

    async def send_update(self, update: dict) -> None:
        """
        Sends JSON weight_update message.
        """
        if not self.ws or not self._connected:
            logger.warning("Cannot send update: not connected")
            return

        message = {
            "type": "weight_update",
            "client_id": self.client_id,
            "task": self.task,
            "round_num": update.get("round_num", 0),
            "global_round_received": update.get("global_round_received", 0),
            "weights": update.get("weights", ""),
            "num_samples": update.get("num_samples", 0),
            "local_loss": update.get("local_loss", 0.0),
            "privacy_budget": update.get("privacy_budget", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await self.ws.send(json.dumps(message))
            logger.debug("Sent weight update: round=%d", update.get("round_num", 0))
        except Exception as e:
            logger.error("Failed to send update: %s", e)
            self._connected = False

    async def receive_loop(self) -> None:
        """Dispatches received messages."""
        if not self.ws:
            return

        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "global_model":
                        logger.info(
                            "Received global model: task=%s, round=%d",
                            data.get("task", ""), data.get("round_num", 0),
                        )
                        await self.on_global_model(data)

                    elif msg_type == "rejected":
                        logger.warning(
                            "Update rejected by server: reason=%s, round=%d",
                            data.get("reason", "unknown"), data.get("round_num", 0),
                        )
                        await self.on_rejected(data)

                    elif msg_type == "status":
                        logger.info(
                            "Status broadcast: event=%s, task=%s",
                            data.get("event", ""), data.get("task", ""),
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

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self._connected = False


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
        import urllib.request, json
        rest_url = server_url.replace("ws://", "http://").replace("/ws/fl", "/nodes/register")
        data = json.dumps({
            "role": client_role,
            "display_name": display_name,
            "participant": participant,
            "task": dataset
        }).encode("utf-8")
        req = urllib.request.Request(rest_url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                auth_token = resp_data.get("token", "")
                if client_id == "unknown-client":
                    client_id = resp_data.get("node_id", client_id)
        except Exception as e:
            print(f"Auto-registration failed: {e}")
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

    # Step 1: Load data
    mongo_uri = os.environ.get("MONGO_URI", "")
    if mongo_uri:
        from client.mongo_loader import MongoPartitionLoader
        loader = MongoPartitionLoader(
            mongo_uri=mongo_uri,
            partition_id=data_partition,
            batch_size=32,
        )
        data_loader = loader.get_dataloader()
        logger.info("Data loaded via MongoPartitionLoader: %s", loader)
    else:
        leaf_loader = LEAFLoader(dataset, node_index=data_partition, total_nodes=total_nodes, batch_size=32)
        data_loader = leaf_loader.get_dataloader()
        logger.info("Data loaded via LEAFLoader (node_index=%d)", data_partition)

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
    async def on_global_model(data: dict):
        nonlocal current_global_weights, current_global_round
        weights_b64 = data.get("weights", "")
        new_global = deserialize_weights(weights_b64)
        alpha = data.get("personalization_alpha", 0.0)
        if alpha > 0.0 and current_global_weights:
            # Personalized blend: keep some local knowledge from previous round
            current_global_weights = {
                k: (1.0 - alpha) * new_global[k] + alpha * current_global_weights.get(k, new_global[k])
                for k in new_global
            }
        else:
            current_global_weights = new_global
        current_global_round = data.get("round_num", 0)
        new_model_event.set()

    async def on_rejected(data: dict):
        logger.warning(
            "Update rejected: reason=%s, round=%d",
            data.get("reason", "unknown"), data.get("round_num", 0),
        )

    # Step 4: Create WebSocket client
    ws_client = WSClient(server_url, auth_token, client_id, dataset,
                         on_global_model, on_rejected)

    # Connect (with retries)
    await ws_client.connect()

    # Start receive loop in background
    receive_task = asyncio.create_task(ws_client.receive_loop())

    # Wait for initial global model
    logger.info("Waiting for initial global model from server...")
    try:
        await asyncio.wait_for(new_model_event.wait(), timeout=60.0)
    except asyncio.TimeoutError:
        logger.warning("Timeout waiting for initial global model. Using local init.")

    new_model_event.clear()

    # Step 5: Main FL training loop
    try:
        while True:
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

            # Apply DP
            processed_diff = privacy_engine.process(result["weight_diff"])
            budget = privacy_engine.get_privacy_budget()

            # Serialize weights
            weights_b64 = serialize_weights(processed_diff)

            # Send to server
            await ws_client.send_update({
                "round_num": local_round,
                "global_round_received": current_global_round,
                "weights": weights_b64,
                "num_samples": result["num_samples"],
                "local_loss": result.get("local_loss", result.get("loss", 0.0)),
                "privacy_budget": budget,
            })

            logger.info(
                "%s | %s | Round %d | Loss %.6f | Epsilon %.4f | Samples %d",
                client_id, dataset, local_round,
                result.get("local_loss", result.get("loss", 0.0)),
                budget["epsilon"], result["num_samples"],
            )

            # Wait for new global model or timeout
            new_model_event.clear()
            try:
                await asyncio.wait_for(new_model_event.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                logger.info("No new global model received in 120s, continuing training")

            new_model_event.clear()

    except KeyboardInterrupt:
        logger.info("Client shutting down (keyboard interrupt)")
    except Exception as e:
        logger.exception("Client error: %s", e)
    finally:
        receive_task.cancel()
        try:
            await receive_task
        except asyncio.CancelledError:
            pass
        await ws_client.close()
        logger.info("Client %s stopped.", client_id)


if __name__ == "__main__":
    asyncio.run(main())
