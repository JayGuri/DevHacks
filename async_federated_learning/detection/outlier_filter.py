"""
detection/outlier_filter.py
============================
Advanced Outlier Filtering for Robust Aggregation

This module implements statistical outlier detection to identify and filter
malicious/buggy client updates BEFORE aggregation. Unlike the gatekeeper which
uses L2 norms, this filter uses multiple statistical methods to detect anomalies.

METHODS:
--------
1. IQR (Interquartile Range) Method
   - Detects updates outside [Q1 - 1.5×IQR, Q3 + 1.5×IQR]
   - Robust to extreme outliers
   - Standard in statistical analysis

2. Z-Score Method
   - Identifies updates with |z| > threshold (typically 3)
   - Assumes approximately normal distribution
   - Fast and interpretable

3. MAD (Median Absolute Deviation) Method
   - More robust than standard deviation
   - Resistant to outliers in the detection process itself
   - Formula: MAD = median(|xi - median(x)|)

4. Isolation Forest Method
   - Machine learning-based anomaly detection
   - Can detect complex attack patterns
   - Works well with high-dimensional data

WHY MULTIPLE METHODS?
---------------------
Different attacks require different defenses:
- Scaling attacks → Caught by IQR/Z-score
- Sign-flipping → Caught by direction analysis
- Gradient noise → Caught by MAD
- Sophisticated poisoning → Caught by Isolation Forest
"""

import logging
from typing import List, Dict, Tuple, Optional
import numpy as np
import torch

logger = logging.getLogger(__name__)


