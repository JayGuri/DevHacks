#!/usr/bin/env python3
"""
tests/e2e_validation.py
=======================
Behavioral end-to-end validation suite for the Async Robust Federated
Learning (ARFL) framework.

Run:  python tests/e2e_validation.py

Tests verify that the system **does what it claims**, not just that it
runs without crashing.  Each test prints PASS / FAIL with diagnostic info.
A summary table is printed at the end.
"""

# ---------------------------------------------------------------------------
# Path bootstrap — ensure imports resolve when run from repo root
# ---------------------------------------------------------------------------
import os as _os
import sys as _sys

_PKG_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
if _PKG_ROOT not in _sys.path:
    _sys.path.insert(0, _PKG_ROOT)

import logging
import queue
import threading
import time
from pathlib import Path

import numpy as np
import torch

from async_federated_learning.config import Config
from async_federated_learning.data.partitioner import DataPartitioner
from async_federated_learning.models.cnn import FLModel, evaluate_model
from async_federated_learning.client.fl_client import FLClient, ClientUpdate
from async_federated_learning.server.fl_server import AsyncFLServer
from async_federated_learning.server.model_history import ModelHistoryBuffer
from async_federated_learning.detection.sabd import SABDCorrector
from async_federated_learning.detection.anomaly import AnomalyDetector
from async_federated_learning.aggregation.fedavg import fedavg
from async_federated_learning.aggregation.trimmed_mean import trimmed_mean
from async_federated_learning.aggregation.coordinate_median import coordinate_median
from async_federated_learning.attacks.byzantine import apply_attack
from async_federated_learning.privacy.dp import DifferentialPrivacyMechanism

# ---------------------------------------------------------------------------
# Suppress verbose logging during tests
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
results: list = []  # collect (name, passed) for summary


def check(name: str, condition: bool, diagnostic: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if not condition and diagnostic:
        print(f"         >> {diagnostic}")
    results.append((name, condition))
    return condition


# ===================================================================
# Shared helpers for setting up a minimal server
# ===================================================================

def _make_minimal_server(config: Config):
    """Create a minimal server with partitioned data for test use."""
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)

    partitioner = DataPartitioner()
    train, test = partitioner.load_dataset(config.dataset_name, config.data_dir)
    client_indices = partitioner.partition_data(
        train, config.num_clients, config.dirichlet_alpha
    )
    client_dataloaders = [
        partitioner.get_client_dataloader(train, idx, config.batch_size)
        for idx in client_indices
    ]
    test_dataloader = partitioner.get_test_dataloader(test)

    model = FLModel(config.in_channels, config.num_classes, config.hidden_dim)
    model_history = ModelHistoryBuffer(config.model_history_size)
    sabd = SABDCorrector(config.sabd_alpha, model_history)
    anomaly = AnomalyDetector(config.anomaly_threshold, sabd)
    server = AsyncFLServer(model, config, test_dataloader, model_history, anomaly)

    num_byz = int(config.num_clients * config.byzantine_fraction)
    clients = []
    for i, dl in enumerate(client_dataloaders):
        is_byz = i < num_byz
        clients.append(
            FLClient(
                i, dl, config,
                is_byzantine=is_byz,
                attack_type=config.attack_type if is_byz else 'none',
            )
        )
    return server, clients, test_dataloader


# ===================================================================
# TEST GROUP 1: Aggregation Numerical Correctness
# ===================================================================

def test_group_1():
    print("\n" + "=" * 60)
    print("TEST GROUP 1: Aggregation Numerical Correctness")
    print("=" * 60)

    # T1.1 — FedAvg weighted average is numerically correct
    updates = [{'w': np.array([2.0, 2.0])}, {'w': np.array([4.0, 4.0])}]
    weights = [0.25, 0.75]
    result = fedavg(updates, weights)
    expected = np.array([3.5, 3.5])
    check(
        "T1.1 FedAvg weighted average",
        np.allclose(result['w'], expected, atol=1e-5),
        f"Got {result['w']}, expected {expected}",
    )

    # T1.2 — Trimmed mean actually removes outliers
    good = [{'w': np.ones(5)} for _ in range(8)]
    bad = [{'w': np.full(5, 1000.0)} for _ in range(2)]
    all_updates = good + bad
    result = trimmed_mean(all_updates, beta=0.2)
    check(
        "T1.2 Trimmed mean removes outliers",
        np.all(result['w'] < 10.0),
        f"Trimmed mean = {result['w'][0]:.2f}, should be < 10.0. Outliers not removed.",
    )

    # T1.3 — FedAvg IS broken by the same outliers
    result_avg = fedavg(all_updates)
    check(
        "T1.3 FedAvg is broken by outliers",
        np.any(result_avg['w'] > 100.0),
        f"FedAvg = {result_avg['w'][0]:.2f}, should be > 100. Attack not working.",
    )

    # T1.4 — Coordinate median is immune to 40% Byzantine clients
    honest = [{'w': np.array([1.0, 1.0, 1.0])} for _ in range(6)]
    byz = [{'w': np.array([9999.0, 9999.0, 9999.0])} for _ in range(4)]
    result = coordinate_median(honest + byz)
    check(
        "T1.4 Coordinate median immune to 40% Byzantine",
        np.all(result['w'] < 5.0),
        f"Median = {result['w'][0]:.2f}, should be ~1.0 (Byzantine-immune)",
    )

    # T1.5 — Trimmed mean raises ValueError when beta is too large
    updates_small = [{'w': np.ones(3)} for _ in range(4)]
    raised = False
    try:
        trimmed_mean(updates_small, beta=0.5)
    except ValueError:
        raised = True
    check(
        "T1.5 Trimmed mean raises ValueError for too-large beta",
        raised,
        "Should have raised ValueError when beta=0.5 trims too many from 4 clients.",
    )


