"""
privacy/dp.py
=============
Differential Privacy via DP-SGD — custom implementation (no Opacus).

Will contain:
- DPMechanism class: implements per-sample gradient clipping and calibrated
  Gaussian noise addition to guarantee (ε, δ)-differential privacy.
  Clipping:  g̃_i = g_i · min(1, C / ‖g_i‖_2)   (clip to L2 norm C)
  Noise:     g̃_noisy = (1/B) · (Σ g̃_i + N(0, σ²C²I))
  where σ is chosen via the moments accountant to satisfy (ε, δ)-DP.
- clip_and_noise(gradients, clip_norm, noise_multiplier) → noisy_gradients.
- Privacy budget tracking (epsilon accounting across rounds).
- Logging of per-step noise scale and cumulative ε expenditure.
"""
