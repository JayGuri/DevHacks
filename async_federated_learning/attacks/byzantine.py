# attacks/byzantine.py — Multi-attack Byzantine simulator + legacy MaliciousTrainer
"""
attacks/byzantine.py
====================
Contains:
- AttackType enum: canonical names for all supported attack variants.
- ByzantineAttackSimulator: static methods for each attack (pure functions).
- apply_attack(): module-level dispatch function for FLClient.
- MaliciousTrainer: legacy akshat async sign-flip trainer (backward compat).
"""

import asyncio
import random
import logging
from enum import Enum

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Attack type enum (from ayush)
# ---------------------------------------------------------------------------

class AttackType(Enum):
    """Canonical identifiers for each supported Byzantine attack strategy."""
    NONE           = "none"
    SIGN_FLIP      = "sign_flipping"
    GRAD_SCALE     = "gradient_scaling"
    RANDOM_NOISE   = "random_noise"
    ZERO_GRADIENT  = "zero_gradient"
    GAUSSIAN_NOISE = "gaussian_noise"


# ---------------------------------------------------------------------------
# Attack simulator (from ayush — pure functions)
# ---------------------------------------------------------------------------

class ByzantineAttackSimulator:
    """Simulates Byzantine adversaries in federated learning.
    All methods are pure functions — input is never modified.
    """

    @staticmethod
    def sign_flipping(weight_delta: dict, scale: float = 1.0) -> dict:
        """Negate every gradient coordinate, optionally scaled.
        Formula: g_attacker = -g_honest * scale
        """
        attacked = {k: -v * scale for k, v in weight_delta.items()}
        logger.debug("sign_flipping applied (scale=%.2f)", scale)
        return attacked

    @staticmethod
    def gradient_scaling(weight_delta: dict, scale: float = 50.0) -> dict:
        """Amplify gradient by a large scalar factor.
        Formula: g_attacker = g_honest * scale
        """
        attacked = {k: v * scale for k, v in weight_delta.items()}
        logger.debug("gradient_scaling applied (scale=%.1f)", scale)
        return attacked

    @staticmethod
    def random_noise(weight_delta: dict, scale: float = 10.0) -> dict:
        """Replace gradient with scaled IID Gaussian noise.
        Formula: g_attacker ~ N(0, scale^2 * I)
        """
        attacked = {
            k: np.random.randn(*v.shape).astype(v.dtype) * scale
            for k, v in weight_delta.items()
        }
        logger.debug("random_noise applied (scale=%.1f).", scale)
        return attacked

    @staticmethod
    def zero_gradient(weight_delta: dict) -> dict:
        """Return all-zero update (free-rider attack)."""
        attacked = {k: np.zeros_like(v) for k, v in weight_delta.items()}
        logger.debug("zero_gradient applied — all-zero update submitted.")
        return attacked

    @staticmethod
    def gaussian_noise(weight_delta: dict, noise_std: float = 5.0) -> dict:
        """Add Gaussian noise on top of honest gradient.
        Formula: g_attacker = g_honest + N(0, noise_std^2 * I)
        """
        attacked = {
            k: v + np.random.normal(0.0, noise_std, v.shape).astype(v.dtype)
            for k, v in weight_delta.items()
        }
        logger.debug("gaussian_noise applied (std=%.2f).", noise_std)
        return attacked


# ---------------------------------------------------------------------------
# Module-level dispatch (from ayush)
# ---------------------------------------------------------------------------

_VALID_TYPES = {m.value for m in AttackType}


def apply_attack(weight_delta: dict, attack_type: str, **kwargs) -> dict:
    """Dispatch to the correct attack method by name.

    Parameters
    ----------
    weight_delta : dict[str, np.ndarray]
    attack_type  : str — one of AttackType values
    **kwargs — forwarded to the selected method

    Returns
    -------
    dict[str, np.ndarray] — poisoned (or clean copy for 'none') weight delta
    """
    atype = attack_type.strip().lower()

    if atype == AttackType.NONE.value:
        return {k: v.copy() for k, v in weight_delta.items()}

    if atype == AttackType.SIGN_FLIP.value:
        return ByzantineAttackSimulator.sign_flipping(weight_delta, **kwargs)

    if atype == AttackType.GRAD_SCALE.value:
        return ByzantineAttackSimulator.gradient_scaling(weight_delta, **kwargs)

    if atype == AttackType.RANDOM_NOISE.value:
        return ByzantineAttackSimulator.random_noise(weight_delta, **kwargs)

    if atype == AttackType.ZERO_GRADIENT.value:
        return ByzantineAttackSimulator.zero_gradient(weight_delta)

    if atype == AttackType.GAUSSIAN_NOISE.value:
        return ByzantineAttackSimulator.gaussian_noise(weight_delta, **kwargs)

    raise ValueError(
        f"Unknown attack_type '{attack_type}'. Valid types: {sorted(_VALID_TYPES)}"
    )


# ---------------------------------------------------------------------------
# Legacy MaliciousTrainer (from akshat — backward compat for WebSocket client)
# ---------------------------------------------------------------------------

class MaliciousTrainer:
    """Sign-flip amplified Byzantine attack with honest training first.
    Trains genuinely, then scales the weight diff by attack_scale.
    """

    def __init__(self, model: nn.Module, global_weights: dict,
                 mu: float = 0.01, lr: float = 0.01, epochs: int = 5,
                 device: str = "cpu", attack_scale: float = -5.0):
        self.model = model
        self.global_weights = global_weights
        self.mu = mu
        self.lr = lr
        self.epochs = epochs
        self.device = device
        self.attack_scale = attack_scale
        self.heartbeat_delay = (0.5, 3.0)

    def _honest_train(self, data_loader) -> dict:
        """Run FedProx training loop honestly. Returns {loss, weight_diff, num_samples}."""
        self.model.to(self.device)
        self.model.train()

        global_tensors = {}
        for name, param in self.model.named_parameters():
            if name in self.global_weights:
                param.data.copy_(torch.tensor(
                    self.global_weights[name], dtype=param.dtype
                ).to(self.device))
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

                if output.dim() == 3:
                    output = output.view(-1, output.size(-1))
                    batch_y = batch_y.view(-1)

                ce_loss = criterion(output, batch_y)

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

        weight_diff = {}
        for name, param in self.model.named_parameters():
            if name in self.global_weights:
                weight_diff[name] = param.data.cpu().numpy() - self.global_weights[name]

        avg_loss = total_loss / max(total_samples, 1)
        return {"loss": avg_loss, "weight_diff": weight_diff, "num_samples": total_samples}

    async def train(self, data_loader) -> dict:
        """Async training: honest train -> apply sign-flip -> return corrupted result."""
        result = await asyncio.to_thread(self._honest_train, data_loader)

        corrupted_diff = {
            key: val * self.attack_scale
            for key, val in result["weight_diff"].items()
        }

        logger.info("MaliciousTrainer: applied sign-flip attack (scale=%.1f)", self.attack_scale)

        delay = random.uniform(*self.heartbeat_delay)
        await asyncio.sleep(delay)

        return {
            "loss": result["loss"],
            "local_loss": result["loss"],
            "weight_diff": corrupted_diff,
            "num_samples": result["num_samples"],
        }
