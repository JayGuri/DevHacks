"""
attacks/byzantine.py
====================
Byzantine attack implementations for adversarial FL experiments.

Contains:
- AttackType enum: canonical names for every supported attack variant.
- ByzantineAttackSimulator: static methods for each attack strategy.
  All methods are pure functions — they never modify their input and always
  return a new dict of numpy arrays.
- apply_attack(): module-level dispatch function used by FLClient.

Byzantine model
---------------
A Byzantine client is one that may send *any* message to the server —
it need not follow the local training protocol at all.  Attacks here are
applied *after* local training and *after* DP noise, modelling a fully
compromised device.

Robustness context
------------------
- sign_flipping  : critically breaks FedAvg; defeatable by coord-median /
                   trimmed-mean when num_byzantine < n/2.
- gradient_scaling: magnitude dominates FedAvg average; trimmed-mean
                   removes it when count < β·n.
- random_noise   : easiest to defend — random vectors cancel in expectation.
- zero_gradient  : free-rider; no convergence damage, fairness violation.
- gaussian_noise : subtler than pure random; adds signal-correlated noise,
                   harder to detect by norm-based filters.
"""

import logging
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class AttackType(Enum):
    """Canonical identifiers for each supported Byzantine attack strategy."""
    NONE           = "none"
    SIGN_FLIP      = "sign_flipping"
    GRAD_SCALE     = "gradient_scaling"
    RANDOM_NOISE   = "random_noise"
    ZERO_GRADIENT  = "zero_gradient"
    GAUSSIAN_NOISE = "gaussian_noise"


