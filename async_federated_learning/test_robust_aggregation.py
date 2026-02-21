"""
Quick Robust Aggregation Test
==============================
Focused test comparing key robust aggregation methods with 30% Byzantine clients.

Tests 5 key configurations in ~15-20 minutes:
1. FedAvg (Baseline) - No defense
2. Trimmed Mean - Standard robust method
3. Coordinate Median - High breakdown point
4. Ensemble (TM + Median) - Combined approach
5. Outlier Filter + Ensemble - Full defense pipeline

Focus: Which method best defends against model poisoning?
"""

import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from experiments.robust_aggregation_comparison import RobustAggregationExperiment

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    """Run focused robust aggregation test."""
    
    print("\n" + "="*70)
    print("ROBUST AGGREGATION QUICK TEST")
    print("="*70)
    print("Attack: Sign Flipping (strong)")
    print("Byzantine Clients: 30%")
    print("Rounds: 5 (quick test)")
    print("Clients: 8")
    print("="*70 + "\n")
    
    # Configuration - SHORT for quick testing
    config = Config()
    config.modality = "image"
    config.num_clients = 8
    config.num_rounds = 5  # Short test
    config.local_epochs = 1  # Fast training
    config.byzantine_fraction = 0.3  # 30% malicious
    config.attack_type = "sign_flipping"
    config.batch_size = 64  # Larger batches = faster
    
    experiment = RobustAggregationExperiment(config)
    
    # Run only key experiments
    results = []
    
    # 1. Baseline: FedAvg (no defense)
    print("\n🔴 Experiment 1/5: FedAvg Baseline (No Defense)")
    config1 = experiment._create_config(aggregation='fedavg', use_gatekeeper=False)
    result1 = experiment.run_single_experiment(
        "1_FedAvg_NoDefense",
        config1,
        use_outlier_filter=False
    )
    results.append(result1)
    
    # 2. Trimmed Mean
    print("\n🟡 Experiment 2/5: Trimmed Mean")
    config2 = experiment._create_config(aggregation='trimmed_mean', use_gatekeeper=False)
    result2 = experiment.run_single_experiment(
        "2_TrimmedMean",
        config2,
        use_trimmed_mean=True
    )
    results.append(result2)
    
    # 3. Coordinate Median
    print("\n🟡 Experiment 3/5: Coordinate Median")
    config3 = experiment._create_config(aggregation='coordinate_median', use_gatekeeper=False)
    result3 = experiment.run_single_experiment(
        "3_CoordinateMedian",
        config3,
        use_median=True
    )
    results.append(result3)
    
    # 4. Ensemble (TM + Median)
    print("\n🟢 Experiment 4/5: Ensemble (Trimmed Mean + Median)")
    config4 = experiment._create_config(aggregation='ensemble', use_gatekeeper=False)
    result4 = experiment.run_single_experiment(
        "4_Ensemble",
        config4,
        use_ensemble=True
    )
    results.append(result4)
    
    # 5. Full Pipeline: Outlier Filter + Ensemble
    print("\n🟢 Experiment 5/5: Outlier Filter + Ensemble (FULL DEFENSE)")
    config5 = experiment._create_config(aggregation='ensemble', use_gatekeeper=False)
    result5 = experiment.run_single_experiment(
        "5_OutlierFilter_Ensemble",
        config5,
        use_outlier_filter=True,
        outlier_method='ensemble',
        use_ensemble=True
    )
    results.append(result5)
    
    # Display final comparison
    print("\n" + "="*90)
    print("FINAL COMPARISON - ROBUST AGGREGATION METHODS")
    print("="*90)
    print(f"{'Method':<40} {'Accuracy':>12} {'Defense Rate':>15} {'Attack Success':>15}")
    print("-"*90)
    
    for result in results:
        name = result['name'].replace('_', ' ')
        metrics = result['metrics']
        
        # Color coding based on performance
        if metrics['final_accuracy'] > 0.6:
            icon = "✅"
        elif metrics['final_accuracy'] > 0.3:
            icon = "⚠️ "
        else:
            icon = "❌"
        
        print(f"{icon} {name:<38} "
              f"{metrics['final_accuracy']:>11.2%} "
              f"{metrics['defense_rate']:>14.1f}% "
              f"{metrics['attack_success_rate']:>14.1f}%")
    
    print("="*90)
    
    # Determine winners
    best_accuracy = max(results, key=lambda x: x['metrics']['final_accuracy'])
    best_defense = max(results, key=lambda x: x['metrics']['defense_rate'])
    lowest_attack = min(results, key=lambda x: x['metrics']['attack_success_rate'])
    
    print("\n🏆 WINNERS:")
    print(f"  Best Accuracy:      {best_accuracy['name']}")
    print(f"                      → {best_accuracy['metrics']['final_accuracy']:.2%} accuracy")
    print(f"\n  Best Defense:       {best_defense['name']}")
    print(f"                      → {best_defense['metrics']['defense_rate']:.1f}% malicious updates blocked")
    print(f"\n  Lowest Attack:      {lowest_attack['name']}")
    print(f"                      → {lowest_attack['metrics']['attack_success_rate']:.1f}% attack success")
    
    # Recommendation
    print("\n" + "="*90)
    print("💡 RECOMMENDATION FOR PRESENTATION:")
    
    # Find the best overall method (balanced accuracy + defense)
    for result in results:
        metrics = result['metrics']
        score = metrics['final_accuracy'] * 0.6 + (1 - metrics['attack_success_rate']/100) * 0.4
        result['_score'] = score
    
    best_overall = max(results, key=lambda x: x['_score'])
    
    print(f"\n  Use: {best_overall['name']}")
    print(f"  Why: Achieves {best_overall['metrics']['final_accuracy']:.1%} accuracy while")
    print(f"       blocking {best_overall['metrics']['defense_rate']:.0f}% of malicious updates")
    print(f"       (attack success only {best_overall['metrics']['attack_success_rate']:.1f}%)")
    
    if 'Ensemble' in best_overall['name']:
        print("\n  Key Message:")
        print("  'Ensemble methods combining Trimmed Mean and Coordinate Median")
        print("   provide the strongest defense against model poisoning attacks.'")
    
    print("="*90 + "\n")
    
    # Save results
    experiment.results = {'experiments': results}
    experiment._save_results()
    
    return results


if __name__ == "__main__":
    main()