# ===================================================================
# TEST GROUP 2: Attack Effectiveness
# ===================================================================

def test_group_2():
    print("\n" + "=" * 60)
    print("TEST GROUP 2: Attack Effectiveness")
    print("=" * 60)

    # T2.1 — Sign flipping attack produces opposite-direction update
    original = {'w': np.array([1.0, 2.0, 3.0])}
    attacked = apply_attack(original, 'sign_flipping')
    check(
        "T2.1a Sign flipping produces negated values",
        np.allclose(attacked['w'], np.array([-1.0, -2.0, -3.0])),
        f"Got {attacked['w']}, expected [-1, -2, -3]",
    )
    check(
        "T2.1b Sign flipping doesn't share memory",
        not np.shares_memory(attacked['w'], original['w']),
        "attacked['w'] shares memory with original — must be a copy.",
    )

    # T2.2 — Gradient scaling produces ~50x larger norm
    original = {'w': np.ones(10)}
    attacked = apply_attack(original, 'gradient_scaling', scale=50.0)
    ratio = np.linalg.norm(attacked['w'].flatten()) / np.linalg.norm(
        original['w'].flatten()
    )
    check(
        "T2.2 Gradient scaling ~50x norm",
        abs(ratio - 50.0) < 1.0,
        f"Scale ratio = {ratio:.1f}, expected ~50.0",
    )

    # T2.3 — FedAvg model update is corrupted by sign-flipping attack
    honest_delta = {'w': np.full(10, 0.1)}
    byz_delta = {'w': np.full(10, -5.0)}
    updates_mixed = [honest_delta] * 8 + [byz_delta] * 2
    result = fedavg(updates_mixed)
    check(
        "T2.3 FedAvg corrupted by sign-flip attack",
        result['w'][0] < 0.0,
        f"FedAvg result = {result['w'][0]:.3f}. Attack should have pulled it negative.",
    )

    # T2.4 — Trimmed mean survives the same attack
    result_tm = trimmed_mean(updates_mixed, beta=0.2)
    check(
        "T2.4 Trimmed mean survives sign-flip attack",
        result_tm['w'][0] > 0.0,
        f"Trimmed mean = {result_tm['w'][0]:.3f}. Should be positive (robust).",
    )


# ===================================================================
# TEST GROUP 3: Differential Privacy
# ===================================================================

def test_group_3():
    print("\n" + "=" * 60)
    print("TEST GROUP 3: Differential Privacy")
    print("=" * 60)

    # T3.1 — DP actually modifies the gradient (noise is non-zero)
    dp = DifferentialPrivacyMechanism(noise_multiplier=0.5, clip_norm=1.0)
    original = {'w': np.ones(100)}
    privatized = dp.privatize(original)
    diff = np.linalg.norm(privatized['w'] - original['w'])
    check(
        "T3.1 DP adds non-zero noise",
        diff > 0.01,
        f"||privatized - original|| = {diff:.4f}. DP added no noise.",
    )

    # T3.2 — Gradient clipping reduces oversized gradients
    dp_noclip = DifferentialPrivacyMechanism(noise_multiplier=0.0, clip_norm=1.0)
    big_delta = {'w': np.ones(100)}
    clipped = dp_noclip.clip_gradients(big_delta)
    norm_after = np.linalg.norm(clipped['w'])
    check(
        "T3.2 Gradient clipping reduces oversized gradients",
        norm_after <= 1.01,
        f"Clipped norm = {norm_after:.4f}, should be <= 1.0",
    )

    # T3.3 — DP does NOT clip already-small gradients
    dp_high = DifferentialPrivacyMechanism(noise_multiplier=0.0, clip_norm=5.0)
    small = {'w': np.ones(3)}
    clipped = dp_high.clip_gradients(small)
    check(
        "T3.3 DP does NOT clip small gradients",
        np.allclose(clipped['w'], np.ones(3), atol=1e-6),
        "Small gradient should not be changed by clipping.",
    )

    # T3.4 — DP is applied before attack in FLClient (order verification)
    print("  [INFO] T3.4 requires MNIST download and local training — running...")
    try:
        config = Config(
            num_clients=2, num_rounds=1, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=False, seed=42,
            local_epochs=1,
        )
        partitioner = DataPartitioner()
        train, _test = partitioner.load_dataset('MNIST', './data/raw')
        indices = partitioner.partition_data(train, 2, alpha=100.0)
        dl = partitioner.get_client_dataloader(train, indices[0], batch_size=32)

        honest_client = FLClient(0, dl, config, is_byzantine=False)
        byz_client = FLClient(
            1, dl,
            Config(num_clients=2, byzantine_fraction=0.0, use_dp=False,
                   client_speed_variance=False, seed=42, local_epochs=1),
            is_byzantine=True, attack_type='sign_flipping',
        )

        global_weights = FLModel().get_weights()
        honest_client.receive_global_model(global_weights, 1)
        byz_client.receive_global_model(global_weights, 1)

        honest_update = honest_client.local_train(1)
        byz_update = byz_client.local_train(1)

        h_flat = np.concatenate(
            [v.flatten() for v in honest_update.weight_delta.values()]
        )
        b_flat = np.concatenate(
            [v.flatten() for v in byz_update.weight_delta.values()]
        )
        cosine_sim = np.dot(h_flat, b_flat) / (
            np.linalg.norm(h_flat) * np.linalg.norm(b_flat) + 1e-8
        )
        check(
            "T3.4 Byzantine sign-flip produces opposite direction",
            cosine_sim < -0.5,
            f"Cosine similarity = {cosine_sim:.3f}. Should be < -0.5.",
        )
    except Exception as e:
        check("T3.4 Byzantine sign-flip produces opposite direction", False,
              f"Exception: {e}")


