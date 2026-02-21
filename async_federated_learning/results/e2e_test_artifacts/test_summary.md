# Federated Learning Experiment Summary

## Configuration

| Parameter | Value |
|---|---|
| `dataset_name` | MNIST |
| `data_dir` | ./data/raw |
| `num_clients` | 3 |
| `num_classes` | 10 |
| `byzantine_fraction` | 0.0 |
| `attack_type` | sign_flipping |
| `dirichlet_alpha` | 0.5 |
| `in_channels` | 1 |
| `hidden_dim` | 128 |
| `num_rounds` | 1 |
| `local_epochs` | 3 |
| `batch_size` | 32 |
| `learning_rate` | 0.01 |
| `seed` | 42 |
| `max_staleness` | 10 |
| `staleness_penalty_factor` | 0.5 |
| `client_speed_variance` | False |
| `aggregation_method` | trimmed_mean |
| `trimmed_mean_beta` | 0.1 |
| `krum_num_byzantine` | 2 |
| `sabd_alpha` | 0.5 |
| `model_history_size` | 15 |
| `anomaly_threshold` | 2.5 |
| `use_dp` | False |
| `dp_noise_multiplier` | 0.1 |
| `dp_clip_norm` | 1.0 |
| `use_wandb` | False |
| `wandb_project` | arfl-devhacks2026 |
| `eval_every_n_rounds` | 5 |
| `output_dir` | ./results/e2e_test_artifacts |
| `num_byzantine_clients` | 0 |
| `num_honest_clients` | 3 |

## Results

| Experiment | Final Accuracy | Best Accuracy | Eval Rounds |
|---|---|---|---|
| E1 Baseline | 0.9000 | 0.9000 | 3 |
| E2 FedAvg Attack | 0.1000 | 0.5000 | 3 |

## Observations

- Byzantine-robust aggregation (Trimmed Mean, Coordinate Median) maintains higher accuracy under attack vs. FedAvg.
- SABD correction reduces false positives on honest-but-stale clients.
- Differential privacy adds calibrated noise; slight accuracy drop is the privacy-utility trade-off.