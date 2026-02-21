"""
Comprehensive Experiment Suite for Async ARFL System

Tests:
1. Multimodal experiments (Image CNN + Text LSTM/RNN)
2. Async vs Sync performance comparison
3. Security effectiveness (Gatekeeper + SABD)
4. Aggregation method comparison
5. Byzantine defense rate analysis
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import torch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from async_federated_learning.config import Config
from async_federated_learning.main import (
    setup_data, setup_clients, run_experiment, set_seeds
)
from async_federated_learning.evaluation.metrics import ExperimentTracker
from async_federated_learning.models.cnn import FLModel
from async_federated_learning.server.fl_server import AsyncFLServer
from async_federated_learning.server.model_history import ModelHistoryBuffer
from async_federated_learning.detection.anomaly import AnomalyDetector
from async_federated_learning.detection.sabd import SABDCorrector
from async_federated_learning.detection.gatekeeper import Gatekeeper
from tqdm import tqdm


class ComprehensiveExperimentSuite:
    """Run and analyze comprehensive ARFL experiments."""
    
    def __init__(self, output_dir="results/comprehensive"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def run_single_experiment(self, name, config):
        """Run a single experiment using the proper main.py workflow."""
        print(f"\n{'='*70}")
        print(f"EXPERIMENT: {name}")
        print(f"{'='*70}")
        
        set_seeds(config.seed)
        
        # Setup data
        client_loaders, test_loader, client_indices, train_data = setup_data(config)
        
        # Setup clients  
        clients = setup_clients(config, client_loaders)
        
        # Setup server with gatekeeper
        model = FLModel(config.in_channels, config.num_classes, config.hidden_dim)
        model_history = ModelHistoryBuffer(config.model_history_size)
        sabd = SABDCorrector(config.sabd_alpha, model_history)
        anomaly = AnomalyDetector(config.anomaly_threshold, sabd)
        
        # Create gatekeeper if enabled
        gatekeeper = None
        if config.use_gatekeeper:
            gatekeeper = Gatekeeper(
                l2_threshold_factor=config.gatekeeper_l2_factor,
                min_l2_threshold=config.gatekeeper_min_threshold,
                max_l2_threshold=config.gatekeeper_max_threshold,
            )
        
        server = AsyncFLServer(model, config, test_loader, model_history, anomaly, gatekeeper)
        
        # Run training rounds
        start_time = time.time()
        round_metrics = []
        
        for round_num in tqdm(range(config.num_rounds), desc=name, unit='round'):
            metrics = server.run_round(clients)
            round_metrics.append(metrics)
        
        total_time = time.time() - start_time
        
        # Final evaluation
        final_acc, final_loss = server.evaluate_and_log()
        
        # Collect results
        history = server.metrics_history
        results = {
            "name": name,
            "config": {
                "modality": config.modality,
                "model": config.text_model_type if hasattr(config, 'text_model_type') and config.modality == "text" else "cnn",
                "num_clients": config.num_clients,
                "num_rounds": config.num_rounds,
                "async_mode": config.client_speed_variance > 0,
                "use_gatekeeper": config.use_gatekeeper,
                "aggregation_method": config.aggregation_method,
                "byzantine_fraction": config.byzantine_fraction,
            },
            "metrics": {
                "total_time": total_time,
                "avg_round_time": total_time / config.num_rounds,
                "final_accuracy": final_acc * 100,
                "final_loss": final_loss,
                "total_processed": sum(history["num_processed"]),
                "total_gatekeeper_rejected": sum(history.get("gatekeeper_rejections", [0] * len(history["num_processed"]))),
                "total_sabd_rejected": sum(history["num_discarded"]),
                "avg_staleness": np.mean(history["avg_staleness"]) if history["avg_staleness"] else 0,
            },
            "round_metrics": round_metrics,
        }
        
        # Calculate defense rate if Byzantine clients present
        if config.byzantine_fraction > 0:
            total_updates = (results["metrics"]["total_processed"] + 
                           results["metrics"]["total_gatekeeper_rejected"] + 
                           results["metrics"]["total_sabd_rejected"])
            filtered = (results["metrics"]["total_gatekeeper_rejected"] + 
                       results["metrics"]["total_sabd_rejected"])
            results["metrics"]["defense_rate"] = (filtered / total_updates * 100) if total_updates > 0 else 0
            results["metrics"]["asr"] = 100 - results["metrics"]["defense_rate"]
        
        self.results[name] = results
        
        # Print summary
        print(f"\n📊 Results Summary:")
        print(f"  Final Accuracy: {results['metrics']['final_accuracy']:.2f}%")
        print(f"  Final Loss: {results['metrics']['final_loss']:.4f}")
        print(f"  Total Time: {results['metrics']['total_time']:.2f}s")
        print(f"  Avg Round Time: {results['metrics']['avg_round_time']:.2f}s")
        print(f"  Total Processed: {results['metrics']['total_processed']}")
        print(f"  Gatekeeper Rejected: {results['metrics']['total_gatekeeper_rejected']}")
        print(f"  SABD Rejected: {results['metrics']['total_sabd_rejected']}")
        if config.byzantine_fraction > 0:
            print(f"  Defense Rate: {results['metrics']['defense_rate']:.1f}%")
            print(f"  Attack Success Rate: {results['metrics']['asr']:.1f}%")
        
        return results
    
    def _calculate_convergence_speed(self, history):
        """Calculate rounds to reach 80% of final accuracy."""
        if "accuracy" not in history or len(history["accuracy"]) == 0:
            return len(history["num_processed"])
        
        accuracies = [acc for acc in history["accuracy"] if acc > 0]
        if len(accuracies) < 2:
            return len(history["num_processed"])
        
        final_acc = accuracies[-1]
        target_acc = 0.8 * final_acc
        
        for i, acc in enumerate(accuracies):
            if acc >= target_acc:
                return i + 1
        return len(accuracies)
    
    def experiment_1_multimodal_image(self):
        """E1: Image Classification with CNN (Async + Gatekeeper)."""
        config = Config()
        config.modality = "image"
        config.num_clients = 10
        config.num_rounds = 10  # Reduced for faster testing
        config.local_epochs = 3
        config.client_speed_variance = 0.5  # Async mode
        config.use_gatekeeper = True
        config.aggregation_method = "trimmed_mean"
        config.byzantine_fraction = 0.2
        config.eval_every_n_rounds = 2
        
        return self.run_single_experiment("E1_Image_CNN_Async_Gatekeeper", config)
    
    def experiment_2_multimodal_text_lstm(self):
        """E2: Text Prediction with LSTM (Async + Gatekeeper)."""
        config = Config()
        config.modality = "text"
        config.text_model_type = "lstm"
        config.num_clients = 5
        config.num_rounds = 5  # Reduced for faster testing
        config.local_epochs = 2
        config.client_speed_variance = 0.5  # Async mode
        config.use_gatekeeper = True
        config.aggregation_method = "trimmed_mean"
        config.byzantine_fraction = 0.2
        config.eval_every_n_rounds = 1
        
        return self.run_single_experiment("E2_Text_LSTM_Async_Gatekeeper", config)
    
    def experiment_3_multimodal_text_rnn(self):
        """E3: Text Prediction with RNN (Async + Gatekeeper)."""
        config = Config()
        config.modality = "text"
        config.text_model_type = "rnn"
        config.num_clients = 5
        config.num_rounds = 5
        config.local_epochs = 2
        config.client_speed_variance = 0.5  # Async mode
        config.use_gatekeeper = True
        config.aggregation_method = "trimmed_mean"
        config.byzantine_fraction = 0.2
        config.eval_every_n_rounds = 1
        
        return self.run_single_experiment("E3_Text_RNN_Async_Gatekeeper", config)
    
    def experiment_4_async_vs_sync(self):
        """E4: Async vs Sync Performance Comparison."""
        # Sync mode
        config_sync = Config()
        config_sync.modality = "image"
        config_sync.num_clients = 10
        config_sync.num_rounds = 10
        config_sync.local_epochs = 3
        config_sync.client_speed_variance = 0  # Sync mode
        config_sync.use_gatekeeper = True
        config_sync.aggregation_method = "fedavg"
        config_sync.byzantine_fraction = 0
        config_sync.eval_every_n_rounds = 2
        
        result_sync = self.run_single_experiment("E4a_Sync_Mode", config_sync)
        
        # Async mode
        config_async = Config()
        config_async.modality = "image"
        config_async.num_clients = 10
        config_async.num_rounds = 10
        config_async.local_epochs = 3
        config_async.client_speed_variance = 0.5  # Async mode
        config_async.use_gatekeeper = True
        config_async.aggregation_method = "fedavg"
        config_async.byzantine_fraction = 0
        config_async.eval_every_n_rounds = 2
        
        result_async = self.run_single_experiment("E4b_Async_Mode", config_async)
        
        # Compare
        speedup = result_sync["metrics"]["total_time"] / result_async["metrics"]["total_time"]
        print(f"\n{'='*70}")
        print(f"ASYNC VS SYNC COMPARISON")
        print(f"{'='*70}")
        print(f"Sync: {result_sync['metrics']['total_time']:.2f}s, Acc={result_sync['metrics']['final_accuracy']:.2f}%")
        print(f"Async: {result_async['metrics']['total_time']:.2f}s, Acc={result_async['metrics']['final_accuracy']:.2f}%")
        print(f"Speedup: {speedup:.2f}x 🚀")
        
        return result_sync, result_async
    
    def experiment_5_gatekeeper_effectiveness(self):
        """E5: Gatekeeper Security Effectiveness."""
        # Without Gatekeeper
        config_no_gk = Config()
        config_no_gk.modality = "image"
        config_no_gk.num_clients = 10
        config_no_gk.num_rounds = 10
        config_no_gk.local_epochs = 3
        config_no_gk.client_speed_variance = 0.5
        config_no_gk.use_gatekeeper = False
        config_no_gk.aggregation_method = "fedavg"
        config_no_gk.byzantine_fraction = 0.3  # 30% attackers
        config_no_gk.eval_every_n_rounds = 2
        
        result_no_gk = self.run_single_experiment("E5a_Without_Gatekeeper", config_no_gk)
        
        # With Gatekeeper
        config_with_gk = Config()
        config_with_gk.modality = "image"
        config_with_gk.num_clients = 10
        config_with_gk.num_rounds = 10
        config_with_gk.local_epochs = 3
        config_with_gk.client_speed_variance = 0.5
        config_with_gk.use_gatekeeper = True
        config_with_gk.aggregation_method = "fedavg"
        config_with_gk.byzantine_fraction = 0.3  # 30% attackers
        config_with_gk.eval_every_n_rounds = 2
        
        result_with_gk = self.run_single_experiment("E5b_With_Gatekeeper", config_with_gk)
        
        # Compare
        print(f"\n{'='*70}")
        print(f"GATEKEEPER EFFECTIVENESS")
        print(f"{'='*70}")
        print(f"Without GK: Acc={result_no_gk['metrics']['final_accuracy']:.2f}%, ASR={result_no_gk['metrics']['asr']:.1f}%")
        print(f"With GK: Acc={result_with_gk['metrics']['final_accuracy']:.2f}%, ASR={result_with_gk['metrics']['asr']:.1f}%")
        print(f"Defense Improvement: {result_with_gk['metrics']['defense_rate'] - result_no_gk['metrics']['defense_rate']:.1f}%")
        
        return result_no_gk, result_with_gk
    
    def experiment_6_aggregation_methods(self):
        """E6: Aggregation Method Comparison."""
        methods = ["fedavg", "trimmed_mean", "coordinate_median"]
        results = {}
        
        for method in methods:
            config = Config()
            config.modality = "image"
            config.num_clients = 10
            config.num_rounds = 10
            config.local_epochs = 3
            config.client_speed_variance = 0.5
            config.use_gatekeeper = True
            config.aggregation_method = method
            config.byzantine_fraction = 0.4  # 40% attackers (high threat)
            config.eval_every_n_rounds = 2
            
            results[method] = self.run_single_experiment(f"E6_{method.upper()}", config)
        
        # Compare
        print(f"\n{'='*70}")
        print(f"AGGREGATION METHOD COMPARISON (40% Byzantine)")
        print(f"{'='*70}")
        for method, result in results.items():
            print(f"{method:20} → Acc={result['metrics']['final_accuracy']:.2f}%, ASR={result['metrics']['asr']:.1f}%")
        
        return results
    
    def run_all_experiments(self):
        """Run all experiments sequentially."""
        print(f"\n{'#'*70}")
        print(f"# COMPREHENSIVE ARFL EXPERIMENT SUITE")
        print(f"# Timestamp: {self.timestamp}")
        print(f"{'#'*70}\n")
        
        experiments = [
            ("Multimodal: Image (CNN)", self.experiment_1_multimodal_image),
            ("Multimodal: Text (LSTM)", self.experiment_2_multimodal_text_lstm),
            ("Multimodal: Text (RNN)", self.experiment_3_multimodal_text_rnn),
            ("Async vs Sync", self.experiment_4_async_vs_sync),
            ("Gatekeeper Effectiveness", self.experiment_5_gatekeeper_effectiveness),
            ("Aggregation Methods", self.experiment_6_aggregation_methods),
        ]
        
        for i, (name, experiment_fn) in enumerate(experiments, 1):
            print(f"\n\n{'#'*70}")
            print(f"# RUNNING EXPERIMENT {i}/{len(experiments)}: {name}")
            print(f"{'#'*70}")
            
            try:
                experiment_fn()
            except Exception as e:
                print(f"\n❌ ERROR in {name}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Generate summary
        self.generate_summary()
        
        # Save results
        self.save_results()
        
        print(f"\n{'#'*70}")
        print(f"# ALL EXPERIMENTS COMPLETE!")
        print(f"# Results saved to: {self.output_dir}")
        print(f"{'#'*70}\n")
    
    def generate_summary(self):
        """Generate comprehensive summary of all experiments."""
        print(f"\n{'='*70}")
        print(f"COMPREHENSIVE SUMMARY")
        print(f"{'='*70}\n")
        
        # Multimodal Performance
        print("1. MULTIMODAL PERFORMANCE")
        print("-" * 70)
        for exp_name in ["E1_Image_CNN_Async_Gatekeeper", "E2_Text_LSTM_Async_Gatekeeper", "E3_Text_RNN_Async_Gatekeeper"]:
            if exp_name in self.results:
                r = self.results[exp_name]
                print(f"{exp_name:40} → Acc={r['metrics']['final_accuracy']:.2f}%, Time={r['metrics']['total_time']:.1f}s")
        
        # Async vs Sync
        print("\n2. ASYNC VS SYNC PERFORMANCE")
        print("-" * 70)
        if "E4a_Sync_Mode" in self.results and "E4b_Async_Mode" in self.results:
            sync = self.results["E4a_Sync_Mode"]
            async_r = self.results["E4b_Async_Mode"]
            speedup = sync["metrics"]["total_time"] / async_r["metrics"]["total_time"]
            print(f"Sync Mode:  {sync['metrics']['total_time']:.2f}s, Acc={sync['metrics']['final_accuracy']:.2f}%")
            print(f"Async Mode: {async_r['metrics']['total_time']:.2f}s, Acc={async_r['metrics']['final_accuracy']:.2f}%")
            print(f"Speedup: {speedup:.2f}x")
        
        # Gatekeeper Effectiveness
        print("\n3. GATEKEEPER SECURITY EFFECTIVENESS")
        print("-" * 70)
        if "E5a_Without_Gatekeeper" in self.results and "E5b_With_Gatekeeper" in self.results:
            no_gk = self.results["E5a_Without_Gatekeeper"]
            with_gk = self.results["E5b_With_Gatekeeper"]
            print(f"Without Gatekeeper: ASR={no_gk['metrics']['asr']:.1f}%, Acc={no_gk['metrics']['final_accuracy']:.2f}%")
            print(f"With Gatekeeper:    ASR={with_gk['metrics']['asr']:.1f}%, Acc={with_gk['metrics']['final_accuracy']:.2f}%")
            print(f"Defense Improvement: {with_gk['metrics']['defense_rate'] - no_gk['metrics']['defense_rate']:.1f}%")
        
        # Aggregation Methods
        print("\n4. AGGREGATION METHOD ROBUSTNESS (40% Byzantine)")
        print("-" * 70)
        for method in ["fedavg", "trimmed_mean", "coordinate_median"]:
            exp_name = f"E6_{method.upper()}"
            if exp_name in self.results:
                r = self.results[exp_name]
                print(f"{method:20} → ASR={r['metrics']['asr']:.1f}%, Acc={r['metrics']['final_accuracy']:.2f}%")
        
        print("\n" + "="*70)
    
    def save_results(self):
        """Save all results to JSON file."""
        output_file = self.output_dir / f"experiment_results_{self.timestamp}.json"
        
        # Convert numpy types to native Python types for JSON serialization
        def convert_types(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(item) for item in obj]
            return obj
        
        results_serializable = convert_types(self.results)
        
        with open(output_file, 'w') as f:
            json.dump(results_serializable, f, indent=2)
        
        print(f"\n✅ Results saved to: {output_file}")
        
        # Also create a readable summary
        summary_file = self.output_dir / f"summary_{self.timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write("="*70 + "\n")
            f.write("COMPREHENSIVE ARFL EXPERIMENT RESULTS\n")
            f.write(f"Timestamp: {self.timestamp}\n")
            f.write("="*70 + "\n\n")
            
            for exp_name, result in self.results.items():
                f.write(f"\n{exp_name}\n")
                f.write("-"*70 + "\n")
                f.write(f"Configuration:\n")
                for key, val in result["config"].items():
                    f.write(f"  {key}: {val}\n")
                f.write(f"\nMetrics:\n")
                for key, val in result["metrics"].items():
                    f.write(f"  {key}: {val}\n")
                f.write("\n")
        
        print(f"✅ Summary saved to: {summary_file}")


def main():
    """Run comprehensive experiment suite."""
    suite = ComprehensiveExperimentSuite()
    suite.run_all_experiments()


if __name__ == "__main__":
    main()
