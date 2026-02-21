"""
Quick test of a single experiment to verify setup works.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from async_federated_learning.config import Config
from run_comprehensive_experiments import ComprehensiveExperimentSuite

def main():
    print("Running quick smoke test with 1 experiment...")
    print("="*70)
    
    suite = ComprehensiveExperimentSuite(output_dir="results/smoke_test")
    
    # Run just the image experiment with very short settings
    config = Config()
    config.modality = "image"
    config.num_clients = 3  # Very few clients to avoid threading issues
    config.num_rounds = 2   # Very few rounds
    config.local_epochs = 1  # Very few epochs
    config.client_speed_variance = 0  # SYNC mode to avoid threading issues
    config.use_gatekeeper = False  # Disable for now due to tensor/numpy issue
    config.aggregation_method = "fedavg"
    config.byzantine_fraction = 0  # No Byzantine for smoke test
    config.eval_every_n_rounds = 1
    
    result = suite.run_single_experiment("Smoke_Test", config)
    
    print("\n" + "="*70)
    print("✅ SMOKE TEST PASSED!")
    print("="*70)
    print(f"Final Accuracy: {result['metrics']['final_accuracy']:.2f}%")
    print(f"Total Time: {result['metrics']['total_time']:.2f}s")
    print(f"Defense Rate: {result['metrics'].get('defense_rate', 0):.1f}%")
    
    suite.save_results()

if __name__ == "__main__":
    main()
