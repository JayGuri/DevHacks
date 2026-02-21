"""
aggregation/coordinate_median.py
=================================
Coordinate-wise median aggregation for Byzantine robustness.

Will contain:
- CoordinateMedian class: for each scalar coordinate across all client updates,
  takes the median value — provably robust to up to ⌊(n−1)/2⌋ Byzantine clients.
  Formula:  CM(x_1,…,x_n)[j] = median({x_i[j] : i=1…n})  ∀ coordinate j.
- aggregate(updates) → state_dict method.
- Efficient vectorised implementation using torch.median.
"""
