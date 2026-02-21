# config.py — All hyperparameters and server settings (Pydantic BaseSettings)
import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Central configuration for the FedBuff system.
    All values are read from environment variables with sensible defaults."""

    # Server
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8765
    USERS_FILE: str = "./users.json"
    LOG_LEVEL: str = "INFO"
    SUPPORTED_TASKS: List[str] = ["femnist", "shakespeare"]

    # FL hyperparameters
    BUFFER_SIZE_K: int = 3
    MAX_STALENESS: int = 10
    STALENESS_ALPHA: float = 0.5
    LEARNING_RATE_GLOBAL: float = 1.0
    JWT_EXPIRY_HOURS: int = 24

    # Defense
    AGGREGATION_STRATEGY: str = "krum"  # "krum" | "trimmed_mean" | "coordinate_median" | "fedavg"
    L2_NORM_THRESHOLD: float = 500.0
    KRUM_BYZANTINE_FRACTION: float = 0.3
    TRIM_FRACTION: float = 0.2

    # Privacy
    DP_MAX_GRAD_NORM: float = 1.0
    DP_NOISE_MULTIPLIER: float = 1.1

    # Storage
    MODEL_CHECKPOINT_DIR: str = "./results/checkpoints"
    RESULTS_DIR: str = "./results"

    # JWT
    JWT_SECRET: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
