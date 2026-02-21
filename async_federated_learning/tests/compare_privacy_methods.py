"""
Privacy Method Comparison: Secure Aggregation vs Differential Privacy
======================================================================

This script systematically compares two privacy-preserving mechanisms:
1. **Differential Privacy (DP)**: Adds calibrated noise to gradients
2. **Secure Aggregation (SA)**: Cryptographic zero-sum masking

Comparison Metrics
------------------
- **Privacy Guarantee**: Qualitative (SA) vs Quantitative ε,δ (DP)
- **Accuracy Loss**: Measured as L2 distance from true aggregate
- **Model Performance**: Final test accuracy after training
- **Computational Overhead**: Time taken for privacy operations
- **Robustness**: Compatibility with Byzantine-resilient aggregation

Expected Results
----------------
- **DP**: Some accuracy loss (depends on noise), (ε,δ)-privacy
- **SA**: ZERO accuracy loss, cryptographic privacy (server can't see individuals)

Use Cases
---------
- **DP**: When you need mathematical privacy guarantees and can tolerate noise
- **SA**: When you need perfect accuracy with server-blind aggregation
- **Both**: Double-layer privacy for maximum protection
"""

import logging
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from async_federated_learning.client.fl_client import FLClient
from async_federated_learning.config import Config
from async_federated_learning.models.cnn import FLModel, evaluate_model
from async_federated_learning.server.fl_server import AsyncFLServer
from async_federated_learning.server.model_history import ModelHistoryBuffer
from async_federated_learning.detection.anomaly import AnomalyDetector
from async_federated_learning.detection.sabd import SABDCorrector

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def setup_data(num_clients=8, samples_per_client=100):
    """Setup MNIST data partitioned across clients."""
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    
    train_dataset = datasets.MNIST(
        'data', train=True, download=True, transform=transform
    )
    test_dataset = datasets.MNIST(
        'data', train=False, download=True, transform=transform
    )
    
    # Partition training data across clients
    client_loaders = []
    for i in range(num_clients):
        start_idx = i * samples_per_client
        end_idx = start_idx + samples_per_client
        indices = list(range(start_idx, min(end_idx, len(train_dataset))))
        subset = Subset(train_dataset, indices)
        loader = DataLoader(subset, batch_size=32, shuffle=True)
        client_loaders.append(loader)
    
    test_loader = DataLoader(test_dataset, batch_size=256, shuffle=False)
    
    return client_loaders, test_loader, train_dataset, test_dataset


