"""
experiments/sabd_proof.py
=========================
Empirical validation and numerical verification of SABD theoretical bounds.

Will contain:
- Numerical simulation of the SABD staleness discount convergence guarantee:
  verifies that the weighted aggregation error is bounded by O(τ_max · λ)
  under the stated assumptions.
- Plots of staleness penalty w(τ) = exp(−λτ) across λ values.
- Monte Carlo trials confirming SABD's Byzantine rejection rate at various
  Byzantine fractions (f = 0.1, 0.2, 0.3) vs. the theoretical threshold.
- All results saved as PNGs to results/sabd_proof/.
"""
