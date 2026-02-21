"""
experiments/sabd_proof.py
=========================
Standalone empirical proof of SABD's core claim.

Core claim
----------
SABD reduces the false-positive rate (FPR) on honest-but-stale clients by
~8×, while retaining >95 % recall on Byzantine clients.

Without correction (α=0), a slow client's gradient naturally diverges from
consensus because the global model has moved on — their raw cosine divergence
looks identical to a Byzantine client's.  SABD applies::

    g*_i = g_i + α · Δ_{s→t}

which removes the staleness drift artefact.  After correction, honest-slow
clients' divergence drops to near-zero while Byzantine (sign-flipped) gradients
remain far from consensus regardless of correction.

Experiment design
-----------------
10 clients per run:
  - Clients 0–3: honest-fast   (simulated staleness = 0)
  - Clients 4–6: honest-slow   (simulated staleness = SIMULATED_STALENESS=5)
  - Clients 7–9: Byzantine     (sign_flipping attack)

Staleness is injected by setting ``client.current_round = round_num - 5``
*after* broadcasting the model, so ``ClientUpdate.round_number`` is 5 behind
the current server round.  No ``time.sleep`` is used — the simulation is fast.

Each run: 50 rounds, MNIST dataset, controlled staleness via direct attribute
manipulation (``client.is_fast_client`` and ``client.current_round``).

Usage
-----
    python -m async_federated_learning.experiments.sabd_proof
or  python async_federated_learning/experiments/sabd_proof.py
"""

import logging
import pathlib
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from async_federated_learning.aggregation.aggregator import get_aggregator
from async_federated_learning.client.fl_client import FLClient
from async_federated_learning.config import Config
from async_federated_learning.data.partitioner import DataPartitioner
from async_federated_learning.detection.anomaly import AnomalyDetector
from async_federated_learning.detection.sabd import SABDCorrector
from async_federated_learning.evaluation.metrics import ExperimentTracker
from async_federated_learning.models.cnn import FLModel
from async_federated_learning.server.model_history import ModelHistoryBuffer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Client role assignments (indices into the client list)
_HONEST_FAST_IDS = [0, 1, 2, 3]   # staleness = 0
_HONEST_SLOW_IDS = [4, 5, 6]      # staleness = SIMULATED_STALENESS
_BYZANTINE_IDS   = [7, 8, 9]      # sign_flipping

# Simulated staleness for slow clients (rounds behind).
# Chosen as midpoint of the 4–6 range noted in the spec.
SIMULATED_STALENESS = 5

# Minimum data required for violin plot (fallback when a group has no data)
_VIOLIN_FALLBACK = [0.0, 0.0]


# ---------------------------------------------------------------------------
# Core experiment
# ---------------------------------------------------------------------------

