"""
Comprehensive Robust Aggregation Analysis
==========================================
Tests multiple attack scenarios to find the most robust method.
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

def create_test_updates(n_honest=6, n_byzantine=2, attack_type='sign_flip', attack_strength=10):
    """
    Create synthetic gradient updates with various attack types.
    
    Attack types:
    - 'sign_flip': Multiply gradients by -attack_strength
    - 'scaling': Multiply gradients by attack_strength
    - 'gaussian': Add Gaussian noise with std=attack_strength
    """
    np.random.seed(42)
    
    updates = []
    
    # Honest clients
    for i in range(n_honest):
        update = {
            'layer1': np.random.randn(100) * 1.0,
            'layer2': np.random.randn(50) * 1.0,
            'layer3': np.random.randn(10) * 1.0
        }
        updates.append(update)
    
    # Byzantine clients
    for i in range(n_byzantine):
        if attack_type == 'sign_flip':
            update = {
                'layer1': np.random.randn(100) * -attack_strength,
                'layer2': np.random.randn(50) * -attack_strength,
                'layer3': np.random.randn(10) * -attack_strength
            }
        elif attack_type == 'scaling':
            update = {
                'layer1': np.random.randn(100) * attack_strength,
                'layer2': np.random.randn(50) * attack_strength,
                'layer3': np.random.randn(10) * attack_strength
            }
        else:  # gaussian
            update = {
                'layer1': np.random.randn(100) + np.random.randn(100) * attack_strength,
                'layer2': np.random.randn(50) + np.random.randn(50) * attack_strength,
                'layer3': np.random.randn(10) + np.random.randn(10) * attack_strength
            }
        updates.append(update)
    
    return updates

def compute_corruption(aggregated, true_mean):
    """Measure corruption as relative L2 distance from true mean."""
    total_dist = 0
    total_norm = 1e-8  # Prevent division by zero
    
    for key in aggregated.keys():
        dist = np.linalg.norm(aggregated[key] - true_mean[key])
        norm = np.linalg.norm(true_mean[key])
        total_dist += dist
        total_norm += norm
    
    return (total_dist / total_norm) * 100

def test_scenario(n_honest, n_byzantine, attack_type, attack_strength):
    """Test all methods on one scenario."""
    updates = create_test_updates(n_honest, n_byzantine, attack_type, attack_strength)
    
    # Compute true mean (without Byzantine clients)
    honest_updates = updates[:n_honest]
    true_mean = {}
    for key in honest_updates[0].keys():
        values = np.array([u[key] for u in honest_updates])
        true_mean[key] = np.mean(values, axis=0)
    
    results = {}
    
    # 1. FedAvg
    agg = fedavg(updates)
    results['FedAvg'] = compute_corruption(agg, true_mean)
    
    # 2. Trimmed Mean
    agg = trimmed_mean(updates, beta=0.15)  # Trim 15% from each end
    results['Trimmed Mean'] = compute_corruption(agg, true_mean)
    
    # 3. Coordinate Median
    agg = coordinate_median(updates)
    results['Coordinate Median'] = compute_corruption(agg, true_mean)
    
    # 4. Ensemble
    agg = ensemble_aggregation(updates, beta=0.15)
    results['Ensemble'] = compute_corruption(agg, true_mean)
    
    # 5. Outlier Filter + FedAvg
    outlier_filter = OutlierFilter(method='ensemble', iqr_factor=1.5)
    filtered, accepted, rejected = outlier_filter.filter_updates(updates)
    if len(filtered) > 0:
        agg = fedavg(filtered)
        results['Outlier+FedAvg'] = compute_corruption(agg, true_mean)
        results['_rejected_outlier'] = len(rejected)
    else:
        results['Outlier+FedAvg'] = float('inf')
        results['_rejected_outlier'] = len(rejected)
    
    # 6. Outlier Filter + Trimmed Mean
    if len(filtered) > 0:
        agg = trimmed_mean(filtered, beta=0.15)
        results['Outlier+TrimMean'] = compute_corruption(agg, true_mean)
    else:
        results['Outlier+TrimMean'] = float('inf')
    
    # 7. Outlier Filter + Ensemble
    if len(filtered) > 0:
        agg = ensemble_aggregation(filtered, beta=0.15)
        results['Outlier+Ensemble'] = compute_corruption(agg, true_mean)
    else:
        results['Outlier+Ensemble'] = float('inf')
    
    return results

def main():
    print("\n" + "="*80)
    print("COMPREHENSIVE ROBUST AGGREGATION ANALYSIS")
    print("="*80)
    
    scenarios = [
        # (n_honest, n_byzantine, attack_type, attack_strength, description)
        (6, 2, 'sign_flip', 10, "Sign Flip (Strong)"),
        (6, 2, 'sign_flip', 5, "Sign Flip (Medium)"),
        (6, 2, 'scaling', 10, "Gradient Scaling (Strong)"),
        (6, 2, 'gaussian', 10, "Gaussian Noise (Strong)"),
        (5, 3, 'sign_flip', 10, "Sign Flip (38% Byzantine)"),
    ]
    
    all_results = {}
    
    for n_honest, n_byz, attack, strength, desc in scenarios:
        print(f"\n{'='*80}")
        print(f"Scenario: {desc}")
        print(f"  Honest: {n_honest}, Byzantine: {n_byz} ({n_byz/(n_honest+n_byz)*100:.0f}%)")
        print(f"  Attack: {attack}, Strength: {strength}")
        print('-'*80)
        
        results = test_scenario(n_honest, n_byz, attack, strength)
        all_results[desc] = results
        
        # Display results sorted by corruption
        sorted_results = sorted([(k, v) for k, v in results.items() if not k.startswith('_')], 
                               key=lambda x: x[1])
        
        for rank, (method, corruption) in enumerate(sorted_results, 1):
            if corruption == float('inf'):
                print(f"  {rank}. {method:<25} FAILED (no updates left)")
            else:
                rating = "✅✅" if corruption < 10 else "✅" if corruption < 50 else "⚠️" if corruption < 150 else "❌"
                print(f"  {rank}. {rating} {method:<25} {corruption:>6.1f}% corruption")
        
        if '_rejected_outlier' in results:
            print(f"\n  Outlier Filter: Rejected {results['_rejected_outlier']}/{n_honest+n_byz} clients")
    
    # Overall summary
    print("\n" + "="*80)
    print("OVERALL PERFORMANCE SUMMARY")
    print("="*80)
    
    methods = ['FedAvg', 'Trimmed Mean', 'Coordinate Median', 'Ensemble', 
               'Outlier+FedAvg', 'Outlier+TrimMean', 'Outlier+Ensemble']
    
    print(f"\n{'Method':<25}", end='')
    for desc, _, _, _, _ in scenarios:
        print(f"{desc[:12]:>13}", end='')
    print(f"{'Avg':>10}")
    print('-'*80)
    
    for method in methods:
        print(f"{method:<25}", end='')
        corruptions = []
        for desc, _, _, _, _ in scenarios:
            corr = all_results[desc].get(method, float('inf'))
            if corr == float('inf'):
                print(f"{'FAIL':>13}", end='')
            else:
                print(f"{corr:>12.1f}%", end='')
                corruptions.append(corr)
        
        if corruptions:
            avg = np.mean(corruptions)
            print(f"{avg:>9.1f}%")
        else:
            print(f"{'N/A':>10}")
    
    # Find best method
    print("\n" + "="*80)
    print("🏆 WINNER ANALYSIS")
    print("="*80)
    
    method_scores = {}
    for method in methods:
        scores = []
        for desc in all_results.keys():
            corr = all_results[desc].get(method, float('inf'))
            if corr != float('inf'):
                scores.append(corr)
        if scores:
            method_scores[method] = np.mean(scores)
    
    best_method = min(method_scores.items(), key=lambda x: x[1])
    
    print(f"\n✅ BEST METHOD: {best_method[0]}")
    print(f"   Average Corruption: {best_method[1]:.1f}%")
    
    # Top 3
    sorted_methods = sorted(method_scores.items(), key=lambda x: x[1])
    print(f"\n📊 TOP 3 METHODS:")
    for i, (method, avg_corr) in enumerate(sorted_methods[:3], 1):
        effectiveness = max(0, 100 - min(avg_corr, 100))
        print(f"   {i}. {method:<25} {avg_corr:>6.1f}% corruption ({effectiveness:.0f}% effective)")
    
    # Presentation recommendation
    print("\n" + "="*80)
    print("💡 RECOMMENDATION FOR PRESENTATION")
    print("="*80)
    
    winner = sorted_methods[0]
    baseline = method_scores.get('FedAvg', 0)
    
    print(f"\n✅ USE: {winner[0]}")
    print(f"   Why: Best average performance across all attack scenarios")
    print(f"   Average Corruption: {winner[1]:.1f}%")
    print(f"   Baseline (FedAvg): {baseline:.1f}%")
    print(f"   Improvement: {((baseline - winner[1])/baseline * 100):.1f}% reduction")
    
    print(f"\n🎤 KEY MESSAGE:")
    if 'Outlier' in winner[0]:
        print(f"   'Our multi-layer defense (Outlier Filter + Robust Aggregation)")
        print(f"    reduces model corruption by {((baseline - winner[1])/baseline * 100):.0f}% compared to standard FedAvg,")
        print(f"    successfully detecting and blocking malicious updates while")
        print(f"    preserving honest client contributions.'")
    else:
        print(f"   '{winner[0]} provides robust Byzantine defense, reducing")
        print(f"    model corruption by {((baseline - winner[1])/baseline * 100):.0f}% compared to standard FedAvg.'")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
