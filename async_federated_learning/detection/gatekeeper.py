"""
detection/gatekeeper.py
=======================
L2 Norm-based Gatekeeper (Filter Funnel) for Byzantine detection.

WHAT IS THE GATEKEEPER?
-----------------------
The gatekeeper inspects incoming gradient updates BEFORE aggregation.
It measures the L2 norm (magnitude) of each update and flags suspiciously
large or small updates that could be poisoning attacks.

WHY DO WE NEED IT?
------------------
WITHOUT Gatekeeper:
    - Byzantine clients can send arbitrarily large gradients (scaling attack)
    - These corrupt the aggregation even with robust methods
    - Example: gradient × 1000 → dominates the median/trimmed mean

WITH Gatekeeper:
    - Large-magnitude updates are caught at the gate
    - Only "reasonable" updates proceed to aggregation
    - Reduces attack surface before SABD/aggregation layers

EXAMPLE SCENARIO
----------------
Client Updates (L2 norms):
  Client 0: ‖Δ₀‖ = 2.3   (honest)
  Client 1: ‖Δ₁‖ = 2.8   (honest, slightly stale)
  Client 2: ‖Δ₂‖ = 150.0 (BYZANTINE - scaling attack!)
  Client 3: ‖Δ₃‖ = 2.1   (honest)

WITHOUT Gatekeeper:
  → All 4 updates go to aggregation
  → Even trimmed_mean gets corrupted by the outlier
  → Attack success!

WITH Gatekeeper:
  → L2 norm check: 2.3, 2.8, 150.0, 2.1
  → Mean = 39.3, Std = 64.7, Threshold = 39.3 + 3×64.7 = 233.4
  → Client 2 (150.0) exceeds reasonable bounds → REJECTED at gate
  → Only [2.3, 2.8, 2.1] proceed to aggregation
  → Attack blocked!
"""

import logging
from typing import List, Dict, Tuple

import numpy as np
import torch

logger = logging.getLogger(__name__)


