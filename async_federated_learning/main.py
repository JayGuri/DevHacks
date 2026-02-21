"""
main.py
=======
Entry point for the Async Robust Federated Learning (ARFL) framework.

Usage examples
--------------
# Run full 4-experiment comparison suite (default MNIST, 50 rounds)
    python -m async_federated_learning.main

# Quick smoke test (3 clients, 2 rounds — verifies all imports and plumbing)
    python -m async_federated_learning.main --smoke_test

# Verify all module imports without running training
    python -m async_federated_learning.main --check

# CIFAR-10, more clients, coordinate-median aggregation, no DP
    python -m async_federated_learning.main \\
        --dataset CIFAR10 --in_channels 3 --num_clients 20 \\
        --aggregation coordinate_median --no_dp

Experiment suite
----------------
E1: FedAvg  — No Attack  (baseline)
E2: FedAvg  — 20% Byzantine sign-flip  (shows vulnerability)
E3: Trimmed Mean  — 20% Byzantine  (robust aggregation)
E4: Coordinate Median — 20% Byzantine  (robust aggregation)
"""

import logging

import numpy as np
import torch
from tqdm import tqdm

from async_federated_learning.client.fl_client import FLClient
from async_federated_learning.config import Config
from async_federated_learning.data.partitioner import DataPartitioner
from async_federated_learning.detection.anomaly import AnomalyDetector
from async_federated_learning.detection.sabd import SABDCorrector
from async_federated_learning.evaluation.metrics import ExperimentTracker
from async_federated_learning.models.cnn import FLModel
from async_federated_learning.server.fl_server import AsyncFLServer
from async_federated_learning.server.model_history import ModelHistoryBuffer

# ---------------------------------------------------------------------------
# Logging — configured at module level per spec
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Derived-field names that must be stripped before passing to_dict() into
# Config() — these are init=False fields recomputed by __post_init__.
# ---------------------------------------------------------------------------
_DERIVED_CONFIG_FIELDS = frozenset({'num_byzantine_clients', 'num_honest_clients'})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def set_seeds(seed: int) -> None:
    """Set all random seeds for reproducibility."""
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def setup_data(config: Config) -> tuple:
    """
    Load dataset and partition across clients.

    Returns
    -------
    tuple
        ``(client_dataloaders, test_dataloader, client_indices, train_dataset)``
    """
    partitioner = DataPartitioner()
    train, test = partitioner.load_dataset(config.dataset_name, config.data_dir)

    client_indices = partitioner.partition_data(
        train, config.num_clients, config.dirichlet_alpha
    )
    client_dataloaders = [
        partitioner.get_client_dataloader(train, idx, config.batch_size)
        for idx in client_indices
    ]
    test_dataloader = partitioner.get_test_dataloader(test)

    return client_dataloaders, test_dataloader, client_indices, train


def setup_clients(
    config: Config,
    client_dataloaders: list,
    byzantine_fraction: float = None,
    attack_type: str = None,
) -> list:
    """
    Instantiate FL clients with correct Byzantine assignments.

    The first ``num_byzantine`` clients (by index) are assigned as Byzantine.
    An assertion verifies the count matches expectation.

    Parameters
    ----------
    config              : Config        Experiment configuration.
    client_dataloaders  : list          One DataLoader per client.
    byzantine_fraction  : float | None  Overrides ``config.byzantine_fraction``.
    attack_type         : str | None    Overrides ``config.attack_type``.

    Returns
    -------
    list[FLClient]
    """
    bf  = byzantine_fraction if byzantine_fraction is not None else config.byzantine_fraction
    at  = attack_type or config.attack_type
    num_byz = int(config.num_clients * bf)

    clients = []
    for i, dl in enumerate(client_dataloaders):
        is_byz = i < num_byz
        clients.append(
            FLClient(
                i, dl, config,
                is_byzantine=is_byz,
                attack_type=at if is_byz else 'none',
            )
        )

    actual_byz = sum(1 for c in clients if c.is_byzantine)
    assert actual_byz == num_byz, (
        f'Byzantine count mismatch: expected {num_byz}, got {actual_byz}'
    )
    logger.info(
        'setup_clients — %d total (%d Byzantine, %d honest), attack=%s.',
        len(clients), num_byz, len(clients) - num_byz,
        at if num_byz > 0 else 'none',
    )
    return clients


