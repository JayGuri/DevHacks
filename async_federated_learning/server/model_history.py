"""
server/model_history.py
=======================
Global model version history for staleness computation.

Will contain:
- ModelHistory class: circular buffer storing the last K snapshots of the
  global model's state_dict (keyed by round number), used by the server to
  compute how many rounds stale each arriving client update is.
- get_snapshot(round_id) and add_snapshot(round_id, state_dict) methods.
- Memory-bounded design (configurable max history length).
"""
