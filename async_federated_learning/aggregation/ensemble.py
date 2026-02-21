"""
aggregation/ensemble.py
=======================
Ensemble Aggregation: Combines multiple robust methods for enhanced security.

This module implements an ensemble approach that combines Trimmed Mean and
Coordinate Median to provide stronger Byzantine resistance than either method alone.

WHY ENSEMBLE?
-------------
Different robust aggregation methods have different strengths:

Trimmed Mean:
  + Good at handling outliers in magnitude
  + Faster than median
  - Can be fooled by coordinated attacks
  - Breakdown point depends on β parameter

Coordinate Median:
  + Highest breakdown point (50%)
  + Resistant to coordinated attacks
  - Computationally more expensive
  - Can be slow with many clients

Ensemble Approach:
  + Combines strengths of both methods
  + More robust to diverse attack patterns
  + Self-correcting: if one method fails, the other compensates
  - Slightly higher computational cost

ALGORITHM:
----------
1. Apply Trimmed Mean to get result_tm
2. Apply Coordinate Median to get result_cm
3. Average the two results: result = (result_tm + result_cm) / 2

This gives us both the outlier-trimming benefit of Trimmed Mean and the
high breakdown point of Coordinate Median.

ALTERNATIVE STRATEGIES:
-----------------------
- Weighted ensemble: w1 × trimmed_mean + w2 × coord_median
- Adaptive ensemble: switch weights based on detected attack level
- Voting ensemble: use majority vote for each coordinate
"""

import logging
from typing import List, Dict, Optional

import numpy as np

from async_federated_learning.aggregation.trimmed_mean import trimmed_mean
from async_federated_learning.aggregation.coordinate_median import coordinate_median

logger = logging.getLogger(__name__)


def ensemble_aggregation(
    updates: List[Dict[str, np.ndarray]],
    beta: float = 0.1,
    weights: Optional[List[float]] = None,
    ensemble_weights: tuple = (0.5, 0.5)
) -> Dict[str, np.ndarray]:
    """
    Ensemble aggregation combining Trimmed Mean and Coordinate Median.
    
    Parameters
    ----------
    updates : List[Dict[str, np.ndarray]]
        List of client gradient updates
    beta : float
        Trimming parameter for trimmed_mean (default: 0.1)
    weights : Optional[List[float]]
        Client weights (currently unused, for interface compatibility)
    ensemble_weights : tuple
        Weights for (trimmed_mean, coord_median) combination (default: (0.5, 0.5))
    
    Returns
    -------
    Dict[str, np.ndarray]
        Aggregated update combining both methods
    
    Algorithm
    ---------
    1. Compute Trimmed Mean aggregation
    2. Compute Coordinate Median aggregation
    3. Take weighted average: w1 × TM + w2 × CM
    
    Example
    -------
    >>> updates = [client1_grads, client2_grads, client3_grads]
    >>> aggregated = ensemble_aggregation(updates, beta=0.2)
    """
    if len(updates) == 0:
        raise ValueError("Cannot aggregate empty update list")
    
    if len(updates) == 1:
        logger.warning("Only 1 update, returning as-is (ensemble not applicable)")
        return updates[0]
    
    # Validate ensemble weights
    w_tm, w_cm = ensemble_weights
    if abs(w_tm + w_cm - 1.0) > 1e-6:
        logger.warning(
            f"Ensemble weights sum to {w_tm + w_cm}, not 1.0. Normalizing."
        )
        total = w_tm + w_cm
        w_tm /= total
        w_cm /= total
    
    logger.info(
        f"Ensemble aggregation — n={len(updates)}, beta={beta:.2f}, "
        f"weights=({w_tm:.2f} TM, {w_cm:.2f} CM)"
    )
    
    # Step 1: Compute Trimmed Mean
    result_tm = trimmed_mean(updates, beta=beta, _weights=None)
    
    # Step 2: Compute Coordinate Median
    result_cm = coordinate_median(updates, _weights=None)
    
    # Step 3: Combine results with weighted average
    ensemble_result = {}
    
    for key in result_tm.keys():
        tm_value = result_tm[key]
        cm_value = result_cm[key]
        
        # Weighted combination
        ensemble_result[key] = w_tm * tm_value + w_cm * cm_value
    
    logger.debug(
        f"Ensemble complete — combined {len(result_tm)} parameters using "
        f"{w_tm:.0%} TM + {w_cm:.0%} CM"
    )
    
    return ensemble_result


