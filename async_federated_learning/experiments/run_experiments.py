"""
experiments/run_experiments.py
==============================
Grid-search experiment driver for systematic FL evaluation.

Will contain:
- run_single_experiment(config) → results_dict — executes one full FL run
  and returns accuracy, ASR, privacy ε, and convergence round.
- run_grid(grid_config) — iterates over all combinations of:
    aggregation strategy × attack type × Byzantine fraction × privacy ε,
  logging each run to WandB and saving CSVs to results/.
- Matplotlib plotting helpers for accuracy-vs-round and robustness bar charts.
- Reproducibility: seeds torch, numpy, random from config.seed.
"""