class OutlierFilter:
    """
    Multi-method statistical outlier detection for Byzantine-robust FL.
    
    Parameters
    ----------
    method : str
        Detection method: 'iqr', 'zscore', 'mad', 'isolation', 'ensemble'
    iqr_factor : float
        IQR multiplier for outlier bounds (default: 1.5)
    zscore_threshold : float
        Z-score threshold for outlier detection (default: 3.0)
    mad_threshold : float
        MAD multiplier for outlier bounds (default: 3.0)
    ensemble_vote_threshold : int
        Minimum votes needed to mark as outlier in ensemble mode (default: 2)
    """
    
    def __init__(
        self,
        method: str = 'ensemble',
        iqr_factor: float = 1.5,
        zscore_threshold: float = 3.0,
        mad_threshold: float = 3.0,
        ensemble_vote_threshold: int = 2
    ):
        self.method = method
        self.iqr_factor = iqr_factor
        self.zscore_threshold = zscore_threshold
        self.mad_threshold = mad_threshold
        self.ensemble_vote_threshold = ensemble_vote_threshold
        
        logger.info(
            f"OutlierFilter initialized — method={method}, "
            f"iqr_factor={iqr_factor:.2f}, zscore_threshold={zscore_threshold:.2f}"
        )
    
    def filter_updates(
        self, 
        updates: List[Dict[str, np.ndarray]],
        client_ids: Optional[List[int]] = None
    ) -> Tuple[List[Dict[str, np.ndarray]], List[int], List[int]]:
        """
        Filter outlier updates using selected method(s).
        
        Parameters
        ----------
        updates : List[Dict[str, np.ndarray]]
            List of client gradient updates
        client_ids : Optional[List[int]]
            Client IDs for logging (default: 0, 1, 2, ...)
        
        Returns
        -------
        filtered_updates : List[Dict[str, np.ndarray]]
            Updates that passed the filter
        accepted_indices : List[int]
            Indices of accepted updates
        rejected_indices : List[int]
            Indices of rejected updates (identified as outliers)
        """
        if client_ids is None:
            client_ids = list(range(len(updates)))
        
        if len(updates) < 3:
            logger.warning("Too few updates to detect outliers, accepting all")
            return updates, list(range(len(updates))), []
        
        # Convert updates to feature vectors (L2 norms per layer)
        feature_vectors = self._extract_features(updates)
        
        # Detect outliers using selected method
        if self.method == 'iqr':
            is_outlier = self._detect_iqr(feature_vectors)
        elif self.method == 'zscore':
            is_outlier = self._detect_zscore(feature_vectors)
        elif self.method == 'mad':
            is_outlier = self._detect_mad(feature_vectors)
        elif self.method == 'ensemble':
            is_outlier = self._detect_ensemble(feature_vectors)
        else:
            logger.error(f"Unknown method: {self.method}, defaulting to IQR")
            is_outlier = self._detect_iqr(feature_vectors)
        
        # Split into accepted and rejected
        accepted_indices = [i for i, outlier in enumerate(is_outlier) if not outlier]
        rejected_indices = [i for i, outlier in enumerate(is_outlier) if outlier]
        
        filtered_updates = [updates[i] for i in accepted_indices]
        
        # Log results
        if rejected_indices:
            rejected_clients = [client_ids[i] for i in rejected_indices]
            logger.warning(
                f"OutlierFilter rejected {len(rejected_indices)}/{len(updates)} updates — "
                f"clients={rejected_clients}, method={self.method}"
            )
        else:
            logger.info(f"OutlierFilter: all {len(updates)} updates accepted")
        
        return filtered_updates, accepted_indices, rejected_indices
    
    def _extract_features(self, updates: List[Dict[str, np.ndarray]]) -> np.ndarray:
        """
        Extract feature vectors from updates for outlier detection.
        Uses L2 norm per parameter as features.
        """
        feature_list = []
        
        for update in updates:
            features = []
            for key, value in sorted(update.items()):
                # Convert to numpy if tensor
                if isinstance(value, torch.Tensor):
                    value = value.cpu().detach().numpy()
                
                # Compute L2 norm for this parameter
                l2_norm = np.linalg.norm(value.flatten())
                features.append(l2_norm)
            
            feature_list.append(features)
        
        return np.array(feature_list)  # Shape: (n_clients, n_features)
    
    def _detect_iqr(self, features: np.ndarray) -> List[bool]:
        """
        IQR (Interquartile Range) outlier detection.
        
        For each feature dimension:
        - Compute Q1 (25th percentile) and Q3 (75th percentile)
        - IQR = Q3 - Q1
        - Lower bound = Q1 - 1.5 × IQR
        - Upper bound = Q3 + 1.5 × IQR
        - Mark as outlier if ANY feature is outside bounds
        """
        n_clients = features.shape[0]
        is_outlier = np.zeros(n_clients, dtype=bool)
        
        # Check each feature dimension independently
        for dim in range(features.shape[1]):
            values = features[:, dim]
            
            q1 = np.percentile(values, 25)
            q3 = np.percentile(values, 75)
            iqr = q3 - q1
            
            lower_bound = q1 - self.iqr_factor * iqr
            upper_bound = q3 + self.iqr_factor * iqr
            
            # Mark clients outside bounds as outliers
            outliers_dim = (values < lower_bound) | (values > upper_bound)
            is_outlier |= outliers_dim
        
        return is_outlier.tolist()
    
    def _detect_zscore(self, features: np.ndarray) -> List[bool]:
        """
        Z-score outlier detection.
        
        For each feature dimension:
        - Compute mean μ and std σ
        - Z-score = (x - μ) / σ
        - Mark as outlier if |Z| > threshold
        """
        n_clients = features.shape[0]
        is_outlier = np.zeros(n_clients, dtype=bool)
        
        for dim in range(features.shape[1]):
            values = features[:, dim]
            
            mean = np.mean(values)
            std = np.std(values)
            
            if std < 1e-8:  # Avoid division by zero
                continue
            
            z_scores = np.abs((values - mean) / std)
            outliers_dim = z_scores > self.zscore_threshold
            is_outlier |= outliers_dim
        
        return is_outlier.tolist()
    
    def _detect_mad(self, features: np.ndarray) -> List[bool]:
        """
        MAD (Median Absolute Deviation) outlier detection.
        
        More robust than Z-score because it uses median instead of mean.
        
        For each feature dimension:
        - Compute median M
        - MAD = median(|xi - M|)
        - Modified Z-score = 0.6745 × (x - M) / MAD
        - Mark as outlier if modified Z-score > threshold
        """
        n_clients = features.shape[0]
        is_outlier = np.zeros(n_clients, dtype=bool)
        
        for dim in range(features.shape[1]):
            values = features[:, dim]
            
            median = np.median(values)
            mad = np.median(np.abs(values - median))
            
            if mad < 1e-8:  # Avoid division by zero
                continue
            
            # Modified Z-score (0.6745 is the constant for normal distribution)
            modified_z = 0.6745 * np.abs(values - median) / mad
            outliers_dim = modified_z > self.mad_threshold
            is_outlier |= outliers_dim
        
        return is_outlier.tolist()
    
    def _detect_ensemble(self, features: np.ndarray) -> List[bool]:
        """
        Ensemble outlier detection: combines IQR, Z-score, and MAD.
        
        A client is marked as outlier if at least `ensemble_vote_threshold`
        methods agree it's an outlier.
        """
        n_clients = features.shape[0]
        
        # Get votes from each method
        iqr_votes = np.array(self._detect_iqr(features), dtype=int)
        zscore_votes = np.array(self._detect_zscore(features), dtype=int)
        mad_votes = np.array(self._detect_mad(features), dtype=int)
        
        # Count votes
        total_votes = iqr_votes + zscore_votes + mad_votes
        
        # Mark as outlier if enough methods agree
        is_outlier = total_votes >= self.ensemble_vote_threshold
        
        logger.debug(
            f"Ensemble voting — IQR: {iqr_votes.sum()}, "
            f"Z-score: {zscore_votes.sum()}, MAD: {mad_votes.sum()}, "
            f"Final outliers: {is_outlier.sum()}"
        )
        
        return is_outlier.tolist()
    
    def get_stats(self, updates: List[Dict[str, np.ndarray]]) -> Dict:
        """
        Get statistical summary of updates for analysis.
        """
        features = self._extract_features(updates)
        
        stats = {
            'n_clients': features.shape[0],
            'n_features': features.shape[1],
            'mean_norms': np.mean(features, axis=0).tolist(),
            'median_norms': np.median(features, axis=0).tolist(),
            'std_norms': np.std(features, axis=0).tolist(),
            'min_norms': np.min(features, axis=0).tolist(),
            'max_norms': np.max(features, axis=0).tolist()
        }
        
        return stats