def adaptive_ensemble_aggregation(
    updates: List[Dict[str, np.ndarray]],
    beta: float = 0.1,
    weights: Optional[List[float]] = None,
    attack_level: float = 0.0
) -> Dict[str, np.ndarray]:
    """
    Adaptive ensemble that adjusts weights based on detected attack level.
    
    Parameters
    ----------
    updates : List[Dict[str, np.ndarray]]
        List of client gradient updates
    beta : float
        Trimming parameter for trimmed_mean
    weights : Optional[List[float]]
        Client weights (unused)
    attack_level : float
        Estimated attack severity in [0, 1]
        0 = no attack detected → favor faster trimmed_mean
        1 = strong attack detected → favor more robust coord_median
    
    Returns
    -------
    Dict[str, np.ndarray]
        Adaptively aggregated update
    
    Strategy
    --------
    - Low attack (0-0.3): 70% TM, 30% CM (prioritize speed)
    - Medium attack (0.3-0.7): 50% TM, 50% CM (balanced)
    - High attack (0.7-1.0): 30% TM, 70% CM (prioritize robustness)
    """
    if attack_level < 0.3:
        # Low attack: favor speed
        w_tm, w_cm = 0.7, 0.3
        logger.info("Low attack level → 70% TM, 30% CM")
    elif attack_level < 0.7:
        # Medium attack: balanced
        w_tm, w_cm = 0.5, 0.5
        logger.info("Medium attack level → 50% TM, 50% CM")
    else:
        # High attack: favor robustness
        w_tm, w_cm = 0.3, 0.7
        logger.info("High attack level → 30% TM, 70% CM")
    
    return ensemble_aggregation(
        updates,
        beta=beta,
        weights=weights,
        ensemble_weights=(w_tm, w_cm)
    )


def voting_ensemble_aggregation(
    updates: List[Dict[str, np.ndarray]],
    beta: float = 0.1,
    weights: Optional[List[float]] = None
) -> Dict[str, np.ndarray]:
    """
    Voting ensemble: For each coordinate, use the method that produces
    a value closer to the overall median.
    
    This is more computationally expensive but provides maximum robustness
    by selecting the most trustworthy result per coordinate.
    
    Parameters
    ----------
    updates : List[Dict[str, np.ndarray]]
        List of client gradient updates
    beta : float
        Trimming parameter for trimmed_mean
    weights : Optional[List[float]]
        Client weights (unused)
    
    Returns
    -------
    Dict[str, np.ndarray]
        Voted aggregated update (most robust per coordinate)
    """
    if len(updates) < 3:
        logger.warning("Too few updates for voting, falling back to ensemble")
        return ensemble_aggregation(updates, beta=beta)
    
    logger.info(f"Voting ensemble — n={len(updates)}, beta={beta:.2f}")
    
    # Compute both methods
    result_tm = trimmed_mean(updates, beta=beta)
    result_cm = coordinate_median(updates)
    
    # For each parameter, vote based on distance to overall median
    voted_result = {}
    
    for key in result_tm.keys():
        tm_value = result_tm[key]
        cm_value = result_cm[key]
        
        # Compute overall median for this parameter
        param_values = np.array([u[key].flatten() for u in updates])
        overall_median = np.median(param_values, axis=0).reshape(tm_value.shape)
        
        # Choose the value closer to the overall median
        tm_distance = np.linalg.norm(tm_value - overall_median)
        cm_distance = np.linalg.norm(cm_value - overall_median)
        
        if tm_distance <= cm_distance:
            voted_result[key] = tm_value
        else:
            voted_result[key] = cm_value
    
    logger.debug(f"Voting complete for {len(voted_result)} parameters")
    
    return voted_result
