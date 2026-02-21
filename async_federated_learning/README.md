# Async Federated Learning (ARFL)

A privacy-preserving, Byzantine-robust asynchronous federated learning framework built entirely from scratch — no FL libraries used.

## Overview

This framework implements the **Asynchronous Robust Federated Learning (ARFL)** pipeline described in the blueprint, featuring:

- **Asynchronous aggregation** — clients update at their own pace; the server aggregates on arrival.
- **Staleness-Aware Byzantine Detection (SABD)** — custom algorithm that discounts stale updates and flags Byzantine clients.
- **Multiple aggregation strategies** — FedAvg, Trimmed Mean, Coordinate Median, Reputation-weighted.
- **Differential Privacy** — custom DP-SGD with per-sample gradient clipping and calibrated Gaussian noise.
- **Byzantine attack simulation** — label-flip, Gaussian noise, sign-flip, scaling attacks.
- **Non-IID data partitioning** — Dirichlet-based heterogeneous data distribution.

## Structure

```
async_federated_learning/
├── config.py            # Central hyperparameter configuration
├── main.py              # Entry point
├── data/                # Dataset loading and non-IID partitioning
├── models/              # CNN model definition
├── server/              # Async FL server and model history
├── client/              # FL client (local training + DP)
├── detection/           # SABD and anomaly detection
├── aggregation/         # FedAvg, TrimmedMean, CoordMedian, Reputation
├── attacks/             # Byzantine attack implementations
├── privacy/             # Differential privacy (DP-SGD)
├── evaluation/          # Metrics: accuracy, ASR, privacy budget
├── experiments/         # Experiment runner and SABD proof
└── results/             # Output directory for logs and plots
```

## Quick Start

```bash
pip install -r requirements.txt
python main.py --config config.yaml
```

## Rules

- No FL libraries (Flower, PySyft, TFF, Opacus).
- All core logic custom-implemented.
- See `COMPONENT_ATTRIBUTION.md` for full provenance table.