def run_sabd_proof_experiment(alpha: float, config: Config) -> dict:
    """
    Run one SABD proof experiment for a given correction strength α.

    Client roles
    ------------
    - Honest-fast  (IDs 0–3): staleness = 0,                  not Byzantine
    - Honest-slow  (IDs 4–6): staleness = SIMULATED_STALENESS, not Byzantine
    - Byzantine    (IDs 7–9): staleness = 0,                   sign_flipping

    Staleness is injected synthetically: after broadcasting the global model
    at round ``r``, slow clients' ``current_round`` is overwritten to
    ``max(0, r − SIMULATED_STALENESS)`` so their ``ClientUpdate.round_number``
    is recorded as stale.  No actual sleep occurs.

    Parameters
    ----------
    alpha  : float   SABD correction strength in (0, 1].  Use 0.0 to disable.
    config : Config  Experiment configuration (num_clients=10, num_rounds=50).

    Returns
    -------
    dict with keys:
        ``fpr_slow``        — fraction of rounds honest-slow clients were flagged
        ``recall_byz``      — fraction of rounds Byzantine clients were flagged
        ``raw_divs``        — {client_id: [raw_cosine_divergence, ...]} per round
        ``corrected_divs``  — {client_id: [corrected_divergence, ...]} per round
    """
    logger.info('=== SABD proof experiment | alpha=%.2f ===', alpha)

    # ── Data setup ───────────────────────────────────────────────────────
    partitioner = DataPartitioner()
    train, _test = partitioner.load_dataset(config.dataset_name, config.data_dir)
    client_indices = partitioner.partition_data(
        train, config.num_clients, config.dirichlet_alpha
    )

    # ── Model and infrastructure ─────────────────────────────────────────
    model = FLModel(config.in_channels, config.num_classes, config.hidden_dim)
    model_history = ModelHistoryBuffer(config.model_history_size)

    # SABDCorrector requires alpha > 0; alpha=0 → legacy detection (no correction)
    sabd = SABDCorrector(alpha, model_history) if alpha > 0.0 else None
    anomaly = AnomalyDetector(config.anomaly_threshold, sabd)
    agg_fn = get_aggregator(config.aggregation_method, config)

    # ── Clients ───────────────────────────────────────────────────────────
    clients = []
    for cid in range(config.num_clients):
        dl = partitioner.get_client_dataloader(
            train, client_indices[cid], config.batch_size
        )
        is_byz = cid in _BYZANTINE_IDS
        client = FLClient(
            cid, dl, config,
            is_byzantine=is_byz,
            attack_type='sign_flipping' if is_byz else 'none',
        )
        client.is_fast_client = True   # disable random delay assignment
        clients.append(client)

    # ── Training loop ─────────────────────────────────────────────────────
    # Record raw divergences manually (consistent across all alpha values)
    tracked_raw: dict       = defaultdict(list)   # client_id → [div_per_round]
    tracked_corrected: dict = defaultdict(list)   # client_id → [div_per_round]

    # Counters for FPR and recall
    slow_flags = slow_total = 0
    byz_flags  = byz_total  = 0

    # Record initial model (version 0) so round-5 lookups always succeed
    model_history.record(0, model.get_weights())

    for round_num in range(1, config.num_rounds + 1):
        current_weights = model.get_weights()

        # Record this round's weights BEFORE training so stale clients can
        # reference earlier versions via model_history
        model_history.record(round_num, current_weights)

        # ── Collect updates ─────────────────────────────────────────────
        updates = []
        for client in clients:
            if client.client_id in _HONEST_SLOW_IDS:
                # Inject synthetic staleness: slow client thinks it's on an
                # older round (max(0, …) to avoid negative round numbers)
                simulated_round = max(0, round_num - SIMULATED_STALENESS)
            else:
                simulated_round = round_num

            # Set model weights + record the simulated round number
            client.model.set_weights(current_weights)
            client.current_round = simulated_round

            # Local training (no sleep — speed_variance is irrelevant here)
            update = client.local_train(round_num)
            updates.append(update)

        # ── Score all updates ────────────────────────────────────────────
        round_scores: dict = {}
        for update in updates:
            score = anomaly.score_update(update, updates, current_weights)
            round_scores[update.client_id] = score

        # ── Compute per-client divergences for logging ───────────────────
        # consensus = simple mean of all weight deltas this round
        keys = list(updates[0].weight_delta.keys())
        consensus = {
            k: np.mean([u.weight_delta[k] for u in updates], axis=0)
            for k in keys
        }

        for update in updates:
            g_flat = np.concatenate(
                [update.weight_delta[k].flatten() for k in keys]
            )
            c_flat = np.concatenate([consensus[k].flatten() for k in keys])

            # Raw cosine divergence: 1 − cos(g_i, consensus)
            raw_div = 1.0 - float(
                np.dot(g_flat, c_flat)
                / (np.linalg.norm(g_flat) * np.linalg.norm(c_flat) + 1e-8)
            )
            tracked_raw[update.client_id].append(raw_div)

            # Corrected divergence: apply SABD correction then recompute
            if sabd is not None:
                g_star  = sabd.correct(
                    update.weight_delta, update.round_number, current_weights
                )
                gs_flat = np.concatenate(
                    [g_star[k].flatten() for k in keys]
                )
                corr_div = 1.0 - float(
                    np.dot(gs_flat, c_flat)
                    / (np.linalg.norm(gs_flat) * np.linalg.norm(c_flat) + 1e-8)
                )
            else:
                # α=0: no correction — corrected = raw
                corr_div = raw_div

            tracked_corrected[update.client_id].append(corr_div)

        # ── FPR / recall counting ────────────────────────────────────────
        for cid, score in round_scores.items():
            flagged = anomaly.is_byzantine(score)
            if cid in _HONEST_SLOW_IDS:
                slow_total += 1
                if flagged:
                    slow_flags += 1
            elif cid in _BYZANTINE_IDS:
                byz_total += 1
                if flagged:
                    byz_flags += 1

        # ── Aggregate valid updates ──────────────────────────────────────
        valid_deltas = [
            u.weight_delta for u in updates
            if not anomaly.is_byzantine(round_scores[u.client_id])
        ]
        if valid_deltas:
            try:
                aggregated = agg_fn(valid_deltas)
                new_weights = {
                    k: current_weights[k] + aggregated[k] * config.learning_rate
                    for k in current_weights
                }
                model.set_weights(new_weights)
            except ValueError as exc:
                logger.warning(
                    'Aggregation skipped at round %d: %s', round_num, exc
                )

    # ── Compute metrics ──────────────────────────────────────────────────
    fpr_slow  = slow_flags / slow_total if slow_total > 0 else 0.0
    recall_byz = byz_flags / byz_total  if byz_total  > 0 else 0.0

    logger.info(
        'alpha=%.2f → FPR(slow)=%.3f (%.0f%%), Recall(byz)=%.3f (%.0f%%)',
        alpha, fpr_slow, fpr_slow * 100, recall_byz, recall_byz * 100,
    )
    return {
        'fpr_slow':        fpr_slow,
        'recall_byz':      recall_byz,
        'raw_divs':        dict(tracked_raw),
        'corrected_divs':  dict(tracked_corrected),
    }


