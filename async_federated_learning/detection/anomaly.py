"""
detection/anomaly.py
====================
Statistical anomaly detection on client model updates.

Will contain:
- AnomalyDetector class: computes update-level anomaly scores using
  statistical methods (z-score on L2 norms, cosine deviation from mean
  update direction) independent of staleness weighting.
- Designed to be composed with SABD or used standalone.
- score_updates() method returning a dict of {client_id: anomaly_score}.
- Configurable sensitivity threshold and detection window size.
"""
