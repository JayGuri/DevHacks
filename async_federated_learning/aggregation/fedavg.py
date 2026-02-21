"""
aggregation/fedavg.py
=====================
Federated Averaging (FedAvg) aggregation strategy.

Will contain:
- FedAvg class: computes the weighted average of client model updates,
  where weights are proportional to each client's local dataset size.
  Formula:  w_global = Σ_i (n_i / N) · w_i
  where n_i = client i's sample count, N = total samples across accepted clients.
- aggregate(updates: List[ClientUpdate]) → state_dict method.
- No external FL library used; pure PyTorch tensor arithmetic.
"""