class Gatekeeper:
    """
    L2 Norm-based Filter Funnel for pre-aggregation Byzantine detection.
    
    Inspects statistical properties of gradient updates before they reach
    the aggregation layer. Complements SABD by catching gross anomalies early.
    
    Parameters
    ----------
    l2_threshold_factor : float
        Multiplier for std deviation in L2 norm filtering (default 3.0)
        Higher = more permissive (fewer false positives)
        Lower = stricter (more false positives but better attack defense)
    
    min_l2_threshold : float
        Minimum absolute L2 norm threshold (default 0.01)
        Prevents rejecting very small but legitimate updates
    
    max_l2_threshold : float
        Maximum absolute L2 norm threshold (default 1000.0)
        Hard cap on gradient magnitude
    """
    
    def __init__(
        self,
        l2_threshold_factor: float = 3.0,
        min_l2_threshold: float = 0.01,
        max_l2_threshold: float = 1000.0,
    ):
        self.l2_threshold_factor = l2_threshold_factor
        self.min_l2_threshold = min_l2_threshold
        self.max_l2_threshold = max_l2_threshold
        
        # Statistics tracking
        self.l2_norms_history = []
        self.rejection_count = 0
        self.total_count = 0
        
        logger.info(
            f"Gatekeeper initialized: l2_factor={l2_threshold_factor}, "
            f"min_threshold={min_l2_threshold}, max_threshold={max_l2_threshold}"
        )
    
    def compute_l2_norm(self, update: Dict[str, torch.Tensor]) -> float:
        """
        Compute L2 norm (magnitude) of a model update.
        
        Formula: ‖Δ‖ = √(Σ_k ‖Δ[k]‖²)
        
        Parameters
        ----------
        update : dict[str, torch.Tensor]
            Model weight delta (gradient or full update)
            
        Returns
        -------
        float
            L2 norm of the entire update
        """
        total_norm_sq = 0.0
        
        for param_name, param_tensor in update.items():
            # Convert to tensor if numpy array
            if isinstance(param_tensor, np.ndarray):
                param_tensor = torch.from_numpy(param_tensor)
            
            # Compute squared norm of this parameter
            param_norm_sq = torch.sum(param_tensor ** 2).item()
            total_norm_sq += param_norm_sq
        
        l2_norm = np.sqrt(total_norm_sq)
        return l2_norm
    
    def inspect_updates(
        self,
        updates: List[Dict],
        current_round: int,
    ) -> Tuple[List[Dict], List[Dict], Dict]:
        """
        Filter updates based on L2 norm inspection (the "Filter Funnel").
        
        Algorithm
        ---------
        1. Compute L2 norm for each update: norms = [‖Δ₀‖, ‖Δ₁‖, ..., ‖Δₙ‖]
        2. Compute statistics: μ = mean(norms), σ = std(norms)
        3. Define bounds: [μ - k·σ, μ + k·σ] where k = l2_threshold_factor
        4. Reject updates outside bounds or exceeding absolute limits
        5. Return (accepted, rejected, statistics)
        
        Parameters
        ----------
        updates : list[dict]
            Client updates with 'client_id' and 'model_update' keys
        current_round : int
            Current FL round (for logging)
            
        Returns
        -------
        tuple
            (accepted_updates, rejected_updates, statistics_dict)
        """
        if not updates:
            return [], [], {}
        
        # Step 1: Compute L2 norms
        l2_norms = []
        client_ids = []
        
        for update in updates:
            client_id = update['client_id']
            model_update = update['model_update']
            
            l2_norm = self.compute_l2_norm(model_update)
            l2_norms.append(l2_norm)
            client_ids.append(client_id)
            
            logger.debug(f"Round {current_round}, Client {client_id}: L2 norm = {l2_norm:.4f}")
        
        # Step 2: Compute statistics
        l2_norms_array = np.array(l2_norms)
        mean_norm = np.mean(l2_norms_array)
        std_norm = np.std(l2_norms_array)
        
        # Step 3: Define adaptive bounds
        lower_bound = max(
            mean_norm - self.l2_threshold_factor * std_norm,
            self.min_l2_threshold,
        )
        upper_bound = min(
            mean_norm + self.l2_threshold_factor * std_norm,
            self.max_l2_threshold,
        )
        
        # Step 4: Filter updates
        accepted = []
        rejected = []
        
        for update, l2_norm, client_id in zip(updates, l2_norms, client_ids):
            self.total_count += 1
            
            # Check bounds
            if l2_norm < lower_bound:
                rejected.append(update)
                self.rejection_count += 1
                logger.warning(
                    f"GATEKEEPER REJECT (too small): Client {client_id}, "
                    f"L2={l2_norm:.4f} < lower_bound={lower_bound:.4f}"
                )
            elif l2_norm > upper_bound:
                rejected.append(update)
                self.rejection_count += 1
                logger.warning(
                    f"GATEKEEPER REJECT (too large): Client {client_id}, "
                    f"L2={l2_norm:.4f} > upper_bound={upper_bound:.4f}"
                )
            else:
                accepted.append(update)
        
        # Track history
        self.l2_norms_history.extend(l2_norms)
        
        # Statistics for logging
        stats = {
            'mean_l2': float(mean_norm),
            'std_l2': float(std_norm),
            'min_l2': float(np.min(l2_norms_array)),
            'max_l2': float(np.max(l2_norms_array)),
            'lower_bound': float(lower_bound),
            'upper_bound': float(upper_bound),
            'num_accepted': len(accepted),
            'num_rejected': len(rejected),
            'rejection_rate': self.rejection_count / self.total_count if self.total_count > 0 else 0.0,
        }
        
        logger.info(
            f"Gatekeeper Round {current_round}: "
            f"mean_L2={mean_norm:.4f}, std_L2={std_norm:.4f}, "
            f"bounds=[{lower_bound:.4f}, {upper_bound:.4f}], "
            f"accepted={len(accepted)}, rejected={len(rejected)}"
        )
        
        return accepted, rejected, stats
    
    def get_statistics(self) -> Dict:
        """
        Get gatekeeper statistics summary.
        
        Returns
        -------
        dict
            Summary statistics including rejection rates and L2 norm distributions
        """
        if not self.l2_norms_history:
            return {
                'total_inspected': 0,
                'total_rejected': 0,
                'rejection_rate': 0.0,
            }
        
        l2_array = np.array(self.l2_norms_history)
        
        return {
            'total_inspected': self.total_count,
            'total_rejected': self.rejection_count,
            'rejection_rate': self.rejection_count / self.total_count,
            'l2_mean': float(np.mean(l2_array)),
            'l2_std': float(np.std(l2_array)),
            'l2_min': float(np.min(l2_array)),
            'l2_max': float(np.max(l2_array)),
            'l2_median': float(np.median(l2_array)),
        }


