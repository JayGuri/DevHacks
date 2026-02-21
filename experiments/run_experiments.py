# experiments/run_experiments.py — Batch experiment runner (offline FL simulation)
import os
import sys
import json
import time
import logging
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from aggregation.aggregator import Aggregator, AggregationResult

logger = logging.getLogger("fedbuff.experiments")


def create_synthetic_update(client_id: str, task: str, round_num: int,
                            param_shapes: dict, is_malicious: bool = False,
                            attack_scale: float = -5.0) -> dict:
    """Create a synthetic weight update for experiments."""
    weights = {}
    for name, shape in param_shapes.items():
        # Honest update: small random perturbation
        w = np.random.normal(0, 0.01, shape).astype(np.float32)
        if is_malicious:
            w = w * attack_scale
        weights[name] = w

    return {
        "client_id": client_id,
        "task": task,
        "round_num": round_num,
        "global_round_received": max(0, round_num - 1),
        "weights": weights,
        "num_samples": np.random.randint(50, 200),
        "local_loss": np.random.uniform(0.5, 2.0) if not is_malicious else np.random.uniform(0.5, 2.0),
        "timestamp": time.time(),
    }


def get_param_shapes(task: str) -> dict:
    """Get parameter shapes for a task's model."""
    from models.cnn import get_model
    model = get_model(task)
    shapes = {}
    for name, param in model.named_parameters():
        shapes[name] = tuple(param.shape)
    return shapes


def simulate_round(task: str, num_clients: int, strategy: str,
                   include_malicious: bool, round_num: int) -> AggregationResult:
    """
    Creates synthetic updates and runs Aggregator.aggregate().
    Returns AggregationResult.
    """
    param_shapes = get_param_shapes(task)

    # Create client IDs
    honest_clients = [f"honest-{i}" for i in range(num_clients - (1 if include_malicious else 0))]
    malicious_clients = ["mallory"] if include_malicious else []

    updates = []
    for cid in honest_clients:
        updates.append(create_synthetic_update(
            cid, task, round_num, param_shapes, is_malicious=False
        ))
    for cid in malicious_clients:
        updates.append(create_synthetic_update(
            cid, task, round_num, param_shapes, is_malicious=True, attack_scale=-5.0
        ))

    # Run aggregation
    config = settings
    aggregator = Aggregator(strategy, config)
    result = aggregator.aggregate(updates, round_num, task)
    return result


def run_experiment(config_dict: dict) -> dict:
    """
    Runs N rounds of FL simulation, recording loss and trust scores per round.
    config_dict keys: task, strategy, num_rounds, num_clients, include_malicious
    """
    task = config_dict["task"]
    strategy = config_dict["strategy"]
    num_rounds = config_dict.get("num_rounds", 10)
    num_clients = config_dict.get("num_clients", 3)
    include_malicious = config_dict.get("include_malicious", True)

    results = {
        "task": task,
        "strategy": strategy,
        "num_rounds": num_rounds,
        "num_clients": num_clients,
        "include_malicious": include_malicious,
        "rounds": [],
    }

    for round_num in range(1, num_rounds + 1):
        agg_result = simulate_round(task, num_clients, strategy,
                                    include_malicious, round_num)
        round_data = {
            "round": round_num,
            "accepted_count": agg_result.accepted_count,
            "gatekeeper_rejected": agg_result.gatekeeper_rejected,
            "rejected_clients": agg_result.rejected_clients,
            "trust_scores": agg_result.trust_scores,
            "strategy_used": agg_result.strategy_used,
        }
        results["rounds"].append(round_data)

    return results


def save_results(results: dict, filepath: str) -> None:
    """Saves experiment results to JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Results saved to %s", filepath)


def main():
    """Run a sweep across strategies for both tasks."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    strategies = ["fedavg", "coordinate_median", "trimmed_mean", "krum"]
    tasks = ["femnist", "shakespeare"]
    num_rounds = 10
    num_clients = 4

    all_results = {}

    print("\n" + "=" * 80)
    print("FedBuff Experiment Sweep")
    print("=" * 80)

    for task in tasks:
        for strategy in strategies:
            print(f"\n--- Running: task={task}, strategy={strategy} ---")
            config_dict = {
                "task": task,
                "strategy": strategy,
                "num_rounds": num_rounds,
                "num_clients": num_clients,
                "include_malicious": True,
            }

            results = run_experiment(config_dict)

            key = f"{task}_{strategy}"
            all_results[key] = results

            # Save individual result
            filepath = os.path.join("results", f"experiment_{key}.json")
            save_results(results, filepath)

    # Print summary table
    print("\n" + "=" * 80)
    print(f"{'Task':<15} {'Strategy':<20} {'Rounds':<8} {'Mallory Rejected':<20} {'Avg Accepted':<15}")
    print("-" * 80)

    for key, result in all_results.items():
        task = result["task"]
        strategy = result["strategy"]
        rounds = result["num_rounds"]

        mallory_rejected_count = 0
        total_accepted = 0
        for rd in result["rounds"]:
            if "mallory" in rd.get("gatekeeper_rejected", []) or \
               "mallory" in rd.get("rejected_clients", []):
                mallory_rejected_count += 1
            total_accepted += rd["accepted_count"]

        avg_accepted = total_accepted / max(rounds, 1)
        print(
            f"{task:<15} {strategy:<20} {rounds:<8} "
            f"{mallory_rejected_count}/{rounds:<18} {avg_accepted:<15.1f}"
        )

    print("=" * 80)

    # Save combined results
    combined_path = os.path.join("results", "experiment_sweep_all.json")
    save_results(all_results, combined_path)
    print(f"\nAll results saved to {combined_path}")


if __name__ == "__main__":
    main()
