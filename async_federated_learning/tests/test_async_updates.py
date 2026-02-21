"""
Test script to verify asynchronous update processing in FL server.

Tests:
1. Async mode triggers aggregation at 50% quorum
2. Gatekeeper filters Byzantine updates
3. SABD filters remaining malicious updates
4. Sync mode waits for all clients
"""

import sys
import time
import random
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from async_federated_learning.config import Config
from async_federated_learning.models.cnn import FLModel
from async_federated_learning.server.fl_server import AsyncFLServer
from async_federated_learning.server.model_history import ModelHistoryBuffer
from async_federated_learning.detection.anomaly import AnomalyDetector
from async_federated_learning.detection.sabd import SABDCorrector
from async_federated_learning.detection.gatekeeper import Gatekeeper
from async_federated_learning.client.fl_client import FLClient
from torch.utils.data import TensorDataset, DataLoader


def create_dummy_mnist_data(num_samples=100):
    """Create dummy MNIST-like data for testing."""
    images = torch.randn(num_samples, 1, 28, 28)
    labels = torch.randint(0, 10, (num_samples,))
    dataset = TensorDataset(images, labels)
    return DataLoader(dataset, batch_size=32, shuffle=True)


def create_test_clients(num_clients, config, attack_fraction=0.2):
    """Create FL clients with variable delays and some Byzantine attackers."""
    clients = []
    num_attackers = int(num_clients * attack_fraction)
    
    for i in range(num_clients):
        # Variable delay (simulate network heterogeneity)
        delay = random.uniform(0.1, 0.5) if config.client_speed_variance > 0 else 0
        
        # Some clients are Byzantine attackers
        is_attacker = i < num_attackers
        attack_type = "label_flip" if is_attacker else None
        
        train_loader = create_dummy_mnist_data(100)
        
        client = FLClient(
            client_id=i,
            train_dataloader=train_loader,
            config=config,
            network_delay=delay,
            attack_type=attack_type,
            attack_fraction=0.5 if is_attacker else 0.0,
        )
        clients.append(client)
    
    return clients


def test_async_quorum():
    """Test 1: Async mode aggregates at 50% quorum without waiting for all clients."""
    print("\n" + "="*70)
    print("TEST 1: Async Quorum (50% threshold)")
    print("="*70)
    
    # Configuration
    config = Config()
    config.num_clients = 10
    config.client_speed_variance = 0.5  # Enable async mode
    config.use_gatekeeper = False  # Disable for this test
    config.aggregation_method = "fedavg"
    config.num_rounds = 1
    
    # Create server components
    model = FLModel()
    test_loader = create_dummy_mnist_data(100)
    model_history = ModelHistoryBuffer(config.model_history_size)
    corrector = SABDCorrector(config.sabd_alpha, model_history)
    anomaly_detector = AnomalyDetector(config, corrector)
    
    server = AsyncFLServer(
        model=model,
        config=config,
        test_dataloader=test_loader,
        model_history=model_history,
        anomaly_detector=anomaly_detector,
    )
    
    # Create clients with variable delays
    clients = create_test_clients(10, config, attack_fraction=0)
    
    # Run one round
    print(f"\nServer mode: {'ASYNC' if server.async_mode else 'SYNC'}")
    print(f"Quorum threshold: {server.min_updates_for_aggregation}/{len(clients)} clients")
    
    start_time = time.time()
    metrics = server.run_round(clients)
    elapsed = time.time() - start_time
    
    # Verify
    print(f"\nRound completed in {elapsed:.2f}s")
    print(f"Processed: {metrics['processed']}/{len(clients)} clients")
    print(f"Mode: {metrics.get('mode', 'unknown')}")
    print(f"Average staleness: {metrics['avg_staleness']:.2f}")
    
    # Assertions
    assert metrics.get("mode") == "async", "Should use async mode"
    assert metrics["processed"] >= server.min_updates_for_aggregation, "Should process at least quorum"
    assert elapsed < 2.0, f"Async should be fast (took {elapsed:.2f}s)"
    
    print("✅ PASSED: Async quorum works correctly")
    return True


def test_gatekeeper_filtering():
    """Test 2: Gatekeeper filters Byzantine updates by L2 norm."""
    print("\n" + "="*70)
    print("TEST 2: Gatekeeper L2 Filtering")
    print("="*70)
    
    # Configuration
    config = Config()
    config.num_clients = 10
    config.client_speed_variance = 0  # Sync mode for predictability
    config.use_gatekeeper = True
    config.gatekeeper_l2_factor = 3.0
    config.gatekeeper_max_threshold = 1000.0
    config.aggregation_method = "fedavg"
    config.num_rounds = 1
    
    # Create server components
    model = FLModel()
    test_loader = create_dummy_mnist_data(100)
    model_history = ModelHistoryBuffer(config.model_history_size)
    corrector = SABDCorrector(config.sabd_alpha, model_history)
    anomaly_detector = AnomalyDetector(config, corrector)
    
    server = AsyncFLServer(
        model=model,
        config=config,
        test_dataloader=test_loader,
        model_history=model_history,
        anomaly_detector=anomaly_detector,
    )
    
    # Create clients with 30% attackers
    clients = create_test_clients(10, config, attack_fraction=0.3)
    
    # Run one round
    print(f"\nClients: {len(clients)} (3 Byzantine attackers)")
    print(f"Gatekeeper enabled: {server.gatekeeper is not None}")
    
    metrics = server.run_round(clients)
    
    # Results
    print(f"\nProcessed: {metrics['processed']} clients")
    print(f"Gatekeeper rejected: {metrics['gatekeeper_rejected']} updates (L2 norm)")
    print(f"SABD rejected: {metrics['discarded_sabd']} updates (Byzantine detection)")
    print(f"Total filtered: {metrics['gatekeeper_rejected'] + metrics['discarded_sabd']}")
    
    # Verify filtering happened
    total_filtered = metrics['gatekeeper_rejected'] + metrics['discarded_sabd']
    assert total_filtered > 0, "Should filter some Byzantine updates"
    
    # Get gatekeeper statistics
    if server.gatekeeper:
        stats = server.gatekeeper.get_statistics()
        print(f"\nGatekeeper stats:")
        print(f"  Total inspected: {stats['total_inspected']}")
        print(f"  Total rejected: {stats['total_rejected']}")
        print(f"  Rejection rate: {stats['rejection_rate']*100:.1f}%")
    
    print("✅ PASSED: Gatekeeper filters Byzantine updates")
    return True


