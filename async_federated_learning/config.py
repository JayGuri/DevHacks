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
    # Gatekeeper (L2 Norm Filter Funnel)
    # ------------------------------------------------------------------
    use_gatekeeper: bool = True
    gatekeeper_l2_factor: float = 3.0  # Std deviation multiplier
    gatekeeper_min_threshold: float = 0.01
    gatekeeper_max_threshold: float = 1000.0

    # ------------------------------------------------------------------
    # Privacy Mechanisms (mutually exclusive or combined)
    # ------------------------------------------------------------------
    # Differential Privacy: adds noise, some accuracy loss
    use_dp: bool = False
    dp_noise_multiplier: float = 0.1
    dp_clip_norm: float = 1.0
    
    # Secure Aggregation: cryptographic masking, ZERO accuracy loss
    use_secure_aggregation: bool = True
    secure_agg_seed: int = 42  # For reproducibility (testing only)

    # ------------------------------------------------------------------
    # WandB
    # ------------------------------------------------------------------
    use_wandb: bool = False
    wandb_project: str = "arfl-devhacks2026"

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    eval_every_n_rounds: int = 5
    output_dir: str = "./results"

    # ------------------------------------------------------------------
    # Derived fields — computed in __post_init__, not set by the caller
    # ------------------------------------------------------------------
    num_byzantine_clients: int = field(default=0, init=False, repr=False)
    num_honest_clients: int = field(default=0, init=False, repr=False)

    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """
        Validate configuration and compute derived fields.

        Checks:
          1. byzantine_fraction must be < 0.5 (majority-honest assumption).
          2. CIFAR-10 requires in_channels == 3.

        Derived:
          - num_byzantine_clients = int(num_clients * byzantine_fraction)
          - num_honest_clients    = num_clients - num_byzantine_clients
          - output_dir is created if it does not already exist.
        """
        # 1. Majority-honest sanity check
        if self.byzantine_fraction >= 0.5:
            raise ValueError(
                f"byzantine_fraction must be < 0.5 for majority-honest "
                f"assumption; got {self.byzantine_fraction}."
            )

        # 2. Derived client counts
        # num_byzantine_clients = ⌊N · f⌋  where f = byzantine_fraction
        self.num_byzantine_clients = int(self.num_clients * self.byzantine_fraction)
        self.num_honest_clients = self.num_clients - self.num_byzantine_clients

        # 3. Create output directory
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        logger.debug("Output directory ensured: %s", output_path.resolve())

        # 4. Channel / dataset consistency check
        if self.in_channels == 1 and self.dataset_name == "CIFAR10":
            raise ValueError(
                "CIFAR10 is an RGB dataset and requires in_channels=3, "
                f"but in_channels={self.in_channels} was provided."
            )

        logger.info(
            "Config validated — clients: %d (%d Byzantine, %d honest), "
            "attack: %s, aggregation: %s, DP: %s",
            self.num_clients,
            self.num_byzantine_clients,
            self.num_honest_clients,
            self.attack_type,
            self.aggregation_method,
            self.use_dp,
        )

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
