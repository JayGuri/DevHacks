"""
client/fl_client.py
===================
Federated learning client responsible for local training and update submission.

Will contain:
- FLClient class: receives the global model, runs E local SGD epochs on its
  private shard, applies optional DP-SGD noise (via privacy/dp.py), and pushes
  a model-delta (or full state_dict) update back to the server queue.
- Byzantine behaviour injection hook (delegates to attacks/byzantine.py).
- Per-client logging of local loss curves and gradient norms.
- Simulated network delay to model asynchronous arrival patterns.
"""
