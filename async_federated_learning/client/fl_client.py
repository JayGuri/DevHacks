"""
client/fl_client.py
===================
Federated learning client: trains locally on private data, returns weight delta.

Design notes
------------
Byzantine behaviour is injected *after* DP to model a compromised device that
runs differential privacy correctly but then corrupts the clipped-and-noised
result before transmission.  This preserves the DP guarantee for honest
clients (the mechanism itself is uncompromised) while still modelling a
realistic threat: a device whose OS/firmware is compromised *after* the local
DP step.

The ``is_byzantine`` field in ``ClientUpdate`` is for evaluation logging only.
The server NEVER reads or branches on it — doing so would be oracle cheating.

Staleness mechanism
-------------------
``receive_global_model`` stores the round number at which the client received
the model (``self.current_round``).  ``ClientUpdate.round_number`` is set to
this value.  The server computes staleness as::

    staleness = global_round − update.round_number

Slow clients (``is_fast_client=False``) sleep 1–3 s versus 0–0.5 s for fast
clients, simulating the straggler problem that is the root cause of staleness
in async FL.
"""

import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn

from async_federated_learning.attacks.byzantine import apply_attack
from async_federated_learning.config import Config
from async_federated_learning.models.cnn import FLModel
from async_federated_learning.privacy.dp import DifferentialPrivacyMechanism

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer object returned by every local_train() call
# ---------------------------------------------------------------------------

@dataclass
class ClientUpdate:
    """
    Immutable container for one client's training result.

    Fields
    ------
    client_id    : int    Unique identifier for the client.
    weight_delta : dict   ``{param_name: np.ndarray}`` — θ_local − θ_start.
    round_number : int    Global round at which the client *started* training.
                          Used by the server to compute staleness.
    num_samples  : int    Local dataset size; used as aggregation weight.
    training_loss: float  Final mini-batch loss of the last local epoch.
    is_byzantine : bool   Ground-truth label — for evaluation/logging ONLY.
                          The server MUST NOT use this field in any decision.
    staleness    : int    Filled in by the server after receipt (defaults 0).
    """

    client_id: int
    weight_delta: dict          # {param_name: numpy_array}
    round_number: int           # which global round this update is based on
    num_samples: int            # local dataset size (aggregation weight)
    training_loss: float
    is_byzantine: bool          # for evaluation ONLY — server never reads this
    staleness: int = 0          # set by server after receipt


# ---------------------------------------------------------------------------
# FL Client
# ---------------------------------------------------------------------------

