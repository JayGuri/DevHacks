# config.py — Unified configuration: Pydantic BaseSettings (networking) + scientific hyperparameters
import os
import math
import logging
from pydantic_settings import BaseSettings
from typing import List
from pathlib import Path

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Central configuration for the ARFL / FedBuff system.
    All values are read from environment variables with sensible defaults.

    Covers:
      - Server networking, JWT, and supported tasks.
      - FL training hyperparameters (rounds, epochs, learning rates).
      - Dataset & partitioning (Dirichlet non-IID).
      - Byzantine attack type and fraction.
      - Model architecture dimensions.
      - Async staleness handling.
      - Aggregation strategy selection.
      - SABD anomaly-detection parameters.
      - Differential privacy (DP-SGD).
      - Storage and evaluation settings.
    """

    # ------------------------------------------------------------------
    # Server (akshat networking layer)
    # ------------------------------------------------------------------
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8765
    USERS_FILE: str = "./users.json"
    LOG_LEVEL: str = "INFO"
    SUPPORTED_TASKS: List[str] = ["femnist", "shakespeare"]
    JWT_EXPIRY_HOURS: int = 24
    JWT_SECRET: str = ""

    # ------------------------------------------------------------------
    # FL Hyperparameters (merged from both branches)
    # ------------------------------------------------------------------
    BUFFER_SIZE_K: int = 3
    NUM_CLIENTS: int = 10
    NUM_ROUNDS: int = 50
    LOCAL_EPOCHS: int = 3
    BATCH_SIZE: int = 32
    LEARNING_RATE: float = 0.01
    LEARNING_RATE_GLOBAL: float = 1.0
    SEED: int = 42

    # ------------------------------------------------------------------
    # Dataset & Partitioning (ayush scientific core)
    # ------------------------------------------------------------------
    DATASET_NAME: str = "MNIST"
    DATA_DIR: str = "./data/raw"
    NUM_CLASSES: int = 10
    DIRICHLET_ALPHA: float = 0.5

    # ------------------------------------------------------------------
    # Byzantine / Attack Settings (ayush scientific core)
    # ------------------------------------------------------------------
    BYZANTINE_FRACTION: float = 0.2
    ATTACK_TYPE: str = "sign_flipping"

    # ------------------------------------------------------------------
    # Model Architecture (ayush scientific core)
    # ------------------------------------------------------------------
    IN_CHANNELS: int = 1
    HIDDEN_DIM: int = 128

    # ------------------------------------------------------------------
    # Async Behaviour (merged)
    # ------------------------------------------------------------------
    MAX_STALENESS: int = 10
    STALENESS_ALPHA: float = 0.5
    CLIENT_SPEED_VARIANCE: bool = True

    # ------------------------------------------------------------------
    # Event-Driven Buffer
    # ------------------------------------------------------------------
    MIN_UPDATES_FOR_AGGREGATION: int = 2
    MAX_WAIT_SECONDS: float = 10.0
    MAX_UPDATES_PER_BATCH: int = 20

    # ------------------------------------------------------------------
    # Client Dropout / Heartbeat
    # ------------------------------------------------------------------
    CLIENT_HEARTBEAT_TIMEOUT: float = 60.0
    MIN_CLIENTS_FOR_AGGREGATION: int = 1
    HEARTBEAT_CHECK_INTERVAL: float = 10.0

    # ------------------------------------------------------------------
    # Staleness-Based Trust Scoring
    # ------------------------------------------------------------------
    STALENESS_DECAY_FN: str = "polynomial"   # "exponential" | "polynomial"
    STALENESS_LAMBDA: float = 0.1            # lambda for exponential decay
    STALENESS_REPUTATION_WEIGHT: float = 0.5 # 0=pure staleness, 1=pure reputation

    # ------------------------------------------------------------------
    # Network Simulation
    # ------------------------------------------------------------------
    NETWORK_SIMULATION_ENABLED: bool = False
    PACKET_LOSS_PROB: float = 0.0
    MIN_LATENCY_MS: float = 10.0
    MAX_LATENCY_MS: float = 500.0
    NETWORK_PARTITION_ENABLED: bool = False
    PARTITION_CLIENTS: List[str] = []

    # ------------------------------------------------------------------
    # Multi-Model / Personalization
    # ------------------------------------------------------------------
    PERSONALIZATION_ENABLED: bool = False
    PERSONALIZATION_ALPHA: float = 0.2
    MODEL_VERSIONING_ENABLED: bool = True

    # ------------------------------------------------------------------
    # Aggregation (merged)
    # ------------------------------------------------------------------
    AGGREGATION_STRATEGY: str = "trimmed_mean"
    KRUM_BYZANTINE_FRACTION: float = 0.3
    TRIM_FRACTION: float = 0.2
    TRIMMED_MEAN_BETA: float = 0.1
    KRUM_NUM_BYZANTINE: int = 2

    # ------------------------------------------------------------------
    # SABD Detection (ayush scientific core)
    # ------------------------------------------------------------------
    SABD_ALPHA: float = 0.5
    MODEL_HISTORY_SIZE: int = 15
    ANOMALY_THRESHOLD: float = 2.5

    # ------------------------------------------------------------------
    # Defense — Gatekeeper
    # ------------------------------------------------------------------
    L2_NORM_THRESHOLD: float = 500.0
    use_gatekeeper: bool = True
    gatekeeper_l2_factor: float = 3.0
    gatekeeper_max_threshold: float = 1000.0

    # ------------------------------------------------------------------
    # Multimodal / text model settings
    # ------------------------------------------------------------------
    modality: str = "image"          # "image" | "text"
    text_model_type: str = "lstm"    # "lstm" | "rnn"
    vocab_size: int = 80             # Shakespeare character vocabulary size

    # ------------------------------------------------------------------
    # Differential Privacy (merged)
    # ------------------------------------------------------------------
    USE_DP: bool = True
    DP_MAX_GRAD_NORM: float = 1.0
    DP_NOISE_MULTIPLIER: float = 1.1
    DP_CLIP_NORM: float = 1.0

    # ------------------------------------------------------------------
    # WandB (ayush scientific core)
    # ------------------------------------------------------------------
    USE_WANDB: bool = False
    WANDB_PROJECT: str = "arfl-devhacks2026"

    # ------------------------------------------------------------------
    # Evaluation & Storage (merged)
    # ------------------------------------------------------------------
    EVAL_EVERY_N_ROUNDS: int = 5
    MODEL_CHECKPOINT_DIR: str = "./results/checkpoints"
    RESULTS_DIR: str = "./results"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def num_byzantine_clients(self) -> int:
        """Number of Byzantine clients = floor(NUM_CLIENTS * BYZANTINE_FRACTION)."""
        return int(self.NUM_CLIENTS * self.BYZANTINE_FRACTION)

    @property
    def num_honest_clients(self) -> int:
        """Number of honest clients = NUM_CLIENTS - num_byzantine_clients."""
        return self.NUM_CLIENTS - self.num_byzantine_clients

    def summary(self) -> None:
        """Print a formatted, grouped table of all configuration settings."""
        groups = {
            "Server": [
                ("SERVER_HOST", self.SERVER_HOST),
                ("SERVER_PORT", self.SERVER_PORT),
                ("LOG_LEVEL", self.LOG_LEVEL),
                ("SUPPORTED_TASKS", self.SUPPORTED_TASKS),
            ],
            "Dataset": [
                ("DATASET_NAME", self.DATASET_NAME),
                ("DATA_DIR", self.DATA_DIR),
                ("NUM_CLIENTS", self.NUM_CLIENTS),
                ("NUM_CLASSES", self.NUM_CLASSES),
                ("DIRICHLET_ALPHA", self.DIRICHLET_ALPHA),
            ],
            "Byzantine / Attack": [
                ("BYZANTINE_FRACTION", self.BYZANTINE_FRACTION),
                ("ATTACK_TYPE", self.ATTACK_TYPE),
                ("num_byzantine_clients", self.num_byzantine_clients),
                ("num_honest_clients", self.num_honest_clients),
            ],
            "Model": [
                ("IN_CHANNELS", self.IN_CHANNELS),
                ("HIDDEN_DIM", self.HIDDEN_DIM),
            ],
            "Training": [
                ("NUM_ROUNDS", self.NUM_ROUNDS),
                ("LOCAL_EPOCHS", self.LOCAL_EPOCHS),
                ("BATCH_SIZE", self.BATCH_SIZE),
                ("LEARNING_RATE", self.LEARNING_RATE),
                ("BUFFER_SIZE_K", self.BUFFER_SIZE_K),
                ("SEED", self.SEED),
            ],
            "Async Behaviour": [
                ("MAX_STALENESS", self.MAX_STALENESS),
                ("STALENESS_ALPHA", self.STALENESS_ALPHA),
                ("CLIENT_SPEED_VARIANCE", self.CLIENT_SPEED_VARIANCE),
                ("MIN_UPDATES_FOR_AGGREGATION", self.MIN_UPDATES_FOR_AGGREGATION),
                ("MAX_WAIT_SECONDS", self.MAX_WAIT_SECONDS),
                ("MAX_UPDATES_PER_BATCH", self.MAX_UPDATES_PER_BATCH),
            ],
            "Client Dropout": [
                ("CLIENT_HEARTBEAT_TIMEOUT", self.CLIENT_HEARTBEAT_TIMEOUT),
                ("MIN_CLIENTS_FOR_AGGREGATION", self.MIN_CLIENTS_FOR_AGGREGATION),
                ("HEARTBEAT_CHECK_INTERVAL", self.HEARTBEAT_CHECK_INTERVAL),
            ],
            "Staleness Trust": [
                ("STALENESS_DECAY_FN", self.STALENESS_DECAY_FN),
                ("STALENESS_LAMBDA", self.STALENESS_LAMBDA),
                ("STALENESS_REPUTATION_WEIGHT", self.STALENESS_REPUTATION_WEIGHT),
            ],
            "Network Simulation": [
                ("NETWORK_SIMULATION_ENABLED", self.NETWORK_SIMULATION_ENABLED),
                ("PACKET_LOSS_PROB", self.PACKET_LOSS_PROB),
                ("MIN_LATENCY_MS", self.MIN_LATENCY_MS),
                ("MAX_LATENCY_MS", self.MAX_LATENCY_MS),
                ("NETWORK_PARTITION_ENABLED", self.NETWORK_PARTITION_ENABLED),
            ],
            "Personalization": [
                ("PERSONALIZATION_ENABLED", self.PERSONALIZATION_ENABLED),
                ("PERSONALIZATION_ALPHA", self.PERSONALIZATION_ALPHA),
                ("MODEL_VERSIONING_ENABLED", self.MODEL_VERSIONING_ENABLED),
            ],
            "Aggregation": [
                ("AGGREGATION_STRATEGY", self.AGGREGATION_STRATEGY),
                ("TRIMMED_MEAN_BETA", self.TRIMMED_MEAN_BETA),
                ("KRUM_NUM_BYZANTINE", self.KRUM_NUM_BYZANTINE),
            ],
            "SABD Detection": [
                ("SABD_ALPHA", self.SABD_ALPHA),
                ("MODEL_HISTORY_SIZE", self.MODEL_HISTORY_SIZE),
                ("ANOMALY_THRESHOLD", self.ANOMALY_THRESHOLD),
            ],
            "Gatekeeper": [
                ("use_gatekeeper", self.use_gatekeeper),
                ("gatekeeper_l2_factor", self.gatekeeper_l2_factor),
                ("gatekeeper_max_threshold", self.gatekeeper_max_threshold),
            ],
            "Differential Privacy": [
                ("USE_DP", self.USE_DP),
                ("DP_NOISE_MULTIPLIER", self.DP_NOISE_MULTIPLIER),
                ("DP_CLIP_NORM", self.DP_CLIP_NORM),
            ],
            "Storage": [
                ("MODEL_CHECKPOINT_DIR", self.MODEL_CHECKPOINT_DIR),
                ("RESULTS_DIR", self.RESULTS_DIR),
            ],
        }

        col_width = 30
        val_width = 20
        separator = "+" + "-" * (col_width + 2) + "+" + "-" * (val_width + 2) + "+"

        print("\n" + "=" * (col_width + val_width + 7))
        print(" ARFL Configuration Summary")
        print("=" * (col_width + val_width + 7))

        for group_name, entries in groups.items():
            print(f"\n  [{group_name}]")
            print(separator)
            for key, value in entries:
                print(f"| {key:<{col_width}} | {str(value):<{val_width}} |")
            print(separator)

        print()


settings = Settings()

# Alias used by test_multimodal.py and experiment scripts
Config = Settings
