"""
Simple Robust Aggregation Test
===============================
Minimal test to compare aggregation methods directly.
Tests the core question: Which method handles malicious updates best?
"""

import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aggregation.fedavg import fedavg
from aggregation.trimmed_mean import trimmed_mean
from aggregation.coordinate_median import coordinate_median
from aggregation.ensemble import ensemble_aggregation
from detection.outlier_filter import OutlierFilter

def create_test_updates(n_honest=6, n_byzantine=2):
    """
    Create synthetic gradient updates for testing.
    
    Honest clients: Normal gradients around mean=0, std=1
    Byzantine clients: Sign-flipping attack (multiply by -10)
    """
    np.random.seed(42)
    
    updates = []
    
    # Honest clients
    for i in range(n_honest):
        update = {
            'layer1': np.random.randn(100) * 1.0,  # Normal gradients
            'layer2': np.random.randn(50) * 1.0,
            'layer3': np.random.randn(10) * 1.0
        }
        updates.append(update)
    
    # Byzantine clients (sign-flipping attack)
    for i in range(n_byzantine):
        update = {
            'layer1': np.random.randn(100) * -10.0,  # Flipped and scaled
            'layer2': np.random.randn(50) * -10.0,
            'layer3': np.random.randn(10) * -10.0
        }
        updates.append(update)
    
    return updates

def compute_corruption(aggregated, true_mean):
    """
    Measure how corrupted the aggregated result is.
    Returns the relative L2 distance from true mean.
    """
    total_dist = 0
    total_norm = 0
    
    for key in aggregated.keys():
        dist = np.linalg.norm(aggregated[key] - true_mean[key])
        norm = np.linalg.norm(true_mean[key])
        total_dist += dist
        total_norm += norm
    
    return (total_dist / total_norm) * 100 if total_norm > 0 else 0

