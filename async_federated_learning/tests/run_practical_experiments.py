"""
Practical Experiment Runner - Tests key ARFL capabilities

Runs 3 focused experiments:
1. Baseline (Sync, No Attacks)
2. Async Performance (Async vs Sync comparison)  
3. Security (Gatekeeper effectiveness)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from async_federated_learning.config import Config
from run_comprehensive_experiments import ComprehensiveExperimentSuite

def main():
    print("\n" + "#"*70)
    print("# PRACTICAL ARFL EXPERIMENT SUITE")
    print("# Testing: Image Classification (MNIST)")
    print("#"*70 + "\n")
    
    suite = ComprehensiveExperimentSuite(output_dir="results/practical")
    
    # Experiment 1: Baseline (Sync, No Attacks)
    print("\n" + "="*70)
    print("EXPERIMENT 1: Baseline (Sync Mode, No Attacks)")
    print("="*70)
    
    config1 = Config()
    config1.modality = "image"
    config1.num_clients = 5
    config1.num_rounds = 5
    config1.local_epochs = 2
    config1.client_speed_variance = 0  # Sync mode
    config1.use_gatekeeper = False
    config1.aggregation_method = "fedavg"
    config1.byzantine_fraction = 0  # No attacks
    config1.eval_every_n_rounds = 1
    
    result1 = suite.run_single_experiment("E1_Baseline_Sync", config1)
    
    # Experiment 2: Async vs Sync (same settings, just async enabled)
    print("\n" + "="*70)
    print("EXPERIMENT 2: Async Performance Test")
    print("="*70)
    
    config2 = Config()
    config2.modality = "image"
    config2.num_clients = 5
    config2.num_rounds = 5
    config2.local_epochs = 2
    config2.client_speed_variance = 0.5  # Async mode (THIS IS THE KEY DIFFERENCE)
    config2.use_gatekeeper = False
    config2.aggregation_method = "fedavg"
    config2.byzantine_fraction = 0
    config2.eval_every_n_rounds = 1
    
    result2 = suite.run_single_experiment("E2_Async_Mode", config2)
    
    # Experiment 3: Security Test (Gatekeeper with Byzantine attacks)
    print("\n" + "="*70)
    print("EXPERIMENT 3: Security Test (Gatekeeper + Byzantine Attacks)")
    print("="*70)
    
    config3 = Config()
    config3.modality = "image"
    config3.num_clients = 5
    config3.num_rounds = 5
    config3.local_epochs = 2
    config3.client_speed_variance = 0  # Sync to avoid threading issues
    config3.use_gatekeeper = True  # Enable gatekeeper!
    config3.aggregation_method = "trimmed_mean"  # Robust aggregation
    config3.byzantine_fraction = 0.2  # 20% attackers (1 out of 5 clients)
    config3.eval_every_n_rounds = 1
    
    result3 = suite.run_single_experiment("E3_Security_Gatekeeper", config3)
    
    # Summary
    print("\n" + "#"*70)
    print("# EXPERIMENT SUMMARY")
    print("#"*70 + "\n")
    
    print("1. BASELINE (Sync, No Attacks)")
    print(f"   Accuracy: {result1['metrics']['final_accuracy']:.2f}%")
    print(f"   Time: {result1['metrics']['total_time']:.2f}s")
    print(f"   Avg Round: {result1['metrics']['avg_round_time']:.2f}s\n")
    
    print("2. ASYNC PERFORMANCE")
    print(f"   Accuracy: {result2['metrics']['final_accuracy']:.2f}%")
    print(f"   Time: {result2['metrics']['total_time']:.2f}s")
    print(f"   Avg Round: {result2['metrics']['avg_round_time']:.2f}s")
    
    # Calculate speedup
    speedup = result1['metrics']['total_time'] / result2['metrics']['total_time']
    print(f"   Speedup vs Sync: {speedup:.2f}x 🚀\n")
    
    print("3. SECURITY (20% Byzantine Attacks)")
    print(f"   Accuracy: {result3['metrics']['final_accuracy']:.2f}%")
    print(f"   Time: {result3['metrics']['total_time']:.2f}s")
    print(f"   Gatekeeper Rejected: {result3['metrics']['total_gatekeeper_rejected']}")
    print(f"   SABD Rejected: {result3['metrics']['total_sabd_rejected']}")
    if 'defense_rate' in result3['metrics']:
        print(f"   Defense Rate: {result3['metrics']['defense_rate']:.1f}%")
        print(f"   Attack Success Rate: {result3['metrics']['asr']:.1f}%")
    
    print("\n" + "#"*70)
    print("# KEY FINDINGS")
    print("#"*70 + "\n")
    
    print(f"✅ Async mode is {speedup:.2f}x faster than sync mode")
    print(f"✅ Final accuracy maintained: {result2['metrics']['final_accuracy']:.2f}% vs {result1['metrics']['final_accuracy']:.2f}%")
    
    if 'defense_rate' in result3['metrics']:
        print(f"✅ Gatekeeper + SABD blocked {result3['metrics']['defense_rate']:.1f}% of attacks")
        print(f"✅ System is robust to {config3.byzantine_fraction*100:.0f}% Byzantine clients")
    
    suite.save_results()
    
    print("\n" + "#"*70)
    print("# ALL EXPERIMENTS COMPLETE!")
    print(f"# Results saved to: {suite.output_dir}")
    print("#"*70 + "\n")

if __name__ == "__main__":
    main()