class FLClient:
    """
    Federated learning client.

    Responsibilities
    ----------------
    - Receive the current global model from the server (``receive_global_model``).
    - Run E local SGD epochs on the private data shard (``local_train``).
    - Apply DP clipping + noise if ``config.use_dp`` is True.
    - Inject a Byzantine attack *after* DP if the client is malicious.
    - Simulate network delay to model asynchronous arrival patterns.

    Thread safety
    -------------
    Each ``FLClient`` instance is used by exactly one thread (one client task
    per round).  No shared state between clients; no locking required here.

    Parameters
    ----------
    client_id   : int           Unique client identifier.
    dataloader  : DataLoader    Private data shard for this client.
    config      : Config        Global experiment configuration.
    is_byzantine: bool          Whether this client behaves adversarially.
    attack_type : str           Attack name (passed to ``apply_attack``).
                                Ignored when ``is_byzantine=False``.
    """

    def __init__(
        self,
        client_id: int,
        dataloader,
        config: Config,
        is_byzantine: bool = False,
        attack_type: str = "sign_flipping",
    ):
        self.client_id = client_id
        self.dataloader = dataloader
        self.config = config
        self.is_byzantine = is_byzantine
        self.attack_type = attack_type
        self.current_round = 0

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.model = FLModel(
            config.in_channels, config.num_classes, config.hidden_dim
        ).to(self.device)

        # DP mechanism — None when use_dp=False (honest-only baseline)
        self.dp_mechanism: Optional[DifferentialPrivacyMechanism] = (
            DifferentialPrivacyMechanism(
                config.dp_noise_multiplier, config.dp_clip_norm
            )
            if config.use_dp
            else None
        )

        # Straggler model: 70 % fast clients, 30 % slow
        self.is_fast_client: bool = random.random() > 0.3

        # Convenience: store once (dataset size is fixed)
        self.num_samples: int = len(dataloader.dataset)

        logger.info(
            "FLClient %d — byzantine=%s, attack=%s, fast=%s, "
            "samples=%d, dp=%s, device=%s.",
            client_id,
            is_byzantine,
            attack_type if is_byzantine else "N/A",
            self.is_fast_client,
            self.num_samples,
            "on" if self.dp_mechanism is not None else "off",
            self.device,
        )

    # ------------------------------------------------------------------
    # Model synchronisation
    # ------------------------------------------------------------------

    def receive_global_model(self, global_weights: dict, round_number: int) -> None:
        """
        Load the global model weights and record the round number.

        The round number stored here becomes ``ClientUpdate.round_number``,
        which the server uses to compute staleness::

            staleness = server.global_round − update.round_number

        Parameters
        ----------
        global_weights : dict[str, np.ndarray]   Weights from the server.
        round_number   : int                      Current global round.
        """
        self.model.set_weights(global_weights)
        self.current_round = round_number
        logger.debug(
            "Client %d received global model at round %d.", self.client_id, round_number
        )

    # ------------------------------------------------------------------
    # Local training
    # ------------------------------------------------------------------

    def local_train(self, _global_round: int) -> ClientUpdate:
        """
        Run local training and return a ``ClientUpdate``.

        Exact sequence (do NOT reorder):

        1. Save pre-train weights snapshot.
        2. Local SGD for ``config.local_epochs`` epochs.
        3. Compute weight delta:  Δ = θ_local − θ_start.
        4. Apply DP (clip + noise) if enabled.
        5. Inject Byzantine attack (after DP) if malicious.
        6. Build and return ``ClientUpdate``.

        DP before attack rationale
        --------------------------
        This order models a device whose DP mechanism is intact (privacy is
        preserved for the gradient computation step) but whose transmission
        layer is compromised by the attacker.  The alternative order (attack
        then DP) would let DP partially wash out the attack, which is
        unrealistically optimistic.

        Parameters
        ----------
        global_round : int   Current server round (stored in ClientUpdate
                             for the server's staleness calculation).

        Returns
        -------
        ClientUpdate
        """
        # ── Step 1: snapshot pre-train weights ──────────────────────────
        pre_train_weights = self.model.get_weights()

        # ── Step 2: local SGD ───────────────────────────────────────────
        self.model.train()
        optimizer = torch.optim.SGD(
            self.model.parameters(),
            lr=self.config.learning_rate,
            momentum=0.9,
        )
        criterion = torch.nn.CrossEntropyLoss()

        final_loss = 0.0
        for epoch in range(self.config.local_epochs):
            for batch_x, batch_y in self.dataloader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)

                optimizer.zero_grad()
                logits = self.model(batch_x)
                loss = criterion(logits, batch_y)
                loss.backward()
                optimizer.step()
                final_loss = loss.item()

        logger.debug(
            "Client %d — local training done (%d epochs), final_loss=%.4f.",
            self.client_id, self.config.local_epochs, final_loss,
        )

        # ── Step 3: compute weight delta Δ = θ_local − θ_start ─────────
        weight_delta = self.model.get_weight_delta(pre_train_weights)

        # ── Step 4: DP — clip then add noise ────────────────────────────
        if self.dp_mechanism is not None:
            weight_delta = self.dp_mechanism.privatize(weight_delta)
            logger.debug(
                "Client %d — DP applied (clip_norm=%.2f, noise_mult=%.2f).",
                self.client_id,
                self.config.dp_clip_norm,
                self.config.dp_noise_multiplier,
            )

        # ── Step 5: Byzantine attack (after DP) ─────────────────────────
        if self.is_byzantine:
            weight_delta = apply_attack(weight_delta, self.attack_type)
            logger.debug(
                "Client %d — Byzantine attack applied (%s).",
                self.client_id, self.attack_type,
            )

        # ── Step 6: build ClientUpdate ───────────────────────────────────
        return ClientUpdate(
            client_id=self.client_id,
            weight_delta=weight_delta,
            round_number=self.current_round,
            num_samples=self.num_samples,
            training_loss=final_loss,
            is_byzantine=self.is_byzantine,
        )

    # ------------------------------------------------------------------
    # Network simulation
    # ------------------------------------------------------------------

    def simulate_network_delay(self) -> float:
        """
        Block the calling thread to simulate the straggler problem.

        Fast clients (70 %) sleep 0.0–0.5 s.
        Slow clients (30 %) sleep 1.0–3.0 s.

        When ``config.client_speed_variance`` is False, returns 0.0 immediately
        (useful for deterministic test runs).

        Returns
        -------
        float   Actual sleep duration in seconds.
        """
        if not self.config.client_speed_variance:
            return 0.0

        if self.is_fast_client:
            delay = random.uniform(0.0, 0.5)
        else:
            # Slow straggler — creates stale gradients (SABD corrects for this)
            delay = random.uniform(1.0, 3.0)

        time.sleep(delay)
        logger.debug(
            "Client %d — network delay %.2f s (fast=%s).",
            self.client_id, delay, self.is_fast_client,
        )
        return delay
