"""
experiments/robust_aggregation_comparison.py
============================================
Comprehensive Comparison of Robust Aggregation Methods

This experiment compares different aggregation strategies for defending
against Byzantine attacks (model poisoning). 

RESEARCH QUESTION:
-----------------
Which aggregation method provides the best defense against malicious clients?

TESTED CONFIGURATIONS:
---------------------
1. FedAvg (Baseline) - No defense
2. FedAvg + Outlier Filter - Simple averaging with preprocessing
3. Trimmed Mean - Removes extreme values per coordinate
4. Trimmed Mean + Outlier Filter - Combined defense
5. Coordinate Median - Takes median per coordinate
6. Coordinate Median + Outlier Filter - Combined defense
7. Ensemble (Trimmed Mean + Median) - Averages both methods
8. Full Pipeline (Outlier Filter → Trimmed Mean → Median) - All defenses

METRICS:
--------
- Final Accuracy: Model performance on test set
- Attack Success Rate: How many malicious updates affected the model
- Defense Rate: Percentage of Byzantine updates successfully filtered
- Convergence Speed: Rounds needed to reach target accuracy
- Robustness Score: Accuracy under attack / Accuracy without attack
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import Dict, List

import numpy as np
import torch
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from main import setup_data, setup_clients
from models.cnn import FLModel
from server.fl_server import AsyncFLServer
from detection.gatekeeper import Gatekeeper
from detection.outlier_filter import OutlierFilter
from detection.sabd import SABDCorrector
from detection.anomaly import AnomalyDetector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class RobustAggregationExperiment:
    """
    Systematic comparison of robust aggregation methods.
    """
    
    def __init__(self, base_config: Config):
        self.base_config = base_config
        self.results = {}
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def run_single_experiment(
        self, 
        name: str, 
        config: Config,
        use_outlier_filter: bool = False,
        outlier_method: str = 'ensemble',
        use_trimmed_mean: bool = False,
        use_median: bool = False,
        use_ensemble: bool = False
    ) -> Dict:
        """
        Run a single experiment with specified configuration.
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"EXPERIMENT: {name}")
        logger.info(f"{'='*70}")
        logger.info(f"Config: outlier_filter={use_outlier_filter}, "
                   f"trimmed_mean={use_trimmed_mean}, median={use_median}, "
                   f"ensemble={use_ensemble}")
        
        # Setup data and clients
        client_dataloaders, test_dataloader, client_indices, train_dataset = setup_data(config)
        clients = setup_clients(config, client_dataloaders)
        
        # Create model
        model = FLModel(
            in_channels=1 if config.modality == "image" else None,
            num_classes=10,
            hidden_dim=config.hidden_dim
        )
        
        # Setup detection mechanisms
        from server.model_history import ModelHistoryBuffer
        model_history = ModelHistoryBuffer(max_size=15)
        sabd = SABDCorrector(alpha=0.5, model_history=model_history)
        anomaly_detector = AnomalyDetector(threshold=2.5, sabd=sabd)
        
        # Setup outlier filter if requested
        outlier_filter = None
        if use_outlier_filter:
            outlier_filter = OutlierFilter(
                method=outlier_method,
                iqr_factor=1.5,
                zscore_threshold=3.0,
                mad_threshold=3.0,
                ensemble_vote_threshold=2
            )
            logger.info(f"Outlier filter enabled: method={outlier_method}")
        
        # Setup gatekeeper (always enabled for basic protection)
        gatekeeper = Gatekeeper() if config.use_gatekeeper else None
        
        # Override aggregation method based on experiment
        if use_ensemble:
            original_method = config.aggregation_method
            config.aggregation_method = 'ensemble'
        elif use_trimmed_mean:
            config.aggregation_method = 'trimmed_mean'
        elif use_median:
            config.aggregation_method = 'coordinate_median'
        
        # Create server with custom aggregation
        server = AsyncFLServer(
            model=model,
            aggregation_method=config.aggregation_method,
            anomaly_detector=anomaly_detector,
            gatekeeper=gatekeeper,
            device=config.device,
            async_mode=config.client_speed_variance
        )
        
        # Training metrics
        accuracies = []
        losses = []
        defense_stats = {
            'gatekeeper_rejected': 0,
            'outlier_rejected': 0,
            'sabd_rejected': 0,
            'total_updates': 0,
            'byzantine_updates': 0
        }
        
        # Training loop
        start_time = time.time()
        
        for round_num in tqdm(range(1, config.num_rounds + 1), 
                             desc=name, 
                             unit="round"):
            
            # Run training round with custom outlier filtering
            if outlier_filter is not None:
                metrics = self._run_round_with_outlier_filter(
                    server, clients, outlier_filter, defense_stats
                )
            else:
                metrics = server.run_round(clients)
                defense_stats['total_updates'] += metrics.get('processed', 0)
                defense_stats['gatekeeper_rejected'] += metrics.get('gatekeeper_rejected', 0)
                defense_stats['sabd_rejected'] += metrics.get('sabd_rejected', 0)
            
            # Evaluation
            if round_num % config.eval_every_n_rounds == 0:
                from evaluation.metrics import evaluate_model
                accuracy, avg_loss = evaluate_model(
                    server.model,
                    test_dataloader,
                    config.device
                )
                accuracies.append(accuracy)
                losses.append(avg_loss)
                
                logger.info(
                    f"Round {round_num} — accuracy={accuracy:.4f}, loss={avg_loss:.4f}"
                )
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Calculate defense rate
        total_rejected = (defense_stats['gatekeeper_rejected'] + 
                         defense_stats['outlier_rejected'] + 
                         defense_stats['sabd_rejected'])
        defense_rate = (total_rejected / defense_stats['total_updates'] * 100 
                       if defense_stats['total_updates'] > 0 else 0)
        
        # Calculate attack success rate (inverse of defense rate for Byzantine updates)
        byzantine_fraction = config.byzantine_fraction
        expected_byzantine = defense_stats['total_updates'] * byzantine_fraction
        attack_success_rate = 0
        if expected_byzantine > 0:
            attack_success_rate = max(0, 100 - (total_rejected / expected_byzantine * 100))
        
        result = {
            'name': name,
            'config': {
                'aggregation_method': config.aggregation_method,
                'outlier_filter': use_outlier_filter,
                'outlier_method': outlier_method if use_outlier_filter else None,
                'byzantine_fraction': config.byzantine_fraction,
                'num_clients': config.num_clients,
                'num_rounds': config.num_rounds
            },
            'metrics': {
                'final_accuracy': accuracies[-1] if accuracies else 0,
                'max_accuracy': max(accuracies) if accuracies else 0,
                'accuracies': accuracies,
                'losses': losses,
                'total_time': total_time,
                'avg_time_per_round': total_time / config.num_rounds,
                'defense_rate': defense_rate,
                'attack_success_rate': attack_success_rate,
                'total_updates': defense_stats['total_updates'],
                'gatekeeper_rejected': defense_stats['gatekeeper_rejected'],
                'outlier_rejected': defense_stats['outlier_rejected'],
                'sabd_rejected': defense_stats['sabd_rejected'],
                'total_rejected': total_rejected
            }
        }
        
        logger.info(f"\n{'='*70}")
        logger.info(f"RESULTS: {name}")
        logger.info(f"Final Accuracy: {result['metrics']['final_accuracy']:.2%}")
        logger.info(f"Defense Rate: {result['metrics']['defense_rate']:.2f}%")
        logger.info(f"Attack Success: {result['metrics']['attack_success_rate']:.2f}%")
        logger.info(f"Total Time: {result['metrics']['total_time']:.1f}s")
        logger.info(f"{'='*70}\n")
        
        return result
    
    def _run_round_with_outlier_filter(
        self, 
        server: AsyncFLServer,
        clients: List,
        outlier_filter: OutlierFilter,
        defense_stats: Dict
    ) -> Dict:
        """
        Run a training round with outlier filtering applied BEFORE aggregation.
        """
        from server.fl_server import ClientUpdate
        
        # Collect updates from clients
        updates = []
        client_ids = []
        
        for client in clients:
            # Get client update
            update_dict = client.get_update(server.get_global_weights())
            
            if update_dict is not None:
                updates.append(update_dict)
                client_ids.append(client.client_id)
        
        defense_stats['total_updates'] += len(updates)
        
        # Apply outlier filter
        filtered_updates, accepted_idx, rejected_idx = outlier_filter.filter_updates(
            updates, client_ids
        )
        defense_stats['outlier_rejected'] += len(rejected_idx)
        
        # Convert to ClientUpdate objects for server
        client_updates = []
        for i in accepted_idx:
            client_updates.append(
                ClientUpdate(
                    client_id=client_ids[i],
                    update=updates[i],
                    model_version=1,
                    timestamp=time.time(),
                    staleness=0
                )
            )
        
        # Process through server's normal pipeline (gatekeeper + SABD + aggregation)
        if len(client_updates) > 0:
            server.pending_updates.extend(client_updates)
            metrics = server._process_pending_updates()
            
            defense_stats['gatekeeper_rejected'] += metrics.get('gatekeeper_rejected', 0)
            defense_stats['sabd_rejected'] += metrics.get('sabd_rejected', 0)
        else:
            metrics = {'processed': 0}
        
        return metrics
    
    def run_all_experiments(self):
        """
        Run all experiment configurations and compare results.
        """
        print("\n" + "="*70)
        print("ROBUST AGGREGATION COMPARISON EXPERIMENT SUITE")
        print("="*70)
        print(f"Byzantine Fraction: {self.base_config.byzantine_fraction * 100}%")
        print(f"Number of Clients: {self.base_config.num_clients}")
        print(f"Training Rounds: {self.base_config.num_rounds}")
        print("="*70 + "\n")
        
        experiments = []
        
        # 1. Baseline: FedAvg (no defense)
        config1 = self._create_config(aggregation='fedavg', use_gatekeeper=False)
        result1 = self.run_single_experiment(
            "1_FedAvg_Baseline",
            config1,
            use_outlier_filter=False
        )
        experiments.append(result1)
        
        # 2. FedAvg + Outlier Filter
        config2 = self._create_config(aggregation='fedavg', use_gatekeeper=False)
        result2 = self.run_single_experiment(
            "2_FedAvg_OutlierFilter",
            config2,
            use_outlier_filter=True,
            outlier_method='ensemble'
        )
        experiments.append(result2)
        
        # 3. Trimmed Mean
        config3 = self._create_config(aggregation='trimmed_mean', use_gatekeeper=False)
        result3 = self.run_single_experiment(
            "3_TrimmedMean",
            config3,
            use_trimmed_mean=True
        )
        experiments.append(result3)
        
        # 4. Trimmed Mean + Outlier Filter
        config4 = self._create_config(aggregation='trimmed_mean', use_gatekeeper=False)
        result4 = self.run_single_experiment(
            "4_TrimmedMean_OutlierFilter",
            config4,
            use_outlier_filter=True,
            outlier_method='ensemble',
            use_trimmed_mean=True
        )
        experiments.append(result4)
        
        # 5. Coordinate Median
        config5 = self._create_config(aggregation='coordinate_median', use_gatekeeper=False)
        result5 = self.run_single_experiment(
            "5_CoordinateMedian",
            config5,
            use_median=True
        )
        experiments.append(result5)
        
        # 6. Coordinate Median + Outlier Filter
        config6 = self._create_config(aggregation='coordinate_median', use_gatekeeper=False)
        result6 = self.run_single_experiment(
            "6_CoordinateMedian_OutlierFilter",
            config6,
            use_outlier_filter=True,
            outlier_method='ensemble',
            use_median=True
        )
        experiments.append(result6)
        
        # 7. Ensemble (Trimmed Mean + Median average)
        config7 = self._create_config(aggregation='ensemble', use_gatekeeper=False)
        result7 = self.run_single_experiment(
            "7_Ensemble_TrimmedMean_Median",
            config7,
            use_ensemble=True
        )
        experiments.append(result7)
        
        # 8. Full Pipeline: Outlier Filter → Trimmed Mean
        config8 = self._create_config(aggregation='trimmed_mean', use_gatekeeper=True)
        result8 = self.run_single_experiment(
            "8_FullPipeline_Outlier_TrimmedMean_Gatekeeper",
            config8,
            use_outlier_filter=True,
            outlier_method='ensemble',
            use_trimmed_mean=True
        )
        experiments.append(result8)
        
        # Save and display results
        self.results = {'experiments': experiments}
        self._save_results()
        self._display_comparison()
        
        return self.results
    
    def _create_config(self, aggregation: str, use_gatekeeper: bool) -> Config:
        """Create a config with specified aggregation method."""
        config = Config()
        config.modality = self.base_config.modality
        config.num_clients = self.base_config.num_clients
        config.num_rounds = self.base_config.num_rounds
        config.local_epochs = self.base_config.local_epochs
        config.byzantine_fraction = self.base_config.byzantine_fraction
        config.attack_type = self.base_config.attack_type
        config.aggregation_method = aggregation
        config.use_gatekeeper = use_gatekeeper
        config.client_speed_variance = 0  # Sync mode for fair comparison
        config.eval_every_n_rounds = 1
        return config
    
    def _save_results(self):
        """Save results to JSON and text files."""
        results_dir = "results/robust_aggregation"
        os.makedirs(results_dir, exist_ok=True)
        
        # Save JSON
        json_path = os.path.join(results_dir, f"comparison_{self.timestamp}.json")
        with open(json_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Results saved to: {json_path}")
    
    def _display_comparison(self):
        """Display comparison table of all experiments."""
        print("\n" + "="*100)
        print("ROBUST AGGREGATION COMPARISON RESULTS")
        print("="*100)
        print(f"{'Experiment':<45} {'Accuracy':>10} {'Defense':>10} {'Attack Success':>15} {'Time(s)':>10}")
        print("-"*100)
        
        for exp in self.results['experiments']:
            name = exp['name']
            metrics = exp['metrics']
            print(f"{name:<45} "
                  f"{metrics['final_accuracy']:>9.2%} "
                  f"{metrics['defense_rate']:>9.1f}% "
                  f"{metrics['attack_success_rate']:>14.1f}% "
                  f"{metrics['total_time']:>10.1f}")
        
        print("="*100)
        
        # Find best methods
        experiments = self.results['experiments']
        best_accuracy = max(experiments, key=lambda x: x['metrics']['final_accuracy'])
        best_defense = max(experiments, key=lambda x: x['metrics']['defense_rate'])
        lowest_attack = min(experiments, key=lambda x: x['metrics']['attack_success_rate'])
        
        print("\n🏆 WINNERS:")
        print(f"  Best Accuracy:     {best_accuracy['name']} ({best_accuracy['metrics']['final_accuracy']:.2%})")
        print(f"  Best Defense Rate: {best_defense['name']} ({best_defense['metrics']['defense_rate']:.1f}%)")
        print(f"  Lowest Attack:     {lowest_attack['name']} ({lowest_attack['metrics']['attack_success_rate']:.1f}%)")
        print("="*100 + "\n")


def main():
    """Run robust aggregation comparison experiments."""
    
    # Base configuration
    config = Config()
    config.modality = "image"
    config.num_clients = 10
    config.num_rounds = 10
    config.local_epochs = 2
    config.byzantine_fraction = 0.3  # 30% malicious clients
    config.attack_type = "sign_flipping"  # Strong attack
    
    # Run experiments
    experiment = RobustAggregationExperiment(config)
    results = experiment.run_all_experiments()
    
    return results


if __name__ == "__main__":
    main()