class ByzantineAttackSimulator:
    """
    Simulates Byzantine adversaries in federated learning.

    Role in pipeline
    ----------------
    A Byzantine client is one that may transmit *any* message — it is not
    constrained to send the result of honest local training.  In the
    pipeline, these attacks are applied **after** local training and
    **after** differential-privacy noise, modelling a device that was
    fully compromised at the OS/hardware level.

    All methods are ``@staticmethod`` pure functions:
      - They accept a ``weight_delta`` dict and return a **new** dict.
      - The input is **never modified in place**.
      - Shape, keys, and dtype of every returned array match the input.

    Robustness context
    ------------------
    Robust aggregation (trimmed-mean, coordinate-median) can tolerate up to
    ``β·n`` or ``n/2`` Byzantine clients respectively.  Attacks here are
    designed to exceed those thresholds in adversarial experiments.
    """

    @staticmethod
    def sign_flipping(weight_delta: dict, scale: float = 1.0) -> dict:
        """
        Negate every gradient coordinate, optionally scaled.

        The most dangerous known attack: the poisoned update points in the
        *exact opposite direction* from the honest gradient.  Even a small
        fraction of sign-flip clients can collapse FedAvg accuracy to chance
        level (~10 % on CIFAR-10 / MNIST with 10 classes).

        Formula: g_attacker = −g_honest · scale

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]
        scale        : float — amplification factor (default 1.0, i.e. pure negation).

        Returns
        -------
        dict[str, np.ndarray] — new dict; input unchanged.
        """
        attacked = {k: -v * scale for k, v in weight_delta.items()}
        logger.debug(
            "sign_flipping applied (scale=%.2f) — keys: %d", scale, len(attacked)
        )
        return attacked

    @staticmethod
    def gradient_scaling(weight_delta: dict, scale: float = 50.0) -> dict:
        """
        Amplify the gradient by a large scalar factor.

        Direction is correct (honest), but magnitude is so large that it
        numerically dominates the FedAvg weighted average.  Less damaging
        than sign-flip directionally, but devastates convergence via
        large-step overshooting.

        Formula: g_attacker = g_honest · scale

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]
        scale        : float — amplification factor (default 50.0).

        Returns
        -------
        dict[str, np.ndarray] — new dict; input unchanged.
        """
        attacked = {k: v * scale for k, v in weight_delta.items()}
        logger.debug(
            "gradient_scaling applied (scale=%.1f) — L∞ max: %.4f",
            scale,
            max(float(np.abs(v).max()) for v in attacked.values()),
        )
        return attacked

    @staticmethod
    def random_noise(weight_delta: dict, scale: float = 10.0) -> dict:
        """
        Replace the gradient with scaled IID Gaussian noise.

        The simplest attack: the adversary discards local training entirely
        and submits random vectors.  Easiest to defend against because random
        noise cancels in expectation and is detectable by norm/direction filters.

        Formula: g_attacker ~ N(0, scale²·I)  (shape-matched to input)

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]
        scale        : float — std of random noise (default 10.0).

        Returns
        -------
        dict[str, np.ndarray] — new dict; input unchanged.
        """
        attacked = {
            k: np.random.randn(*v.shape).astype(v.dtype) * scale
            for k, v in weight_delta.items()
        }
        logger.debug("random_noise applied (scale=%.1f).", scale)
        return attacked

    @staticmethod
    def zero_gradient(weight_delta: dict) -> dict:
        """
        Return an all-zero update (free-rider / lazy-client attack).

        The adversary contributes nothing to training.  This is a *fairness*
        violation rather than a convergence attack — the global model still
        converges (zero updates are filtered or averaged away), but the
        Byzantine client benefits from the shared model without contributing.

        Formula: g_attacker = 0  (zero tensor, shape-matched)

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]

        Returns
        -------
        dict[str, np.ndarray] — zero arrays; input unchanged.
        """
        attacked = {k: np.zeros_like(v) for k, v in weight_delta.items()}
        logger.debug("zero_gradient applied — all-zero update submitted.")
        return attacked

    @staticmethod
    def gaussian_noise(weight_delta: dict, noise_std: float = 5.0) -> dict:
        """
        Add Gaussian noise *on top of* the honest gradient.

        Subtler than pure random_noise: the poisoned update preserves the
        correct gradient direction under the noise layer, making it harder to
        detect via cosine-similarity or norm-based filters.  This models a
        partially compromised client or a model-poisoning attack that injects
        noise into activations rather than raw gradients.

        Formula: g_attacker = g_honest + N(0, noise_std²·I)

        Parameters
        ----------
        weight_delta : dict[str, np.ndarray]
        noise_std    : float — std of additive noise (default 5.0).

        Returns
        -------
        dict[str, np.ndarray] — new dict; input unchanged.
        """
        attacked = {
            k: v + np.random.normal(0.0, noise_std, v.shape).astype(v.dtype)
            for k, v in weight_delta.items()
        }
        logger.debug("gaussian_noise applied (std=%.2f).", noise_std)
        return attacked


# ---------------------------------------------------------------------------
# Module-level dispatch
# ---------------------------------------------------------------------------

_VALID_TYPES = {m.value for m in AttackType}


def apply_attack(weight_delta: dict, attack_type: str, **kwargs) -> dict:
    """
    Dispatch to the correct ByzantineAttackSimulator method by name.

    Parameters
    ----------
    weight_delta : dict[str, np.ndarray]
        Honest client update (not modified in place).
    attack_type  : str
        One of: ``'none'``, ``'sign_flipping'``, ``'gradient_scaling'``,
        ``'random_noise'``, ``'zero_gradient'``, ``'gaussian_noise'``.
    **kwargs
        Forwarded to the selected attack method (e.g. ``scale=``, ``noise_std=``).

    Returns
    -------
    dict[str, np.ndarray]
        Poisoned (or unmodified for ``'none'``) weight delta.

    Raises
    ------
    ValueError
        If ``attack_type`` is not in the list of valid types.
    """
    atype = attack_type.strip().lower()

    if atype == AttackType.NONE.value:
        # No attack — return a clean copy so callers can safely mutate it
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
        f"Unknown attack_type '{attack_type}'. "
        f"Valid types: {sorted(_VALID_TYPES)}"
    )
