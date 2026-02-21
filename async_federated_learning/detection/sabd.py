"""
detection/sabd.py
=================
Staleness-Aware Byzantine Detection (SABD) — custom algorithm.

Will contain:
- SABD class: scores each incoming client update by combining a staleness
  penalty (function of round gap τ) with a statistical distance measure
  (cosine similarity or L2 norm deviation from the current global model),
  then thresholds to flag Byzantine suspects.
- Mathematical derivation comments for the staleness discount factor:
      w(τ) = exp(−λ · τ)   (exponential staleness decay)
  and the composite anomaly score:
      score(i) = (1 − w(τ_i)) · dist(Δ_i, μ_Δ)
- filter_updates() method returning accepted and rejected update lists.
- Detailed logging of per-client scores and rejection decisions.
"""