# ---------------------------------------------------------------------------
# Comparison example (for documentation/testing)
# ---------------------------------------------------------------------------

def demonstrate_gatekeeper_effect():
    """
    Demonstration of WITH vs WITHOUT gatekeeper.
    
    This function shows the impact of the gatekeeper on attack mitigation.
    """
    print("\n" + "=" * 70)
    print("GATEKEEPER DEMONSTRATION: WITH vs WITHOUT")
    print("=" * 70)
    
    # Simulate client updates
    honest_updates = [
        {'client_id': 0, 'l2_norm': 2.3},
        {'client_id': 1, 'l2_norm': 2.8},
        {'client_id': 3, 'l2_norm': 2.1},
        {'client_id': 4, 'l2_norm': 2.5},
    ]
    
    byzantine_update = {'client_id': 2, 'l2_norm': 150.0}  # Scaling attack
    
    all_updates = honest_updates + [byzantine_update]
    
    # WITHOUT Gatekeeper
    print("\nSCENARIO 1: WITHOUT GATEKEEPER")
    print("-" * 70)
    print("All updates proceed to aggregation:")
    for u in all_updates:
        print(f"  Client {u['client_id']}: L2 norm = {u['l2_norm']:.1f}")
    print(f"\nMedian L2 norm: {np.median([u['l2_norm'] for u in all_updates]):.1f}")
    print("→ Byzantine outlier (150.0) corrupts even robust aggregation!")
    
    # WITH Gatekeeper
    print("\n\nSCENARIO 2: WITH GATEKEEPER")
    print("-" * 70)
    
    l2_norms = [u['l2_norm'] for u in all_updates]
    mean_l2 = np.mean(l2_norms)
    std_l2 = np.std(l2_norms)
    threshold_factor = 3.0
    upper_bound = mean_l2 + threshold_factor * std_l2
    
    print(f"L2 norms: {l2_norms}")
    print(f"Mean: {mean_l2:.1f}, Std: {std_l2:.1f}")
    print(f"Upper bound (mean + 3×std): {upper_bound:.1f}")
    
    accepted = [u for u in all_updates if u['l2_norm'] <= upper_bound]
    rejected = [u for u in all_updates if u['l2_norm'] > upper_bound]
    
    print(f"\nAccepted updates:")
    for u in accepted:
        print(f"  Client {u['client_id']}: L2 norm = {u['l2_norm']:.1f} ✓")
    
    print(f"\nRejected updates:")
    for u in rejected:
        print(f"  Client {u['client_id']}: L2 norm = {u['l2_norm']:.1f} ✗ (BLOCKED)")
    
    print(f"\n→ Byzantine attack blocked at the gate!")
    print(f"→ Clean aggregation with only honest updates: {[u['l2_norm'] for u in accepted]}")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    demonstrate_gatekeeper_effect()
