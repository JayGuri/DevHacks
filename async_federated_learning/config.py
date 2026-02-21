"""
config.py
=========
Central configuration module for the async federated learning framework.

Contains:
- Config dataclass: single source of truth for all hyperparameters covering
  dataset, model architecture, local training, async behaviour, aggregation,
  SABD detection, differential privacy, WandB logging, and evaluation.
- __post_init__ validation and derived-field computation.
- summary() for human-readable grouped display.
- to_dict() for serialisation / WandB config upload.
"""

import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """
    Single source of truth for every hyperparameter in the ARFL pipeline.

    Covers:
      - Dataset & partitioning (Dirichlet non-IID).
      - Byzantine attack type and fraction.
      - Model architecture dimensions.
      - Local SGD training schedule.
      - Async staleness handling.
      - Aggregation strategy (FedAvg / TrimmedMean / CoordMedian).
      - SABD anomaly-detection parameters.
      - Differential privacy (DP-SGD).
      - WandB experiment tracking.
      - Evaluation cadence and output directory.

    Derived fields (init=False):
      - num_byzantine_clients: floor(num_clients * byzantine_fraction)
      - num_honest_clients:    num_clients - num_byzantine_clients
    """

    # ------------------------------------------------------------------
    # Dataset
    # ------------------------------------------------------------------
    dataset_name: str = "MNIST"
    data_dir: str = "./data/raw"
    num_clients: int = 10
    num_classes: int = 10

    # ------------------------------------------------------------------
    # Byzantine / Attack settings
    # ------------------------------------------------------------------
    byzantine_fraction: float = 0.2
    attack_type: str = "sign_flipping"

    # ------------------------------------------------------------------
    # Data heterogeneity
    # ------------------------------------------------------------------
    dirichlet_alpha: float = 0.5

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------
    modality: str = "image"  # "image" or "text"
    in_channels: int = 1
    hidden_dim: int = 128
    
    # Text-specific model parameters (for Shakespeare)
    text_model_type: str = "lstm"  # "lstm" or "rnn"
    vocab_size: int = 80  # Will be set dynamically from data
    embedding_dim: int = 128
    text_hidden_dim: int = 256
    text_num_layers: int = 2
    text_dropout: float = 0.3
    seq_length: int = 80

    # ------------------------------------------------------------------
    # Local training
    # ------------------------------------------------------------------
    num_rounds: int = 50
    local_epochs: int = 3
    batch_size: int = 32
    learning_rate: float = 0.01
    seed: int = 42

    # ------------------------------------------------------------------
    # Async behaviour
    # ------------------------------------------------------------------
    max_staleness: int = 10
    staleness_penalty_factor: float = 0.5
    client_speed_variance: bool = True

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    aggregation_method: str = "trimmed_mean"
    trimmed_mean_beta: float = 0.1
    krum_num_byzantine: int = 2

    # ------------------------------------------------------------------
    # SABD (Staleness-Aware Byzantine Detection)
    # ------------------------------------------------------------------
    sabd_alpha: float = 0.5
    model_history_size: int = 15
    anomaly_threshold: float = 2.5
    
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

    def summary(self) -> None:
        """Print a formatted, grouped table of all configuration settings."""
        groups = {
            "Dataset": [
                ("dataset_name", self.dataset_name),
                ("data_dir", self.data_dir),
                ("num_clients", self.num_clients),
                ("num_classes", self.num_classes),
                ("dirichlet_alpha", self.dirichlet_alpha),
            ],
            "Byzantine / Attack": [
                ("byzantine_fraction", self.byzantine_fraction),
                ("attack_type", self.attack_type),
                ("num_byzantine_clients", self.num_byzantine_clients),
                ("num_honest_clients", self.num_honest_clients),
            ],
            "Model": [
                ("modality", self.modality),
                ("in_channels", self.in_channels),
                ("hidden_dim", self.hidden_dim),
                ("text_model_type", self.text_model_type if self.modality == "text" else "N/A"),
                ("vocab_size", self.vocab_size if self.modality == "text" else "N/A"),
            ],
            "Local Training": [
                ("num_rounds", self.num_rounds),
                ("local_epochs", self.local_epochs),
                ("batch_size", self.batch_size),
                ("learning_rate", self.learning_rate),
                ("seed", self.seed),
            ],
            "Async Behaviour": [
                ("max_staleness", self.max_staleness),
                ("staleness_penalty_factor", self.staleness_penalty_factor),
                ("client_speed_variance", self.client_speed_variance),
            ],
            "Aggregation": [
                ("aggregation_method", self.aggregation_method),
                ("trimmed_mean_beta", self.trimmed_mean_beta),
                ("krum_num_byzantine", self.krum_num_byzantine),
            ],
            "SABD Detection": [
                ("sabd_alpha", self.sabd_alpha),
                ("model_history_size", self.model_history_size),
                ("anomaly_threshold", self.anomaly_threshold),
            ],
            "Gatekeeper": [
                ("use_gatekeeper", self.use_gatekeeper),
                ("gatekeeper_l2_factor", self.gatekeeper_l2_factor),
                ("gatekeeper_max_threshold", self.gatekeeper_max_threshold),
            ],
            "Differential Privacy": [
                ("use_dp", self.use_dp),
                ("dp_noise_multiplier", self.dp_noise_multiplier),
                ("dp_clip_norm", self.dp_clip_norm),
            ],
            "WandB": [
                ("use_wandb", self.use_wandb),
                ("wandb_project", self.wandb_project),
            ],
            "Evaluation": [
                ("eval_every_n_rounds", self.eval_every_n_rounds),
                ("output_dir", self.output_dir),
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

    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return all configuration fields as a plain dict (via dataclasses.asdict)."""
        return asdict(self)