def run_experiment(
    name: str,
    config: Config,
    client_dataloaders: list,
    test_dataloader,
    aggregation_method: str,
    byzantine_fraction: float,
    attack_type: str = 'sign_flipping',
) -> dict:
    """
    Run one complete FL experiment and return metrics.

    Creates a fresh config, model, SABD, anomaly detector, clients, and server
    for each experiment so there is no state leakage between runs.

    Parameters
    ----------
    name               : str   Human-readable experiment label.
    config             : Config Base configuration (overridden by the method/fraction args).
    client_dataloaders : list  Per-client DataLoaders (shared across experiments).
    test_dataloader    :       Held-out test set.
    aggregation_method : str   Aggregation strategy to use.
    byzantine_fraction : float Fraction of Byzantine clients for this experiment.
    attack_type        : str   Attack type to inject.

    Returns
    -------
    dict with keys ``metrics``, ``staleness``, ``name``.
    """
    set_seeds(config.seed)

    # Build a new Config with just the aggregation method overridden.
    # Filter out init=False derived fields before passing to Config().
    base_dict = {
        k: v for k, v in config.to_dict().items()
        if k not in _DERIVED_CONFIG_FIELDS
    }
    exp_config = Config(**{**base_dict, 'aggregation_method': aggregation_method})

    model        = FLModel(exp_config.in_channels, exp_config.num_classes, exp_config.hidden_dim)
    model_history = ModelHistoryBuffer(exp_config.model_history_size)
    sabd         = SABDCorrector(exp_config.sabd_alpha, model_history)
    anomaly      = AnomalyDetector(exp_config.anomaly_threshold, sabd)
    clients      = setup_clients(exp_config, client_dataloaders, byzantine_fraction, attack_type)
    server       = AsyncFLServer(model, exp_config, test_dataloader, model_history, anomaly)

    all_staleness = []
    logger.info('Starting experiment: %s', name)

    for _round_num in tqdm(range(exp_config.num_rounds), desc=name, unit='round'):
        metrics = server.run_round(clients)
        if 'avg_staleness' in metrics:
            all_staleness.append(metrics['avg_staleness'])

    # Final evaluation at the end of training (regardless of eval cadence)
    server.evaluate_and_log()

    return {
        'metrics':  server.get_metrics(),
        'staleness': all_staleness,
        'name':      name,
    }


# ---------------------------------------------------------------------------
# Experiment suite
# ---------------------------------------------------------------------------