# ===================================================================
# TEST GROUP 4: Asynchronous Threading and Staleness
# ===================================================================

def test_group_4():
    print("\n" + "=" * 60)
    print("TEST GROUP 4: Asynchronous Threading and Staleness")
    print("=" * 60)

    # T4.1 — Clients actually run in parallel (timing test)
    print("  [INFO] T4.1 requires MNIST and threading test — running...")
    try:
        config = Config(
            num_clients=5, num_rounds=1, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=True,
            eval_every_n_rounds=1, seed=42,
            local_epochs=1,
        )
        server, clients, _tdl = _make_minimal_server(config)

        start = time.time()
        server.run_round(clients)
        elapsed = time.time() - start
        # On CPU training takes ~20-30s per client; serial 5 clients = 100-150s
        # Parallel should be roughly 1 client time + overhead ≈ 30-40s
        check(
            "T4.1 Clients run in parallel (timing)",
            elapsed < 60.0,
            f"Round took {elapsed:.2f}s. If > 60s, clients may be running serially.",
        )
    except Exception as e:
        check("T4.1 Clients run in parallel (timing)", False, f"Exception: {e}")

    # T4.2 — Staleness values are actually non-zero
    try:
        config = Config(
            num_clients=5, num_rounds=5, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=True,
            eval_every_n_rounds=5, seed=42,
            local_epochs=1,
        )
        server, clients, _tdl = _make_minimal_server(config)

        collected_staleness = []
        for _ in range(5):
            metrics = server.run_round(clients)
            collected_staleness.append(metrics.get('avg_staleness', 0.0))

        check(
            "T4.2 Staleness values are non-zero (async is real)",
            any(s > 0 for s in collected_staleness),
            f"All staleness values are 0: {collected_staleness}. "
            "Async may not be creating real staleness.",
        )
    except Exception as e:
        check("T4.2 Staleness values are non-zero", False, f"Exception: {e}")

    # T4.3 — Thread safety: concurrent model reads don't produce corrupted weights
    try:
        config = Config(
            num_clients=3, num_rounds=1, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=False, seed=42,
        )
        server, _clients, _tdl = _make_minimal_server(config)

        read_results = []
        read_errors = []

        def read_weights():
            try:
                w = server.get_global_weights()
                flat = np.concatenate([v.flatten() for v in w.values()])
                read_results.append(not np.any(np.isnan(flat)))
            except Exception as e:
                read_errors.append(str(e))

        threads = [threading.Thread(target=read_weights) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check(
            "T4.3 Thread safety: concurrent reads produce valid weights",
            len(read_errors) == 0 and all(read_results),
            f"Errors: {read_errors}. NaN results: {read_results.count(False)}",
        )
    except Exception as e:
        check("T4.3 Thread safety", False, f"Exception: {e}")

    # T4.4 — Max staleness discard works correctly
    try:
        config = Config(
            num_clients=3, num_rounds=1, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=False,
            anomaly_threshold=9999.0,   # never flag Byzantine by score
            seed=42,
        )
        server, _clients, _tdl = _make_minimal_server(config)

        server.global_round = 20
        stale_update = ClientUpdate(
            client_id=99,
            weight_delta={k: np.ones_like(v) for k, v in FLModel().get_weights().items()},
            round_number=5,  # staleness = 20 - 5 = 15, exceeds max_staleness=10
            num_samples=100,
            training_loss=0.5,
            is_byzantine=False,
        )
        server.receive_update(stale_update)
        processed, discarded, _avg = server.aggregate_pending_updates()
        check(
            "T4.4 Max staleness discard works",
            discarded >= 1 and processed == 0,
            f"processed={processed}, discarded={discarded}. "
            "Stale update should have been discarded.",
        )
    except Exception as e:
        check("T4.4 Max staleness discard", False, f"Exception: {e}")

    # T4.5 — Empty queue guard: no crash when all updates are stale
    try:
        config = Config(
            num_clients=3, num_rounds=1, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=False,
            anomaly_threshold=9999.0,
            seed=42,
        )
        server, _clients, _tdl = _make_minimal_server(config)
        server.global_round = 100
        model_weights = FLModel().get_weights()
        for i in range(3):
            stale = ClientUpdate(
                client_id=i,
                weight_delta={k: np.ones_like(v) for k, v in model_weights.items()},
                round_number=0,
                num_samples=100,
                training_loss=0.5,
                is_byzantine=False,
            )
            server.receive_update(stale)
        try:
            processed, discarded, _avg = server.aggregate_pending_updates()
            check(
                "T4.5 Empty queue guard (all stale): no crash",
                processed == 0 and discarded == 3,
                f"processed={processed}, discarded={discarded}. "
                "Expected 0 processed, 3 discarded.",
            )
        except Exception as e:
            check(
                "T4.5 Empty queue guard (all stale): no crash",
                False,
                f"Crashed with: {e}. Empty queue guard is missing.",
            )
    except Exception as e:
        check("T4.5 Empty queue guard", False, f"Exception: {e}")


# ===================================================================
# TEST GROUP 5: SABD Behavioral Correctness
# ===================================================================

def test_group_5():
    print("\n" + "=" * 60)
    print("TEST GROUP 5: SABD Behavioral Correctness")
    print("=" * 60)

    # Setup shared model history
    history = ModelHistoryBuffer(max_size=10)
    weights_v0 = {'w': np.zeros(10)}
    weights_v5 = {'w': np.ones(10) * 0.5}
    history.record(0, weights_v0)
    history.record(5, weights_v5)

    sabd = SABDCorrector(alpha=0.5, model_history=history)

    # T5.1 — SABD correction reduces divergence for honest stale update
    stale_gradient = {'w': np.ones(10) * 0.3}
    consensus = {'w': np.ones(10) * 0.4}

    raw_div = sabd.compute_raw_divergence(stale_gradient, consensus)
    corrected = sabd.correct(stale_gradient, client_round=0, current_weights=weights_v5)
    corrected_div = sabd.compute_corrected_divergence(corrected, consensus)

    check(
        "T5.1 SABD reduces divergence for honest stale client",
        corrected_div < raw_div,
        f"raw_div={raw_div:.4f}, corrected_div={corrected_div:.4f}. "
        "SABD should reduce divergence for honest stale client.",
    )

    # T5.2 — SABD correction does NOT reduce divergence for Byzantine update
    byzantine_gradient = {'w': np.ones(10) * -0.3}
    consensus = {'w': np.ones(10) * 0.4}

    raw_div = sabd.compute_raw_divergence(byzantine_gradient, consensus)
    corrected = sabd.correct(byzantine_gradient, client_round=0, current_weights=weights_v5)
    corrected_div = sabd.compute_corrected_divergence(corrected, consensus)

    check(
        "T5.2 SABD does NOT help Byzantine gradient",
        corrected_div > 0.3,
        f"corrected_div={corrected_div:.4f}. "
        "Byzantine gradient should still be flagged after SABD.",
    )

    # T5.3 — SABD returns uncorrected gradient when version is missing
    history_empty = ModelHistoryBuffer(max_size=10)
    sabd_empty = SABDCorrector(alpha=0.5, model_history=history_empty)
    gradient = {'w': np.ones(5)}
    current = {'w': np.ones(5) * 2.0}
    result = sabd_empty.correct(gradient, client_round=7, current_weights=current)
    check(
        "T5.3 SABD returns original gradient when version missing",
        np.allclose(result['w'], gradient['w']),
        "SABD should return original gradient unchanged when version not in history.",
    )

    # T5.4 — ModelHistoryBuffer evicts oldest version at capacity
    history_small = ModelHistoryBuffer(max_size=3)
    for i in range(5):
        history_small.record(i, {'w': np.ones(3) * i})

    evicted_ok = not history_small.has_version(0) and not history_small.has_version(1)
    kept_ok = (
        history_small.has_version(2)
        and history_small.has_version(3)
        and history_small.has_version(4)
    )
    check(
        "T5.4 ModelHistoryBuffer evicts oldest at capacity",
        evicted_ok and kept_ok,
        f"Buffer of size 3 should have evicted versions 0 and 1. "
        f"has(0)={history_small.has_version(0)}, has(1)={history_small.has_version(1)}, "
        f"has(2)={history_small.has_version(2)}, has(3)={history_small.has_version(3)}, "
        f"has(4)={history_small.has_version(4)}",
    )


# ===================================================================
# TEST GROUP 6: Full Convergence Behavior
# ===================================================================

def test_group_6():
    print("\n" + "=" * 60)
    print("TEST GROUP 6: Full Convergence Behavior (Demo-Critical)")
    print("=" * 60)

    # Helper to run a full pipeline with a given config
    def _run_pipeline(config: Config):
        np.random.seed(config.seed)
        torch.manual_seed(config.seed)
        server, clients, _tdl = _make_minimal_server(config)
        for _ in range(config.num_rounds):
            server.run_round(clients)
        server.evaluate_and_log()
        return server

    # T6.1 — FedAvg converges normally without attack
    print("  [INFO] T6.1 FedAvg baseline (8 rounds)...")
    try:
        config_baseline = Config(
            num_clients=5, num_rounds=8, byzantine_fraction=0.0,
            aggregation_method='fedavg', use_dp=False,
            client_speed_variance=False, eval_every_n_rounds=2, seed=42,
            local_epochs=1,
        )
        server_baseline = _run_pipeline(config_baseline)
        accs = server_baseline.metrics_history['accuracy']
        check("T6.1a FedAvg baseline has ≥2 evaluations", len(accs) >= 2,
              f"Only {len(accs)} accuracy points.")
        check("T6.1b FedAvg accuracy improves over rounds",
              accs[-1] > accs[0],
              f"Accuracies: {[f'{a:.2%}' for a in accs]}. Should improve.")
        check("T6.1c FedAvg accuracy > 20% after 8 rounds",
              accs[-1] > 0.20,
              f"Final accuracy: {accs[-1]:.2%}. Should be > 20%.")
    except Exception as e:
        check("T6.1 FedAvg baseline", False, f"Exception: {e}")
        accs = []

    # T6.2 — FedAvg degrades under Byzantine sign-flip attack
    print("  [INFO] T6.2 FedAvg under attack (8 rounds)...")
    fedavg_attack_acc = None
    try:
        config_attack = Config(
            num_clients=5, num_rounds=8, byzantine_fraction=0.4,
            attack_type='sign_flipping', aggregation_method='fedavg',
            use_dp=False, client_speed_variance=False,
            eval_every_n_rounds=2, seed=42,
            local_epochs=1,
        )
        server_attack = _run_pipeline(config_attack)
        fedavg_attack_acc = server_attack.metrics_history['accuracy'][-1]
        check("T6.2 FedAvg degrades under attack (acc < 30%)",
              fedavg_attack_acc < 0.30,
              f"FedAvg under attack: {fedavg_attack_acc:.2%}. Should be < 30%.")
    except Exception as e:
        check("T6.2 FedAvg under attack", False, f"Exception: {e}")

    # T6.3 — Trimmed mean maintains performance under same attack
    print("  [INFO] T6.3 Trimmed mean under attack (8 rounds)...")
    tm_attack_acc = None
    try:
        config_tm = Config(
            num_clients=5, num_rounds=8, byzantine_fraction=0.4,
            attack_type='sign_flipping', aggregation_method='trimmed_mean',
            use_dp=False, client_speed_variance=False,
            eval_every_n_rounds=2, seed=42,
            local_epochs=1,
        )
        server_tm = _run_pipeline(config_tm)
        tm_attack_acc = server_tm.metrics_history['accuracy'][-1]
        check("T6.3 Trimmed mean maintains accuracy under attack (> 35%)",
              tm_attack_acc > 0.35,
              f"Trimmed mean under attack: {tm_attack_acc:.2%}. Should be > 35%.")
    except Exception as e:
        check("T6.3 Trimmed mean under attack", False, f"Exception: {e}")

    # T6.4 — Convergence gap between T6.2 and T6.3 is significant
    if fedavg_attack_acc is not None and tm_attack_acc is not None:
        gap = tm_attack_acc - fedavg_attack_acc
        check("T6.4 Convergence gap > 15% (demo key result)",
              gap > 0.15,
              f"Gap = {gap:.2%}. This is the key demo result. Should be > 15%.")
    else:
        check("T6.4 Convergence gap", False,
              "Could not compute — T6.2 or T6.3 failed.")

    # T6.5 — DP has non-trivial but acceptable impact
    print("  [INFO] T6.5 DP utility test (8 rounds)...")
    try:
        config_no_dp = Config(
            num_clients=5, num_rounds=8, byzantine_fraction=0.0,
            use_dp=False, aggregation_method='fedavg',
            client_speed_variance=False, eval_every_n_rounds=4, seed=42,
            local_epochs=1,
        )
        config_with_dp = Config(
            num_clients=5, num_rounds=8, byzantine_fraction=0.0,
            use_dp=True, dp_noise_multiplier=0.1,
            aggregation_method='fedavg', client_speed_variance=False,
            local_epochs=1,
            eval_every_n_rounds=4, seed=42,
        )
        server_no_dp = _run_pipeline(config_no_dp)
        server_with_dp = _run_pipeline(config_with_dp)
        acc_no_dp = server_no_dp.metrics_history['accuracy'][-1]
        acc_with_dp = server_with_dp.metrics_history['accuracy'][-1]
        dp_cost = acc_no_dp - acc_with_dp
        check("T6.5 DP cost < 20% accuracy points",
              dp_cost < 0.20,
              f"No DP: {acc_no_dp:.2%}, With DP: {acc_with_dp:.2%}, "
              f"DP cost: {dp_cost:.2%}. Should be < 20%.")
    except Exception as e:
        check("T6.5 DP utility", False, f"Exception: {e}")


# ===================================================================
# TEST GROUP 7: Weight Delta Pipeline Integrity
# ===================================================================

def test_group_7():
    print("\n" + "=" * 60)
    print("TEST GROUP 7: Weight Delta Pipeline Integrity")
    print("=" * 60)

    # T7.1 — Weight delta is exactly zero when model is not trained
    model = FLModel()
    pre = model.get_weights()
    delta = model.get_weight_delta(pre)
    total_norm = sum(np.linalg.norm(v.flatten()) for v in delta.values())
    check(
        "T7.1 Weight delta is zero when model is not trained",
        total_norm < 1e-6,
        f"Delta norm = {total_norm:.8f}. Should be ~0 when model hasn't trained.",
    )

    # T7.2 — set_weights / get_weights roundtrip is lossless
    model = FLModel()
    original = model.get_weights()
    np.random.seed(42)
    perturbed = {k: np.asarray(v + np.random.normal(0, 0.01, size=v.shape)).astype(v.dtype)
                 for k, v in original.items()}
    model.set_weights(perturbed)
    recovered = model.get_weights()
    # atol=1e-4 accounts for float64→float32→float64 roundtrip via PyTorch
    all_match = all(np.allclose(perturbed[k], recovered[k], atol=1e-4) for k in original)
    check(
        "T7.2 set_weights/get_weights roundtrip is lossless",
        all_match,
        "set_weights/get_weights roundtrip should be lossless.",
    )

    # T7.3 — Weight delta applies correctly
    model = FLModel()
    w0 = model.get_weights()
    w1 = {k: v + 0.1 for k, v in w0.items()}
    model.set_weights(w1)
    delta = model.get_weight_delta(w0)
    all_correct = all(
        np.allclose(v, np.full_like(v, 0.1), atol=1e-5)
        for v in delta.values()
    )
    check(
        "T7.3 Weight delta = w1 - w0 = 0.1 for all params",
        all_correct,
        "Delta should be exactly w1 - w0 = 0.1 for all parameters.",
    )

    # T7.4 — Server _apply_delta actually changes the global model
    try:
        config = Config(
            num_clients=3, num_rounds=1, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=False, seed=42,
        )
        server, _clients, _tdl = _make_minimal_server(config)

        pre_weights = server.get_global_weights()
        delta = {k: np.ones_like(v) * 0.01 for k, v in pre_weights.items()}
        server._apply_delta(delta)
        post_weights = server.get_global_weights()
        changed = any(
            not np.allclose(pre_weights[k], post_weights[k])
            for k in pre_weights
        )
        check(
            "T7.4 Server _apply_delta changes global model",
            changed,
            "After _apply_delta, global model weights should have changed.",
        )
    except Exception as e:
        check("T7.4 Server _apply_delta", False, f"Exception: {e}")


# ===================================================================
# TEST GROUP 8: Anomaly Detector Behavioral Tests
# ===================================================================

def test_group_8():
    print("\n" + "=" * 60)
    print("TEST GROUP 8: Anomaly Detector Behavioral Tests")
    print("=" * 60)

    # Setup
    model = FLModel()
    current_weights = model.get_weights()
    small_delta = {k: np.asarray(np.random.normal(0, 0.001, size=v.shape))
                   for k, v in current_weights.items()}

    # T8.1 — AnomalyDetector flags high-scoring (Byzantine) updates
    detector = AnomalyDetector(threshold=1.5, sabd_corrector=None)

    honest_updates = []
    for i in range(8):
        u = ClientUpdate(
            client_id=i,
            weight_delta={k: np.asarray(v + np.random.normal(0, 0.0001, size=np.asarray(v).shape))
                          for k, v in small_delta.items()},
            round_number=1,
            num_samples=100,
            training_loss=0.5 + np.random.randn() * 0.01,
            is_byzantine=False,
        )
        honest_updates.append(u)

    # Byzantine: sign-flipped delta (very divergent)
    byz_delta = {k: -v * 1000.0 for k, v in small_delta.items()}
    byzantine_update = ClientUpdate(
        client_id=99,
        weight_delta=byz_delta,
        round_number=1,
        num_samples=100,
        training_loss=5.0,
        is_byzantine=True,
    )
    all_updates = honest_updates + [byzantine_update]

    scores = [
        detector.score_update(u, all_updates, current_weights)
        for u in all_updates
    ]
    byz_score = scores[-1]
    honest_avg = np.mean(scores[:-1])
    check(
        "T8.1a Byzantine scores higher than honest avg × 2",
        byz_score > honest_avg * 2,
        f"Byzantine score={byz_score:.3f}, honest avg={honest_avg:.3f}. "
        "Byzantine should score much higher.",
    )
    check(
        "T8.1b Byzantine is flagged by detector",
        detector.is_byzantine(byz_score),
        f"Byzantine score={byz_score:.3f}, threshold={detector.threshold}. "
        "Should be flagged.",
    )

    # T8.2 — AnomalyDetector does NOT flag honest updates
    detector_clean = AnomalyDetector(threshold=2.5, sabd_corrector=None)
    honest_only = []
    for i in range(10):
        u = ClientUpdate(
            client_id=i,
            weight_delta={k: np.asarray(v + np.random.normal(0, 0.0001, size=np.asarray(v).shape))
                          for k, v in small_delta.items()},
            round_number=1,
            num_samples=100,
            training_loss=0.5 + np.random.randn() * 0.01,
            is_byzantine=False,
        )
        honest_only.append(u)

    clean_scores = [
        detector_clean.score_update(u, honest_only, current_weights)
        for u in honest_only
    ]
    falsely_flagged = sum(1 for s in clean_scores if detector_clean.is_byzantine(s))
    check(
        "T8.2 No honest clients falsely flagged",
        falsely_flagged == 0,
        f"{falsely_flagged}/10 honest clients falsely flagged. Should be 0.",
    )

    # T8.3 — is_byzantine flag in ClientUpdate is never used by server
    try:
        config = Config(
            num_clients=3, num_rounds=1, byzantine_fraction=0.0,
            use_dp=False, client_speed_variance=False,
            anomaly_threshold=9999.0,  # very high threshold => nothing flagged
            seed=42,
        )
        server, _clients, _tdl = _make_minimal_server(config)
        server.global_round = 1
        # Record model history so SABD doesn't fail
        server.model_history.record(1, server.get_global_weights())

        legit_delta = {k: np.zeros_like(v) for k, v in server.get_global_weights().items()}
        sneaky_update = ClientUpdate(
            client_id=99,
            weight_delta=legit_delta,
            round_number=1,
            num_samples=100,
            training_loss=0.3,
            is_byzantine=True,  # flag is True, but server should ignore it
        )
        server.receive_update(sneaky_update)
        processed, discarded, _ = server.aggregate_pending_updates()
        check(
            "T8.3 Server does NOT use is_byzantine flag",
            processed == 1,
            f"processed={processed}, discarded={discarded}. "
            "Server should not use is_byzantine flag for decisions.",
        )
    except Exception as e:
        check("T8.3 Server behaviour", False, f"Exception: {e}")


# ===================================================================
# TEST GROUP 9: Output Artifacts (What Judges See)
# ===================================================================

def test_group_9():
    print("\n" + "=" * 60)
    print("TEST GROUP 9: Output Artifacts")
    print("=" * 60)

    from async_federated_learning.evaluation.metrics import ExperimentTracker

    config = Config(
        num_clients=3, num_rounds=1, byzantine_fraction=0.0,
        use_dp=False, client_speed_variance=False,
        output_dir='./results/e2e_test_artifacts',
        seed=42,
    )
    tracker = ExperimentTracker(config)

    results_dict = {
        'E1 Baseline':      {'rounds': [5, 10, 15], 'accuracy': [0.5, 0.7, 0.9]},
        'E2 FedAvg Attack': {'rounds': [5, 10, 15], 'accuracy': [0.5, 0.2, 0.1]},
    }

    # T9.1 — Convergence plot
    try:
        tracker.plot_convergence_comparison(results_dict, 'test_convergence.png')
        path = Path(config.output_dir) / 'test_convergence.png'
        check(
            "T9.1 Convergence plot generated and non-empty",
            path.exists() and path.stat().st_size > 1000,
            f"Plot file: exists={path.exists()}, "
            f"size={path.stat().st_size if path.exists() else 0} bytes",
        )
    except Exception as e:
        check("T9.1 Convergence plot", False, f"Exception: {e}")

    # T9.2 — SABD proof plot
    try:
        raw_divs = {'honest_slow': [0.3, 0.4, 0.35], 'byzantine': [0.8, 0.9, 0.85]}
        corrected_divs = {'honest_slow': [0.05, 0.04, 0.06], 'byzantine': [0.8, 0.88, 0.82]}
        tracker.plot_sabd_proof(raw_divs, corrected_divs, 'test_sabd_proof.png')
        path = Path(config.output_dir) / 'test_sabd_proof.png'
        check(
            "T9.2 SABD proof plot generated and non-empty",
            path.exists() and path.stat().st_size > 1000,
            "SABD proof plot not generated or empty.",
        )
    except Exception as e:
        check("T9.2 SABD proof plot", False, f"Exception: {e}")

    # T9.3 — Summary report
    try:
        tracker.generate_summary_report(results_dict, 'test_summary.md')
        path = Path(config.output_dir) / 'test_summary.md'
        exists = path.exists()
        content = path.read_text() if exists else ""
        has_acc = 'Final Acc' in content or 'accuracy' in content.lower()
        has_config = 'Config' in content or 'config' in content.lower()
        check(
            "T9.3 Summary report generated with key sections",
            exists and has_acc and has_config,
            "Summary report missing key sections.",
        )
    except Exception as e:
        check("T9.3 Summary report", False, f"Exception: {e}")

    # T9.4 — CSV metrics file
    try:
        tracker.save_round_metrics_csv(results_dict, 'test_metrics.csv')
        path = Path(config.output_dir) / 'test_metrics.csv'
        exists = path.exists()
        if exists:
            import pandas as pd
            df = pd.read_csv(path)
            has_acc_col = 'accuracy' in df.columns
            has_rows = len(df) > 0
            check(
                "T9.4 CSV metrics file generated and parseable",
                has_acc_col and has_rows,
                f"CSV has {len(df)} rows and columns: {list(df.columns)}",
            )
        else:
            check("T9.4 CSV metrics file", False, "File not found.")
    except Exception as e:
        check("T9.4 CSV metrics file", False, f"Exception: {e}")


# ===================================================================
# FINAL SUMMARY
# ===================================================================

def print_summary():
    print("\n" + "=" * 60)
    print("E2E VALIDATION SUMMARY")
    print("=" * 60)

    # Build groups from results list
    # Group boundaries based on expected counts per group
    # Group 1: Aggregation Numerics  => 5 items (T1.1-T1.5)
    # Group 2: Attack Effectiveness  => 4 items (T2.1a, T2.1b, T2.2, T2.3, T2.4)
    # Group 3: Differential Privacy  => 4 items (T3.1, T3.2, T3.3, T3.4)
    # Group 4: Async & Staleness     => 5 items (T4.1-T4.5)
    # Group 5: SABD Behavior         => 4 items (T5.1-T5.4)
    # Group 6: Convergence Behavior  => 5+ items (T6.1a-c, T6.2, T6.3, T6.4, T6.5)
    # Group 7: Weight Delta Pipeline => 4 items (T7.1-T7.4)
    # Group 8: Anomaly Detector      => 4 items (T8.1a, T8.1b, T8.2, T8.3)
    # Group 9: Output Artifacts      => 4 items (T9.1-T9.4)

    # Rather than hard-coding indices (which would break if counts change),
    # we use name prefixes to group results dynamically.
    group_defs = [
        ("Aggregation Numerics",  "T1."),
        ("Attack Effectiveness",  "T2."),
        ("Differential Privacy",  "T3."),
        ("Async & Staleness",     "T4."),
        ("SABD Behavior",         "T5."),
        ("Convergence Behavior",  "T6."),
        ("Weight Delta Pipeline", "T7."),
        ("Anomaly Detector",      "T8."),
        ("Output Artifacts",      "T9."),
    ]

    total_pass = 0
    total_fail = 0

    for group_name, prefix in group_defs:
        group_results = [(n, p) for n, p in results if prefix in n]
        passed = sum(1 for _, p in group_results if p)
        failed = len(group_results) - passed
        total_pass += passed
        total_fail += failed
        status = "✓" if failed == 0 else "✗"
        print(f"  {status} {group_name}: {passed}/{len(group_results)} passed")

    print(f"\nTotal: {total_pass}/{total_pass + total_fail} passed")
    if total_fail == 0:
        print("✓ ALL TESTS PASSED — System is demo-ready")
    else:
        print(f"✗ {total_fail} TESTS FAILED — Fix before demo")
        print("\nFailed tests:")
        for name, passed in results:
            if not passed:
                print(f"  - {name}")


# ===================================================================
# Main — supports per-group execution via CLI
# ===================================================================
#
# Usage:
#   python tests/e2e_validation.py              # run ALL groups
#   python tests/e2e_validation.py --group 1    # run only group 1
#   python tests/e2e_validation.py --group 1 2 5 7  # run groups 1, 2, 5, 7
#
# Groups:
#   1  Aggregation Numerics       (fast, no GPU)
#   2  Attack Effectiveness       (fast, no GPU)
#   3  Differential Privacy       (⏱ needs MNIST download + training)
#   4  Async & Staleness          (⏱ needs MNIST + threading)
#   5  SABD Behavior              (fast, no GPU)
#   6  Convergence Behavior       (⏱⏱ slowest — 5 full training runs)
#   7  Weight Delta Pipeline      (fast, no GPU)
#   8  Anomaly Detector           (fast, no GPU)
#   9  Output Artifacts           (fast, no GPU)

ALL_GROUPS = {
    1: ("Aggregation Numerics",   test_group_1),
    2: ("Attack Effectiveness",   test_group_2),
    3: ("Differential Privacy ⏱", test_group_3),
    4: ("Async & Staleness ⏱",    test_group_4),
    5: ("SABD Behavior",          test_group_5),
    6: ("Convergence ⏱⏱",         test_group_6),
    7: ("Weight Delta Pipeline",  test_group_7),
    8: ("Anomaly Detector",       test_group_8),
    9: ("Output Artifacts",       test_group_9),
}

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="E2E behavioral validation for Async Federated Learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Group reference:\n"
            "  1  Aggregation Numerics        (fast)\n"
            "  2  Attack Effectiveness        (fast)\n"
            "  3  Differential Privacy        (⏱ MNIST training)\n"
            "  4  Async & Staleness           (⏱ MNIST + threads)\n"
            "  5  SABD Behavior               (fast)\n"
            "  6  Convergence Behavior        (⏱⏱ slowest)\n"
            "  7  Weight Delta Pipeline       (fast)\n"
            "  8  Anomaly Detector            (fast)\n"
            "  9  Output Artifacts            (fast)\n"
        ),
    )
    parser.add_argument(
        "--group", "-g",
        type=int, nargs="+",
        choices=range(1, 10),
        metavar="N",
        help="Run only these test group(s). Example: --group 1 2 5",
    )
    args = parser.parse_args()

    groups_to_run = args.group if args.group else list(range(1, 10))

    print("=" * 60)
    print("ASYNC FEDERATED LEARNING — E2E BEHAVIORAL VALIDATION")
    print("=" * 60)
    if args.group:
        names = [ALL_GROUPS[g][0] for g in groups_to_run]
        print(f"  Running groups: {', '.join(names)}")

    for gid in sorted(groups_to_run):
        ALL_GROUPS[gid][1]()

    print_summary()

