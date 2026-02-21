"""
server/fl_server.py
===================
Asynchronous federated learning server.

Architecture
------------
Clients run in parallel threads within each round.  After training they push
their ``ClientUpdate`` objects into a thread-safe ``queue.Queue``.  At the end
of every round the server drains the queue, filters stale / Byzantine updates,
weights survivors by staleness + dataset size, and aggregates with the
configured strategy.

Threading model
---------------
``_model_lock`` protects all reads and writes of ``self.model``.  The lock is
held for the *minimum* duration required:

- ``get_global_weights()`` — acquire, copy, release.
- ``_apply_delta()``       — acquire, update, record in history, release.

NEVER hold ``_model_lock`` while calling any other lock-acquiring function
(``model_history.record``, aggregation, etc.) — deadlock risk.

Staleness weighting
-------------------
A client whose update is d rounds stale receives a soft downweight::

    w_staleness(d) = 1 / (1 + d · penalty_factor)

staleness=0 → weight=1.0
staleness=2, penalty=0.5 → weight=0.5
staleness=∞ → weight→0

The combined weight before normalisation is::

    w_i = w_staleness(d_i) · num_samples_i

so larger, more timely clients dominate the aggregate.

SABD / Anomaly integration
--------------------------
``AnomalyDetector.score_update`` is called per update before adding to the
valid list.  The detector internally calls ``SABDCorrector.correct`` (if
attached) so the cosine divergence signal is staleness-corrected.  Updates
flagged as Byzantine are discarded.
"""

import logging
import queue
import threading

import numpy as np
import torch

from async_federated_learning.aggregation.aggregator import get_aggregator
from async_federated_learning.client.fl_client import ClientUpdate
from async_federated_learning.config import Config
from async_federated_learning.detection.anomaly import AnomalyDetector
from async_federated_learning.models.cnn import FLModel, evaluate_model
from async_federated_learning.server.model_history import ModelHistoryBuffer

logger = logging.getLogger(__name__)


