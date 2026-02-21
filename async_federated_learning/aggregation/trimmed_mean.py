"""
aggregation/trimmed_mean.py
===========================
Coordinate-wise α-trimmed mean aggregation for Byzantine robustness.

Will contain:
- TrimmedMean class: for each model parameter coordinate, sorts the values
  contributed by all clients, removes the top-α and bottom-α fractions,
  and averages the remainder.
  Formula:  TM_α(x_1,…,x_n) = mean of x_{(⌈αn⌉+1) … x_{(n−⌈αn⌉)}}
- aggregate(updates, trim_fraction=0.1) → state_dict method.
- Supports configurable trim fraction (default 10% each side).
"""