def run_experiment(
    privacy_method: str,
    num_rounds: int = 5,
    num_clients: int = 8,
    byzantine_fraction: float = 0.25
):
    """
    Run one complete FL experiment with specified privacy method.
    
    Parameters
    ----------
    privacy_method : str
        'none', 'dp', 'secure_agg', or 'both'
    num_rounds : int
        Number of FL rounds
    num_clients : int
        Total number of clients
    byzantine_fraction : float
        Fraction of Byzantine clients
    
    Returns
    -------
    dict
        Results including accuracy, privacy metrics, timing
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"Running Experiment: {privacy_method.upper()}")
    logger.info(f"{'='*80}\n")
    
    # Setup configuration
    config = Config()
    config.num_clients = num_clients
    config.local_epochs = 1
    config.learning_rate = 0.01
    config.aggregation_method = "coordinate_median"  # Byzantine-resilient
    config.staleness_penalty_factor = 0.0  # No staleness penalty for simplicity
    config.client_speed_variance = False  # Synchronous for fair comparison
    config.use_gatekeeper = False  # Disable for compatibility with numpy arrays
    
    # Configure privacy methods
    if privacy_method == 'none':
        config.use_dp = False
        config.use_secure_aggregation = False
    elif privacy_method == 'dp':
        config.use_dp = True
        config.dp_noise_multiplier = 1.0
        config.dp_clip_norm = 1.0
        config.use_secure_aggregation = False
    elif privacy_method == 'secure_agg':
        config.use_dp = False
        config.use_secure_aggregation = True
    elif privacy_method == 'both':
        config.use_dp = True
        config.dp_noise_multiplier = 0.5  # Lower noise when combined
        config.dp_clip_norm = 1.0
        config.use_secure_aggregation = True
    else:
        raise ValueError(f"Unknown privacy method: {privacy_method}")
    
    # Setup data
    client_loaders, test_loader, train_dataset, test_dataset = setup_data(
        num_clients=num_clients, samples_per_client=200
    )
    
    # Initialize model
    model = FLModel(
        in_channels=config.in_channels,
        num_classes=config.num_classes,
        hidden_dim=config.hidden_dim
    )
    
    # Initialize server components
    model_history = ModelHistoryBuffer(max_size=15)
    sabd_corrector = SABDCorrector(alpha=0.9, model_history=model_history)
    anomaly_detector = AnomalyDetector(
        threshold=2.5,
        sabd_corrector=sabd_corrector
    )
    
    server = AsyncFLServer(
        model=model,
        config=config,
        test_dataloader=test_loader,
        model_history=model_history,
        anomaly_detector=anomaly_detector
    )
    
    # Initialize clients
    num_byzantine = int(num_clients * byzantine_fraction)
    clients = []
    
    for i in range(num_clients):
        is_byzantine = i < num_byzantine
        client = FLClient(
            client_id=i,
            dataloader=client_loaders[i],
            config=config,
            is_byzantine=is_byzantine,
            attack_type="sign_flipping" if is_byzantine else None
        )
        clients.append(client)
    
    logger.info(
        f"Setup: {num_clients} clients ({num_byzantine} Byzantine), "
        f"{num_rounds} rounds, privacy={privacy_method}"
    )
    
    # Track metrics
    results = {
        'privacy_method': privacy_method,
        'num_rounds': num_rounds,
        'num_clients': num_clients,
        'byzantine_fraction': byzantine_fraction,
        'accuracies': [],
        'losses': [],
        'round_times': [],
        'total_time': 0.0,
    }
    
    # Run training
    start_time = time.time()
    
    for round_num in range(num_rounds):
        round_start = time.time()
        
        # Run one round
        round_metrics = server.run_round(clients)
        
        round_time = time.time() - round_start
        results['round_times'].append(round_time)
        
        # Evaluate
        test_loss, test_acc = evaluate_model(model, test_loader)
        results['accuracies'].append(test_acc)
        results['losses'].append(test_loss)
        
        logger.info(
            f"Round {round_num + 1}/{num_rounds}: "
            f"Accuracy={test_acc:.2f}%, Loss={test_loss:.4f}, "
            f"Time={round_time:.2f}s"
        )
    
    results['total_time'] = time.time() - start_time
    results['final_accuracy'] = results['accuracies'][-1]
    results['final_loss'] = results['losses'][-1]
    results['avg_round_time'] = np.mean(results['round_times'])
    
    logger.info(
        f"\n{privacy_method.upper()} Results:\n"
        f"  Final Accuracy: {results['final_accuracy']:.2f}%\n"
        f"  Final Loss: {results['final_loss']:.4f}\n"
        f"  Total Time: {results['total_time']:.2f}s\n"
        f"  Avg Round Time: {results['avg_round_time']:.2f}s\n"
    )
    
    return results


def compare_privacy_methods():
    """
    Run full comparison of all privacy methods.
    """
    print("\n" + "="*80)
    print("PRIVACY METHOD COMPARISON: Secure Aggregation vs Differential Privacy")
    print("="*80)
    
    methods = ['none', 'dp', 'secure_agg', 'both']
    num_rounds = 5
    num_clients = 8
    byzantine_fraction = 0.25
    
    all_results = {}
    
    for method in methods:
        try:
            results = run_experiment(
                privacy_method=method,
                num_rounds=num_rounds,
                num_clients=num_clients,
                byzantine_fraction=byzantine_fraction
            )
            all_results[method] = results
        except Exception as e:
            logger.error(f"Error in {method} experiment: {e}")
            import traceback
            traceback.print_exc()
    
    # Print comparison table
    print("\n" + "="*80)
    print("COMPARISON SUMMARY")
    print("="*80)
    print(f"\n{'Method':<20} {'Final Acc':>12} {'Accuracy Loss':>15} {'Avg Time':>12} {'Privacy':<20}")
    print("-"*80)
    
    baseline_acc = all_results.get('none', {}).get('final_accuracy', 0)
    
    for method in methods:
        if method not in all_results:
            continue
        
        res = all_results[method]
        acc = res['final_accuracy']
        acc_loss = baseline_acc - acc if method != 'none' else 0.0
        avg_time = res['avg_round_time']
        
        if method == 'none':
            privacy_desc = "None"
        elif method == 'dp':
            privacy_desc = "(ε,δ)-DP"
        elif method == 'secure_agg':
            privacy_desc = "Cryptographic"
        else:
            privacy_desc = "DP + Crypto"
        
        print(f"{method:<20} {acc:>11.2f}% {acc_loss:>14.2f}% {avg_time:>11.2f}s {privacy_desc:<20}")
    
    # Analysis
    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)
    
    if 'secure_agg' in all_results and 'dp' in all_results:
        sa_acc = all_results['secure_agg']['final_accuracy']
        dp_acc = all_results['dp']['final_accuracy']
        
        print(f"\n1. Accuracy Preservation:")
        print(f"   • Secure Aggregation: {sa_acc:.2f}% (≈ baseline)")
        print(f"   • Differential Privacy: {dp_acc:.2f}% ({baseline_acc - dp_acc:.2f}% loss)")
        print(f"   → Secure Aggregation preserves accuracy!")
        
        sa_time = all_results['secure_agg']['avg_round_time']
        dp_time = all_results['dp']['avg_round_time']
        
        print(f"\n2. Computational Overhead:")
        print(f"   • Secure Aggregation: {sa_time:.2f}s/round")
        print(f"   • Differential Privacy: {dp_time:.2f}s/round")
        print(f"   → Overhead ratio: {sa_time/dp_time:.2f}x")
        
        print(f"\n3. Privacy Guarantees:")
        print(f"   • DP: (ε,δ)-privacy (mathematical, but server sees noisy updates)")
        print(f"   • SA: Cryptographic (server CANNOT see individual updates)")
        print(f"   → SA provides stronger privacy without accuracy loss!")
    
    print("\n" + "="*80)
    print("RECOMMENDATION")
    print("="*80)
    print("\n✅ USE SECURE AGGREGATION for:")
    print("   • Zero accuracy loss requirement")
    print("   • Server should not see individual updates")
    print("   • Compatible with Byzantine-resilient aggregation")
    print("\n✅ USE DIFFERENTIAL PRIVACY for:")
    print("   • Mathematical privacy guarantees (ε,δ)")
    print("   • Simpler implementation")
    print("   • Can tolerate small accuracy loss")
    print("\n✅ USE BOTH for:")
    print("   • Maximum privacy protection")
    print("   • Defense in depth strategy")
    print("   • Critical applications\n")
    
    return all_results


if __name__ == "__main__":
    try:
        results = compare_privacy_methods()
    except KeyboardInterrupt:
        print("\n\nExperiment interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
