# server/model_history.py — Task-aware model registry, serialization, checkpointing
import uuid
import pickle
import base64
import json
import os
import logging
import numpy as np
import msgpack
from datetime import datetime, timezone

logger = logging.getLogger("fedbuff.server.model_history")


class ModelHistory:
    """Task-aware model registry with serialization and checkpointing support."""

    def __init__(self, models: dict, checkpoint_dir: str):
        """
        models: {"femnist": FEMNISTNet(), "shakespeare": ShakespeareNet()}
        Builds self.state with current weights and history for each task.
        """
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

        self.state = {}
        for task, model in models.items():
            weights = {}
            for name, param in model.named_parameters():
                weights[name] = param.data.cpu().numpy().copy()

            self.state[task] = {
                "current_round": 0,
                "version": str(uuid.uuid4()),
                "weights": weights,
                "loss_history": [],
                "accuracy_history": [],
            }
            logger.info(
                "ModelHistory initialized for task=%s, version=%s, params=%d",
                task, self.state[task]["version"], len(weights),
            )

    def update(self, task: str, aggregated_weights: dict,
               loss: float, accuracy: float = None) -> None:
        """
        Increments current_round for the task.
        Replaces weights. Appends loss (and accuracy if provided) to history.
        Generates a new version UUID.
        Every 5 rounds, pickles state to checkpoint file.
        """
        if task not in self.state:
            raise ValueError(f"Unknown task: {task}")

        task_state = self.state[task]
        task_state["current_round"] += 1
        task_state["version"] = str(uuid.uuid4())

        # Apply aggregated weight diffs to current weights
        for name, diff in aggregated_weights.items():
            if name in task_state["weights"]:
                task_state["weights"][name] = (
                    task_state["weights"][name].astype(np.float64) + diff.astype(np.float64)
                ).astype(np.float32)
            else:
                task_state["weights"][name] = diff.astype(np.float32)

        task_state["loss_history"].append(loss)
        if accuracy is not None:
            task_state["accuracy_history"].append(accuracy)

        current_round = task_state["current_round"]
        logger.info(
            "ModelHistory updated: task=%s, round=%d, version=%s, loss=%.6f",
            task, current_round, task_state["version"], loss,
        )

        # Checkpoint every 5 rounds
        if current_round % 5 == 0:
            checkpoint_path = os.path.join(
                self.checkpoint_dir,
                f"{task}_round_{current_round:04d}.pkl",
            )
            try:
                with open(checkpoint_path, "wb") as f:
                    pickle.dump(task_state, f)
                logger.info(
                    "Checkpoint saved: %s (round %d)", checkpoint_path, current_round
                )
            except Exception as e:
                logger.error("Failed to save checkpoint: %s", e)

    def get_latest(self, task: str) -> dict:
        """Returns compact representation of latest model for a task."""
        if task not in self.state:
            raise ValueError(f"Unknown task: {task}")

        task_state = self.state[task]
        return {
            "version": task_state["version"],
            "round": task_state["current_round"],
            "weights": self.serialize_weights(task_state["weights"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def serialize_weights(self, weights: dict) -> str:
        """numpy arrays -> lists -> msgpack bytes -> base64 string."""
        serializable = {}
        for key, val in weights.items():
            serializable[key] = val.tolist()
        packed = msgpack.packb(serializable, use_bin_type=True)
        return base64.b64encode(packed).decode("utf-8")

    def deserialize_weights(self, b64_str: str) -> dict:
        """Reverses serialize_weights. Returns dict of numpy arrays."""
        packed = base64.b64decode(b64_str)
        unpacked = msgpack.unpackb(packed, raw=False)
        weights = {}
        for key, val in unpacked.items():
            k = key if isinstance(key, str) else key.decode("utf-8")
            weights[k] = np.array(val, dtype=np.float32)
        return weights

    def get_loss_history(self, task: str) -> list:
        """Returns the loss history for a task."""
        if task not in self.state:
            return []
        return self.state[task]["loss_history"]

    def get_accuracy_history(self, task: str) -> list:
        """Returns the accuracy history for a task."""
        if task not in self.state:
            return []
        return self.state[task].get("accuracy_history", [])

    def get_weights(self, task: str) -> dict:
        """Returns the current numpy weights dict for a task."""
        if task not in self.state:
            raise ValueError(f"Unknown task: {task}")
        return self.state[task]["weights"]

    def get_round(self, task: str) -> int:
        """Returns the current round for a task."""
        if task not in self.state:
            return 0
        return self.state[task]["current_round"]
