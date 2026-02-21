"""
server/model_history.py
=======================
Rolling buffer of versioned global model snapshots for the async FL server.

Contains:
- ModelHistoryBuffer: fixed-capacity dict-backed buffer keyed by integer
  version_id.  Used by SABD to compute the per-parameter drift
  Δ_{s→t} = θ_t − θ_s between a client's base version and the current
  global model, enabling staleness-aware Byzantine scoring.
"""

import logging
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)


class ModelHistoryBuffer:
    """
    Rolling buffer of versioned global model snapshots.

    Role in pipeline
    ----------------
    The FLServer calls ``record()`` after every aggregation round, storing a
    copy of the new global model weights.  When a client update arrives with
    a ``base_version`` tag, SABD calls ``get_drift(base_version, current_weights)``
    to retrieve the parameter drift Δ_{s→t} = θ_t − θ_s.  This drift
    measures how far the global model has moved since the client last
    synchronised and is used to discount stale or Byzantine updates.

    Design
    ------
    Capacity is bounded by ``max_size``.  Once full, the *oldest* snapshot is
    evicted before a new one is inserted (FIFO via ``collections.deque``).
    Weights are stored as deep copies so subsequent in-place modifications to
    the caller's tensors do not corrupt the history.

    Parameters
    ----------
    max_size : int
        Maximum number of model snapshots to retain.  Corresponds to
        ``Config.model_history_size`` (default 15).
    """

    def __init__(self, max_size: int) -> None:
        # version_id (int) → weights snapshot (dict[str, np.ndarray])
        self._history: dict = {}
        # Ordered insertion record; maxlen enforces capacity at append time
        self._order: deque = deque(maxlen=max_size)
        self.max_size = max_size
        self.logger = logging.getLogger(__name__)
        self.logger.debug("ModelHistoryBuffer initialised (max_size=%d).", max_size)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record(self, version_id: int, weights_dict: dict) -> None:
        """
        Snapshot and store the global model at ``version_id``.

        If the buffer is already at capacity (``len(self) == max_size``), the
        oldest snapshot is evicted from ``_history`` before the new one is
        inserted.  The eviction is driven by ``_order``'s ``maxlen`` — when a
        new element is appended to a full deque, the leftmost element is
        automatically dropped, and we mirror that eviction in ``_history``.

        Parameters
        ----------
        version_id   : int  — typically the global round number.
        weights_dict : dict[str, np.ndarray] — current global model weights.
        """
        # Evict oldest if at capacity (deque.append with maxlen handles _order)
        if len(self._history) >= self.max_size:
            oldest = self._order[0]   # leftmost = oldest; will be dropped by deque
            del self._history[oldest]
            self.logger.debug(
                "Evicted model snapshot version %d from history.", oldest
            )

        # Deep copy: callers may mutate their weights_dict without corrupting history
        self._history[version_id] = {k: v.copy() for k, v in weights_dict.items()}
        self._order.append(version_id)    # may drop oldest from left if maxlen reached

        self.logger.info(
            "Recorded model version %d. Buffer size: %d / %d.",
            version_id, len(self._history), self.max_size,
        )

    def get_drift(self, from_version: int, to_weights: dict) -> dict:
        """
        Compute the per-parameter drift from a historical snapshot to current weights.

        Drift formula used by SABD::

            Δ_{s→t}[k] = θ_t[k] − θ_s[k]   for each parameter key k

        where s = ``from_version`` (client's base version) and t = current round.
        Large drift indicates the global model has evolved significantly since
        the client's update was computed, implying high staleness.

        Parameters
        ----------
        from_version : int
            Version ID the client trained on (its ``base_version`` tag).
        to_weights   : dict[str, np.ndarray]
            Current global model weights (θ_t).

        Returns
        -------
        dict[str, np.ndarray]
            Parameter-wise signed drift arrays.

        Raises
        ------
        ValueError
            If ``from_version`` has been evicted from the buffer or was never
            recorded.  SABD should fall back to treating the update as maximally
            stale in this case.
        """
        if from_version not in self._history:
            available = sorted(self._history.keys())
            raise ValueError(
                f"Model version {from_version} is not in the history buffer. "
                f"Available versions: {available}. "
                f"The snapshot may have been evicted (max_size={self.max_size}). "
                "Consider increasing Config.model_history_size."
            )

        base = self._history[from_version]
        # Δ_{s→t}[k] = θ_t[k] − θ_s[k]
        drift = {k: to_weights[k] - base[k] for k in to_weights}

        drift_norm = float(
            np.sqrt(sum(np.sum(d ** 2) for d in drift.values()))
        )
        self.logger.debug(
            "Drift from version %d → current: L2 norm = %.6f", from_version, drift_norm
        )
        return drift

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def has_version(self, version_id: int) -> bool:
        """Return True if ``version_id`` is currently in the buffer."""
        return version_id in self._history

    def get_oldest_version(self) -> int | None:
        """
        Return the version_id of the oldest retained snapshot, or None if empty.

        The oldest version is the first element of ``_order`` (leftmost = FIFO head).
        Staleness of a client update relative to the oldest retained snapshot can
        be computed as ``current_version - get_oldest_version()``.
        """
        return self._order[0] if self._order else None

    def get_latest_version(self) -> int | None:
        """
        Return the version_id of the most recently recorded snapshot, or None.

        This should equal the server's current global round number after every
        round's ``record()`` call.
        """
        return self._order[-1] if self._order else None

    def __len__(self) -> int:
        """Number of snapshots currently held in the buffer."""
        return len(self._history)

    def __repr__(self) -> str:
        return (
            f"ModelHistoryBuffer(max_size={self.max_size}, "
            f"len={len(self)}, "
            f"versions={list(self._order)})"
        )