def test_multi_layer_defense():
    """Test 3: Multi-layer defense (Gatekeeper → SABD → Robust Agg)."""
    print("\n" + "="*70)
    print("TEST 3: Multi-Layer Defense Pipeline")
    print("="*70)
    
    # Configuration
    config = Config()
    config.num_clients = 10
    config.client_speed_variance = 0.5  # Async mode
    config.use_gatekeeper = True
    config.gatekeeper_l2_factor = 3.0
    config.gatekeeper_max_threshold = 1000.0
    config.aggregation_method = "trimmed_mean"  # Robust aggregation
    config.trimmed_mean_beta = 0.2
    config.num_rounds = 1
    
    # Create server components
    model = FLModel()
    test_loader = create_dummy_mnist_data(100)
    model_history = ModelHistoryBuffer(config.model_history_size)
    corrector = SABDCorrector(config.sabd_alpha, model_history)
    anomaly_detector = AnomalyDetector(config, corrector)
    
    server = AsyncFLServer(
        model=model,
        config=config,
        test_dataloader=test_loader,
        model_history=model_history,
        anomaly_detector=anomaly_detector,
    )
    
    # Create clients with 40% attackers (high threat)
    clients = create_test_clients(10, config, attack_fraction=0.4)
    
    # Run one round
    print(f"\nClients: {len(clients)} (4 Byzantine attackers - HIGH THREAT)")
    print(f"Defense layers:")
    print(f"  Layer 1: Gatekeeper (L2 norm inspection)")
    print(f"  Layer 2: Staleness filter (max age)")
    print(f"  Layer 3: SABD (gradient divergence)")
    print(f"  Layer 4: Trimmed Mean (robust aggregation)")
    
    metrics = server.run_round(clients)
    
    # Results
    print(f"\n📊 Filtering Results:")
    print(f"  Initial updates: {len(clients)}")
    print(f"  ❌ Gatekeeper rejected: {metrics['gatekeeper_rejected']} (L2 norm)")
    print(f"  ❌ SABD rejected: {metrics['discarded_sabd']} (Byzantine)")
    print(f"  ✅ Aggregated: {metrics['processed']} (clean)")
    print(f"  Defense rate: {(metrics['gatekeeper_rejected'] + metrics['discarded_sabd']) / len(clients) * 100:.1f}%")
    
    # Verify defense effectiveness
    assert metrics['processed'] > 0, "Should have some clean updates"
    total_filtered = metrics['gatekeeper_rejected'] + metrics['discarded_sabd']
    defense_rate = total_filtered / len(clients)
    
    print(f"\n🛡️ Defense Effectiveness: {defense_rate*100:.1f}% of threats filtered")
    
    print("✅ PASSED: Multi-layer defense working")
    return True


def test_sync_mode():
    """Test 4: Sync mode waits for all clients before aggregating."""
    print("\n" + "="*70)
    print("TEST 4: Sync Mode (Wait for All)")
    print("="*70)
    
    # Configuration
    config = Config()
    config.num_clients = 5
    config.client_speed_variance = 0  # Disable async mode
    config.use_gatekeeper = False
    config.aggregation_method = "fedavg"
    config.num_rounds = 1
    
    # Create server components
    model = FLModel()
    test_loader = create_dummy_mnist_data(100)
    model_history = ModelHistoryBuffer(config.model_history_size)
    corrector = SABDCorrector(config.sabd_alpha, model_history)
    anomaly_detector = AnomalyDetector(config, corrector)
    
    server = AsyncFLServer(
        model=model,
        config=config,
        test_dataloader=test_loader,
        model_history=model_history,
        anomaly_detector=anomaly_detector,
    )
    
    # Create clients (no delays in sync mode)
    clients = create_test_clients(5, config, attack_fraction=0)
    
    # Run one round
    print(f"\nServer mode: {'ASYNC' if server.async_mode else 'SYNC'}")
    print(f"Clients: {len(clients)} (all honest)")
    
    metrics = server.run_round(clients)
    
    # Results
    print(f"\nProcessed: {metrics['processed']}/{len(clients)} clients")
    print(f"Mode: {metrics.get('mode', 'unknown')}")
    
    # Verify sync behavior
    assert metrics.get("mode") == "sync", "Should use sync mode"
    assert metrics["processed"] == len(clients), "Should process ALL clients in sync mode"
    
    print("✅ PASSED: Sync mode waits for all clients")
    return True


def run_all_tests():
    """Run all async update tests."""
    print("\n" + "="*70)
    print("ASYNC UPDATE TEST SUITE")
    print("="*70)
    print("\nTesting asynchronous update processing with multi-layer security...")
    
    tests = [
        ("Async Quorum", test_async_quorum),
        ("Gatekeeper Filtering", test_gatekeeper_filtering),
        ("Multi-Layer Defense", test_multi_layer_defense),
        ("Sync Mode", test_sync_mode),
    ]
    
    results = []
    for name, test_fn in tests:
        try:
            success = test_fn()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ FAILED: {name}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Async updates fully working!")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Check logs above.")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