def run_all_experiments(config: Config) -> None:
    """
    Run the 4-experiment comparison suite and save all plots and reports.

    Experiments
    -----------
    E1: FedAvg   — 0 % Byzantine    (baseline)
    E2: FedAvg   — 20 % Byzantine   (shows vulnerability)
    E3: Trimmed Mean — 20 % Byzantine   (robust)
    E4: Coord. Median — 20 % Byzantine  (robust)
    """
    client_dataloaders, test_dataloader, client_indices, train_ds = setup_data(config)

    tracker = ExperimentTracker(config)
    tracker.plot_data_distribution(
        client_indices, train_ds, config.num_classes,
        save_path=f'{config.output_dir}/data_distribution.png',
    )

    experiments = [
        {
            'name': 'E1: FedAvg — No Attack (Baseline)',
            'aggregation': 'fedavg',
            'byzantine_fraction': 0.0,
        },
        {
            'name': 'E2: FedAvg — Byzantine Attack (Vulnerable)',
            'aggregation': 'fedavg',
            'byzantine_fraction': 0.2,
        },
        {
            'name': 'E3: Trimmed Mean — Byzantine Attack (Robust)',
            'aggregation': 'trimmed_mean',
            'byzantine_fraction': 0.2,
        },
        {
            'name': 'E4: Coord. Median — Byzantine Attack (Robust)',
            'aggregation': 'coordinate_median',
            'byzantine_fraction': 0.2,
        },
    ]

    all_results  = {}
    all_staleness = []

    for exp in experiments:
        result = run_experiment(
            exp['name'], config,
            client_dataloaders, test_dataloader,
            exp['aggregation'], exp['byzantine_fraction'],
        )
        all_results[exp['name']] = {
            'rounds':   result['metrics']['round'],
            'accuracy': result['metrics']['accuracy'],
        }
        all_staleness.extend(result['staleness'])

    # ── Plots and reports ────────────────────────────────────────────────
    tracker.plot_convergence_comparison(all_results)
    tracker.plot_staleness_distribution(all_staleness)
    tracker.generate_summary_report(all_results)
    tracker.save_round_metrics_csv(all_results)

    # ── Console summary ──────────────────────────────────────────────────
    print('\n' + '=' * 65)
    print('FINAL RESULTS')
    print('=' * 65)
    print(f"{'Experiment':<45} {'Final Acc':>10} {'Best Acc':>10}")
    print('-' * 65)
    for name, data in all_results.items():
        if data['accuracy']:
            print(
                f"{name:<45} "
                f"{data['accuracy'][-1]:>9.1%} "
                f"{max(data['accuracy']):>9.1%}"
            )
    print('=' * 65)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def run_smoke_test() -> None:
    """
    Minimal 3-client, 2-round sanity check.

    Verifies that all imports work, the full pipeline runs without error,
    and the model achieves better than random accuracy after 2 rounds.

    Raises
    ------
    AssertionError   If test accuracy ≤ 5 % (worse than random on MNIST).
    """
    logger.info('Running smoke test…')

    config = Config(
        num_clients=3,
        num_rounds=2,
        byzantine_fraction=0.0,
        use_dp=False,
        client_speed_variance=False,
        eval_every_n_rounds=1,
    )

    client_dataloaders, test_dataloader, _, _ = setup_data(config)

    model         = FLModel(config.in_channels, config.num_classes, config.hidden_dim)
    model_history = ModelHistoryBuffer(config.model_history_size)
    sabd          = SABDCorrector(config.sabd_alpha, model_history)
    anomaly       = AnomalyDetector(config.anomaly_threshold, sabd)
    clients       = setup_clients(config, client_dataloaders, 0.0)
    server        = AsyncFLServer(model, config, test_dataloader, model_history, anomaly)

    for _ in range(config.num_rounds):
        server.run_round(clients)

    acc, _ = server.evaluate_and_log()

    assert acc > 0.05, (
        f'Smoke test FAILED: accuracy {acc:.4f} ≤ 0.05 (worse than random)'
    )
    print(f'Smoke test PASSED.  Accuracy after {config.num_rounds} rounds: {acc:.4f}')


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command-line arguments."""
    import argparse

    p = argparse.ArgumentParser(
        description='Async Robust Federated Learning (ARFL) framework',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    p.add_argument('--dataset',            default='MNIST',        choices=['MNIST', 'CIFAR10'])
    p.add_argument('--num_clients',        type=int,  default=10)
    p.add_argument('--num_rounds',         type=int,  default=50)
    p.add_argument('--aggregation',        default='trimmed_mean')
    p.add_argument('--byzantine_fraction', type=float, default=0.2)
    p.add_argument('--alpha',              type=float, default=0.5,  help='Dirichlet alpha')
    p.add_argument('--sabd_alpha',         type=float, default=0.5,  help='SABD correction strength')
    p.add_argument('--no_dp',              action='store_true',      help='Disable differential privacy')
    p.add_argument('--smoke_test',         action='store_true',      help='Run 3-client sanity check')
    p.add_argument('--check',              action='store_true',      help='Verify imports only')
    p.add_argument('--output_dir',         default='./results')
    p.add_argument('--in_channels',        type=int,  default=1,    help='1=MNIST, 3=CIFAR10')

    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse arguments and dispatch to the requested mode."""
    args = parse_args()

    # ── --check: import verification ─────────────────────────────────────
    if args.check:
        from async_federated_learning.aggregation.aggregator import list_available_methods
        print('All imports successful.')
        print('Available aggregation methods:', list_available_methods())
        return

    # ── --smoke_test: fast 3-client sanity check ──────────────────────────
    if args.smoke_test:
        run_smoke_test()
        return

    # ── Full experiment suite ─────────────────────────────────────────────
    config = Config(
        dataset_name=args.dataset,
        num_clients=args.num_clients,
        num_rounds=args.num_rounds,
        aggregation_method=args.aggregation,
        byzantine_fraction=args.byzantine_fraction,
        dirichlet_alpha=args.alpha,
        sabd_alpha=args.sabd_alpha,
        use_dp=not args.no_dp,
        output_dir=args.output_dir,
        in_channels=args.in_channels,
    )

    config.summary()
    run_all_experiments(config)


if __name__ == '__main__':
    main()