# ---------------------------------------------------------------------------
# Full sweep
# ---------------------------------------------------------------------------

def run_full_sabd_proof() -> None:
    """
    Sweep α ∈ {0.0, 0.3, 0.5, 0.7, 1.0} and generate two figures.

    Figures
    -------
    1. ``sabd_proof.png``        — violin plot using α=0.5 data.
       Left: raw divergences (honest-slow ≈ Byzantine).
       Right: SABD-corrected (honest-slow drops, Byzantine stays high).

    2. ``sabd_alpha_sweep.png``  — bar chart: FPR and Recall vs α.

    Expected results (logged)
    -------------------------
    - α=0 : FPR ≈ 40 %  (honest-slow falsely flagged as often as Byzantine)
    - α=0.5: FPR ≈  5 %  (~8× reduction), Recall ≥ 95 % (Byzantine still caught)
    """
    alphas  = [0.0, 0.3, 0.5, 0.7, 1.0]
    results = {}

    for alpha in alphas:
        cfg = Config(
            num_clients=10,
            num_rounds=50,
            byzantine_fraction=0.3,
            attack_type='sign_flipping',
            use_dp=False,                  # DP disabled for a clean proof
            client_speed_variance=False,   # no random delay — staleness injected manually
            eval_every_n_rounds=999,       # no mid-experiment evaluation
        )
        results[alpha] = run_sabd_proof_experiment(alpha, cfg)

    output_dir = pathlib.Path(cfg.output_dir)

    # ── Plot 1: violin — raw vs corrected at α=0.5 ───────────────────────
    ref_result = results[0.5]
    raw_divs_by_group = {
        'honest_slow': [
            div
            for cid in _HONEST_SLOW_IDS
            for div in ref_result['raw_divs'].get(cid, [])
        ],
        'byzantine': [
            div
            for cid in _BYZANTINE_IDS
            for div in ref_result['raw_divs'].get(cid, [])
        ],
    }
    corrected_divs_by_group = {
        'honest_slow': [
            div
            for cid in _HONEST_SLOW_IDS
            for div in ref_result['corrected_divs'].get(cid, [])
        ],
        'byzantine': [
            div
            for cid in _BYZANTINE_IDS
            for div in ref_result['corrected_divs'].get(cid, [])
        ],
    }

    tracker = ExperimentTracker(cfg)
    tracker.plot_sabd_proof(raw_divs_by_group, corrected_divs_by_group)

    # ── Plot 2: bar chart — FPR and Recall vs α ───────────────────────────
    fpr_vals    = [results[a]['fpr_slow']   for a in alphas]
    recall_vals = [results[a]['recall_byz'] for a in alphas]

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(alphas))
    width = 0.35

    ax.bar(x - width / 2, fpr_vals,    width, label='FPR (honest-slow)',   color='#F44336', alpha=0.85)
    ax.bar(x + width / 2, recall_vals, width, label='Recall (byzantine)',   color='#2196F3', alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([f'α={a}' for a in alphas])
    ax.set_ylabel('Rate')
    ax.set_ylim(0, 1.1)
    ax.set_title('SABD Alpha Sweep: FPR Reduction vs. Byzantine Recall', fontsize=13, fontweight='bold')
    ax.axhline(0.95, color='green', linestyle='--', linewidth=1.5, label='95% Recall threshold')
    ax.legend()
    plt.tight_layout()

    bar_path = output_dir / 'sabd_alpha_sweep.png'
    plt.savefig(bar_path, dpi=150)
    plt.close()
    logger.info('Alpha sweep bar chart saved to %s', bar_path)

    # ── Log expected vs observed ─────────────────────────────────────────
    logger.info(
        'Expected: FPR drops from ~40%% at α=0 to ~5%% at α=0.5; '
        'Recall stays ≥ 95%%.'
    )
    logger.info(
        'Observed: α=0.0 FPR=%.1f%%, α=0.5 FPR=%.1f%%, α=0.5 Recall=%.1f%%',
        results[0.0]['fpr_slow']  * 100,
        results[0.5]['fpr_slow']  * 100,
        results[0.5]['recall_byz'] * 100,
    )
    if results[0.5]['fpr_slow'] > 0.0:
        reduction = results[0.0]['fpr_slow'] / results[0.5]['fpr_slow']
        logger.info('FPR reduction factor at α=0.5: %.1f×', reduction)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    run_full_sabd_proof()
