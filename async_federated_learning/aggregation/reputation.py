"""
aggregation/reputation.py
=========================
Client reputation scoring system for adaptive aggregation weighting.

Will contain:
- ReputationSystem class: maintains a running reputation score r_i for each
  client, updated after each round based on whether the client's update was
  accepted or flagged by SABD/AnomalyDetector.
  Update rule:  r_i ← β · r_i + (1−β) · feedback_i
  where β is the exponential decay factor and feedback_i ∈ {0, 1}.
- get_weights() method returning normalised reputation weights for aggregation.
- Penalty and reward functions with configurable magnitudes.
"""