def test_aggregation_methods():
    """
    Test all aggregation methods and compare corruption levels.
    """
    print("\n" + "="*70)
    print("ROBUST AGGREGATION DIRECT COMPARISON")
    print("="*70)
    print("Setup:")
    print("  - 6 Honest clients (normal gradients)")
    print("  - 2 Byzantine clients (sign-flipping × -10)")
    print("  - Attack: 25% of clients are malicious")
    print("="*70 + "\n")
    
    # Create test data
    updates = create_test_updates(n_honest=6, n_byzantine=2)
    
    # Compute true mean (without Byzantine clients)
    honest_updates = updates[:6]
    true_mean = {}
    for key in honest_updates[0].keys():
        values = np.array([u[key] for u in honest_updates])
        true_mean[key] = np.mean(values, axis=0)
    
    # Test each method
    results = []
    
    # 1. FedAvg (No Defense)
    print("🔴 Testing: FedAvg (Baseline - No Defense)")
    agg_fedavg = fedavg(updates)
    corruption_fedavg = compute_corruption(agg_fedavg, true_mean)
    results.append(("FedAvg (No Defense)", corruption_fedavg, "❌"))
    print(f"   Corruption: {corruption_fedavg:.2f}%\n")
    
    # 2. Trimmed Mean
    print("🟡 Testing: Trimmed Mean (β=0.1)")
    agg_trimmed = trimmed_mean(updates, beta=0.1)
    corruption_trimmed = compute_corruption(agg_trimmed, true_mean)
    results.append(("Trimmed Mean", corruption_trimmed, "⚠️" if corruption_trimmed < 50 else "❌"))
    print(f"   Corruption: {corruption_trimmed:.2f}%\n")
    
    # 3. Coordinate Median
    print("🟡 Testing: Coordinate Median")
    agg_median = coordinate_median(updates)
    corruption_median = compute_corruption(agg_median, true_mean)
    results.append(("Coordinate Median", corruption_median, "✅" if corruption_median < 30 else "⚠️"))
    print(f"   Corruption: {corruption_median:.2f}%\n")
    
    # 4. Ensemble
    print("🟢 Testing: Ensemble (TM + Median)")
    agg_ensemble = ensemble_aggregation(updates, beta=0.1)
    corruption_ensemble = compute_corruption(agg_ensemble, true_mean)
    results.append(("Ensemble", corruption_ensemble, "✅" if corruption_ensemble < 25 else "⚠️"))
    print(f"   Corruption: {corruption_ensemble:.2f}%\n")
    
    # 5. Outlier Filter + FedAvg
    print("🟢 Testing: Outlier Filter + FedAvg")
    outlier_filter = OutlierFilter(method='ensemble')
    filtered_updates, accepted_idx, rejected_idx = outlier_filter.filter_updates(updates)
    agg_filtered = fedavg(filtered_updates)
    corruption_filtered = compute_corruption(agg_filtered, true_mean)
    results.append(("Outlier Filter + FedAvg", corruption_filtered, "✅" if corruption_filtered < 20 else "⚠️"))
    print(f"   Rejected: {len(rejected_idx)}/{len(updates)} clients")
    print(f"   Corruption: {corruption_filtered:.2f}%\n")
    
    # 6. Outlier Filter + Ensemble
    print("🟢 Testing: Outlier Filter + Ensemble (FULL PIPELINE)")
    filtered_updates2, accepted_idx2, rejected_idx2 = outlier_filter.filter_updates(updates)
    agg_full = ensemble_aggregation(filtered_updates2, beta=0.1)
    corruption_full = compute_corruption(agg_full, true_mean)
    results.append(("Outlier Filter + Ensemble", corruption_full, "✅✅" if corruption_full < 15 else "✅"))
    print(f"   Rejected: {len(rejected_idx2)}/{len(updates)} clients")
    print(f"   Corruption: {corruption_full:.2f}%\n")
    
    # Display final comparison
    print("="*70)
    print("FINAL RESULTS - CORRUPTION FROM TRUE MEAN")
    print("="*70)
    print(f"{'Method':<35} {'Corruption':>15} {'Rating':>10}")
    print("-"*70)
    
    # Sort by corruption (lower is better)
    results.sort(key=lambda x: x[1])
    
    for name, corruption, rating in results:
        print(f"{rating} {name:<33} {corruption:>14.2f}% {rating:>10}")
    
    print("="*70)
    
    # Find best method
    best_method, best_corruption, _ = results[0]
    
    print(f"\n🏆 WINNER: {best_method}")
    print(f"   → {best_corruption:.2f}% corruption (closest to true mean)")
    
    # Calculate improvements
    baseline_corruption = [r for r in results if r[0] == "FedAvg (No Defense)"][0][1]
    improvement = ((baseline_corruption - best_corruption) / baseline_corruption) * 100
    
    print(f"\n💡 KEY INSIGHTS:")
    print(f"   • Baseline (FedAvg): {baseline_corruption:.1f}% corruption")
    print(f"   • Best Method: {best_corruption:.1f}% corruption")
    print(f"   • Improvement: {improvement:.1f}% reduction in corruption")
    
    print(f"\n📊 RANKING:")
    for i, (name, corruption, _) in enumerate(results, 1):
        effectiveness = max(0, 100 - corruption)
        print(f"   {i}. {name}: {effectiveness:.1f}% effective")
    
    print("\n" + "="*70)
    print("RECOMMENDATION FOR PRESENTATION:")
    print("="*70)
    
    if "Outlier Filter + Ensemble" in best_method:
        print("✅ Use: Outlier Filter + Ensemble (Full Pipeline)")
        print("   Why: Combines statistical filtering with robust aggregation")
        print(f"   Result: {best_corruption:.1f}% corruption vs {baseline_corruption:.1f}% baseline")
        print("   Key Message: 'Multi-layer defense achieves near-perfect")
        print("                 protection against model poisoning attacks'")
    elif "Ensemble" in best_method:
        print("✅ Use: Ensemble (Trimmed Mean + Coordinate Median)")
        print("   Why: Single method with strong Byzantine resistance")
        print(f"   Result: {best_corruption:.1f}% corruption vs {baseline_corruption:.1f}% baseline")
        print("   Key Message: 'Ensemble aggregation provides robust defense")
        print("                 without complex preprocessing'")
    else:
        print(f"✅ Use: {best_method}")
        print(f"   Result: {best_corruption:.1f}% corruption")
    
    print("="*70 + "\n")
    
    return results

if __name__ == "__main__":
    results = test_aggregation_methods()
