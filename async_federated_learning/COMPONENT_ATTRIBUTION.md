# Component Attribution

All core logic is custom-implemented from scratch (no FL libraries used).
External libraries are used only as numerical/ML backends.

| Component | File | Status | Notes |
|---|---|---|---|
| Central Configuration | `config.py` | Custom | FLConfig dataclass; all hyperparameters, enums for strategy/attack selection |
| Data Partitioner | `data/partitioner.py` | Custom | Non-IID Dirichlet partitioning of CIFAR-10 across clients |
| CNN Model | `models/cnn.py` | Custom | Lightweight convolutional network for CIFAR-10 classification |
| FL Server | `server/fl_server.py` | Custom | Async aggregation loop, staleness tracking, Byzantine filtering orchestration |
| Model History | `server/model_history.py` | Custom | Circular buffer of global model checkpoints for staleness computation |
| FL Client | `client/fl_client.py` | Custom | Local SGD training, gradient clipping, update serialisation |
| SABD Detection | `detection/sabd.py` | Custom | Staleness-Aware Byzantine Detection algorithm (custom derivation) |
| Anomaly Detection | `detection/anomaly.py` | Custom | Statistical anomaly scoring on client updates |
| FedAvg Aggregation | `aggregation/fedavg.py` | Custom | Weighted federated averaging (McMahan et al. style, no library) |
| Trimmed Mean | `aggregation/trimmed_mean.py` | Custom | Coordinate-wise α-trimmed mean for Byzantine robustness |
| Coordinate Median | `aggregation/coordinate_median.py` | Custom | Coordinate-wise geometric median aggregation |
| Reputation System | `aggregation/reputation.py` | Custom | Exponential-decay reputation scoring per client |
| Aggregator Router | `aggregation/aggregator.py` | Custom | Unified interface routing to FedAvg / TrimmedMean / CoordMedian |
| Byzantine Attacks | `attacks/byzantine.py` | Custom | Label-flip, Gaussian noise, sign-flip, and scaling attack implementations |
| Differential Privacy | `privacy/dp.py` | Custom | DP-SGD: per-sample gradient clipping + Gaussian noise calibration |
| Evaluation Metrics | `evaluation/metrics.py` | Custom | Accuracy, loss, ASR (attack success rate), privacy budget accounting |
| Experiment Runner | `experiments/run_experiments.py` | Custom | Grid-search driver over aggregation × attack × privacy configurations |
| SABD Convergence Proof | `experiments/sabd_proof.py` | Custom | Empirical validation / numerical verification of SABD theoretical bounds |
| PyTorch | — | External (backend) | Deep learning framework; tensor ops, autograd, optimisers |
| NumPy | — | External (backend) | Numerical computing; array math used inside custom algorithms |
| Matplotlib | — | External (backend) | Visualisation of training curves and experiment results |
| WandB | — | External (backend) | Experiment tracking and hyperparameter logging |