class AsyncFLServer:
    """
    Asynchronous federated learning server.

    One global round consists of:
    1. Broadcast current global weights to all clients.
    2. Spawn one thread per client; each thread calls
       ``client.simulate_network_delay()`` then ``client.local_train()``.
    3. Join all threads (async arrival is modelled by the variable delay).
    4. Drain the update queue, filter stale / Byzantine, aggregate.
    5. Optionally evaluate on the test set every N rounds.

    Parameters
    ----------
    model            : FLModel          The global model instance.
    config           : Config           Experiment configuration.
    test_dataloader  : DataLoader       Held-out test set.
    model_history    : ModelHistoryBuffer
        Rolling weight snapshot buffer (used by SABD for drift computation).
    anomaly_detector : AnomalyDetector
        Composite Byzantine detector (SABD-aware when a corrector is attached).
    """

    def __init__(
        self,
        model: FLModel,
        config: Config,
        test_dataloader,
        model_history: ModelHistoryBuffer,
        anomaly_detector: AnomalyDetector,
    ):
        self.model = model
        self.config = config
        self.test_dataloader = test_dataloader
        self.model_history = model_history
        self.anomaly_detector = anomaly_detector
        self.aggregation_fn = get_aggregator(config.aggregation_method, config)

        self.global_round: int = 0
        self.update_queue: queue.Queue = queue.Queue()
        self._model_lock = threading.Lock()

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Accumulated metrics across rounds
        self.metrics_history: dict = {
            "round": [],
            "accuracy": [],
            "loss": [],
            "num_processed": [],
            "num_discarded": [],
            "avg_staleness": [],
            "byzantine_detected": [],
        }

        logger.info(
            "AsyncFLServer initialised — aggregation=%s, device=%s.",
            config.aggregation_method, self.device,
        )

    # ------------------------------------------------------------------
    # Thread-safe model access
    # ------------------------------------------------------------------

    def get_global_weights(self) -> dict:
        """
        Return a copy of the current global model weights.

        Thread-safe: acquires ``_model_lock`` for the duration of the copy.
        """
        with self._model_lock:
            return self.model.get_weights()

    # ------------------------------------------------------------------
    # Update ingestion
    # ------------------------------------------------------------------

    def receive_update(self, update: ClientUpdate) -> None:
        """
        Enqueue a client update for processing at the next aggregation step.

        Non-blocking (``put_nowait``).  Called from client threads.
        """
        self.update_queue.put_nowait(update)
        logger.debug(
            "Queued update from client %d (round %d).",
            update.client_id, update.round_number,
        )

    # ------------------------------------------------------------------
    # Staleness helpers
    # ------------------------------------------------------------------

    def compute_staleness(self, update: ClientUpdate) -> int:
        """
        Return the staleness of an update in rounds.

        staleness = global_round − update.round_number
        """
        return self.global_round - update.round_number

    def staleness_weight(self, staleness: int) -> float:
        """
        Smooth exponential-like staleness discount.

        Formula::

            w(d) = 1 / (1 + d · penalty_factor)

        staleness=0 → 1.0 (no penalty).
        staleness=∞ → 0.0 (fully discounted).

        Parameters
        ----------
        staleness : int   Round gap between client start and current server round.

        Returns
        -------
        float   Weight in (0, 1].
        """
        # w(d) = 1 / (1 + d · penalty_factor)
        return 1.0 / (1.0 + staleness * self.config.staleness_penalty_factor)

    # ------------------------------------------------------------------
    # Core aggregation
    # ------------------------------------------------------------------

    def aggregate_pending_updates(self) -> tuple:
        """
        Drain the update queue, filter, score, and aggregate.

        Steps
        -----
        1. Drain all items currently in the queue into ``pending``.
        2. For each update:
           a. Compute staleness; discard if > ``config.max_staleness``.
           b. Score with ``AnomalyDetector``; discard if Byzantine.
           c. Otherwise add to ``valid`` list with its staleness.
        3. GUARD: if ``valid`` is empty, skip aggregation and return zeros.
        4. Compute combined weight = staleness_weight × num_samples, normalise.
        5. Call ``aggregation_fn`` on the surviving deltas.
        6. Apply the aggregated delta to the global model.

        Returns
        -------
        tuple[int, int, float]
            ``(num_processed, num_discarded, avg_staleness)``
        """
        # ── Step 1: drain queue ─────────────────────────────────────────
        pending = []
        while not self.update_queue.empty():
            try:
                pending.append(self.update_queue.get_nowait())
            except queue.Empty:
                break

        if not pending:
            logger.warning("aggregate_pending_updates — queue was empty.")
            return (0, 0, 0.0)

        # Get current weights once (used by AnomalyDetector / SABD)
        current_weights = self.get_global_weights()

        valid = []       # list of (ClientUpdate, staleness)
        discarded = 0
        staleness_vals = []

        # ── Steps 2a-2c: filter ─────────────────────────────────────────
        for update in pending:
            staleness = self.compute_staleness(update)
            update.staleness = staleness

            if staleness > self.config.max_staleness:
                logger.warning(
                    "Discarding stale update from client %d (staleness=%d > max=%d).",
                    update.client_id, staleness, self.config.max_staleness,
                )
                discarded += 1
                continue

            score = self.anomaly_detector.score_update(update, pending, current_weights)
            if self.anomaly_detector.is_byzantine(score):
                logger.warning(
                    "Flagged client %d as Byzantine (score=%.3f > threshold=%.3f).",
                    update.client_id, score, self.anomaly_detector.threshold,
                )
                discarded += 1
                continue

            valid.append((update, staleness))
            staleness_vals.append(staleness)

        # ── Step 3: guard ───────────────────────────────────────────────
        if not valid:
            logger.warning(
                "No valid updates this round. Skipping aggregation "
                "(%d discarded).", discarded,
            )
            return (0, discarded, 0.0)

        # ── Step 4: combined weights ─────────────────────────────────────
        # w_i = w_staleness(d_i) · num_samples_i
        raw_weights = [
            self.staleness_weight(s) * u.num_samples
            for u, s in valid
        ]
        total = sum(raw_weights)
        norm_weights = [w / total for w in raw_weights]

        # ── Step 5: aggregate ───────────────────────────────────────────
        deltas = [u.weight_delta for u, _ in valid]
        try:
            aggregated_delta = self.aggregation_fn(deltas, weights=norm_weights)
        except ValueError as exc:
            # trimmed_mean raises ValueError when 2k >= n (too few survivors).
            # Fall back to unweighted mean so training continues.
            logger.warning(
                "Aggregation '%s' failed with %d valid updates: %s. "
                "Falling back to unweighted mean.",
                self.config.aggregation_method, len(deltas), exc,
            )
            keys = list(deltas[0].keys())
            aggregated_delta = {
                k: np.mean([d[k] for d in deltas], axis=0) for k in keys
            }

        # ── Step 6: apply ───────────────────────────────────────────────
        self._apply_delta(aggregated_delta)

        avg_stale = float(np.mean(staleness_vals)) if staleness_vals else 0.0
        logger.info(
            "Round %d aggregation — processed=%d, discarded=%d, avg_staleness=%.2f.",
            self.global_round, len(valid), discarded, avg_stale,
        )
        return (len(valid), discarded, avg_stale)

    def _apply_delta(self, aggregated_delta: dict) -> None:
        """
        Apply the aggregated delta to the global model and record in history.

        Formula::

            θ_{t+1}[k] = θ_t[k] + lr · Δ_agg[k]

        Thread-safe: ``_model_lock`` is held for the full read-update-write
        cycle so no other thread can observe a partially updated model.
        The history record is made *inside* the lock so the stored version
        is exactly the model that clients will receive next round.
        """
        with self._model_lock:
            current = self.model.get_weights()
            # θ_{t+1}[k] = θ_t[k] + lr · Δ_agg[k]
            updated = {
                k: current[k] + aggregated_delta[k] * self.config.learning_rate
                for k in current
            }
            self.model.set_weights(updated)
            # History recording is done at the START of run_round (before training)
            # so SABD can look up the version clients trained on.  No record here.

        logger.debug(
            "_apply_delta — round %d model updated and applied.",
            self.global_round,
        )

    # ------------------------------------------------------------------
    # Round orchestration
    # ------------------------------------------------------------------

    def run_round(self, clients: list) -> dict:
        """
        Execute one complete global round.

        Sequence
        --------
        1. Increment ``global_round``.
        2. Broadcast current global weights to every client.
        3. Spawn one thread per client (delay + train + enqueue).
        4. Join all threads.
        5. Aggregate pending updates.
        6. Evaluate every ``eval_every_n_rounds`` rounds.

        Parameters
        ----------
        clients : list[FLClient]   All clients participating this round.

        Returns
        -------
        dict   Per-round metrics snapshot.
        """
        self.global_round += 1
        logger.info("=== Starting round %d ===", self.global_round)

        # ── Step 2: broadcast ───────────────────────────────────────────
        global_weights = self.get_global_weights()

        # Record the model that clients will train on under version global_round.
        # SABDCorrector.correct() looks up update.round_number in the history to
        # compute drift Δ_{s→t}.  Recording HERE (before training) means version r
        # = θ_r = the weights clients received this round, so:
        #   - staleness-0 clients: drift = θ_r − θ_r = 0  (no correction, correct)
        #   - stale clients (round_number = r−d): drift = θ_r − θ_{r−d}  (correct)
        # If we recorded AFTER aggregation instead, clients' round_number r would
        # not be in the buffer yet when score_update() is called, causing warnings.
        self.model_history.record(self.global_round, global_weights)

        for client in clients:
            client.receive_global_model(global_weights, self.global_round)

        # ── Steps 3–4: parallel client execution ─────────────────────────
        threads = []

        def client_task(c):
            c.simulate_network_delay()
            update = c.local_train(self.global_round)
            self.receive_update(update)

        for client in clients:
            t = threading.Thread(
                target=client_task,
                args=(client,),
                name=f"client-{client.client_id}",
                daemon=True,
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # ── Step 5: aggregate ───────────────────────────────────────────
        processed, discarded, avg_stale = self.aggregate_pending_updates()

        # Update metrics history
        self.metrics_history["num_processed"].append(processed)
        self.metrics_history["num_discarded"].append(discarded)
        self.metrics_history["avg_staleness"].append(avg_stale)

        round_metrics: dict = {
            "round": self.global_round,
            "processed": processed,
            "discarded": discarded,
            "avg_staleness": avg_stale,
        }

        # ── Step 6: evaluation ──────────────────────────────────────────
        if self.global_round % self.config.eval_every_n_rounds == 0:
            acc, loss = self.evaluate_and_log()
            round_metrics["accuracy"] = acc
            round_metrics["loss"] = loss

        return round_metrics

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate_and_log(self) -> tuple:
        """
        Evaluate the global model on the held-out test set.

        Creates a *fresh* ``FLModel`` instance for evaluation to avoid any
        interference with the server's live model during concurrent operations.
        Appends results to ``metrics_history``.

        Returns
        -------
        tuple[float, float]   ``(accuracy, avg_loss)``
        """
        eval_model = FLModel(
            self.config.in_channels,
            self.config.num_classes,
            self.config.hidden_dim,
        ).to(self.device)

        current_weights = self.get_global_weights()
        eval_model.set_weights(current_weights)

        acc, loss = evaluate_model(eval_model, self.test_dataloader, self.device)

        self.metrics_history["round"].append(self.global_round)
        self.metrics_history["accuracy"].append(acc)
        self.metrics_history["loss"].append(loss)

        logger.info(
            "Round %d evaluation — accuracy=%.4f, loss=%.4f.",
            self.global_round, acc, loss,
        )
        return acc, loss

    # ------------------------------------------------------------------
    # Metrics retrieval
    # ------------------------------------------------------------------

    def get_metrics(self) -> dict:
        """Return the full accumulated metrics history across all rounds."""
        return self.metrics_history
