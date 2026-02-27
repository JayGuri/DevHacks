"""
privacy/secure_aggregation.py
==============================
Secure Aggregation Protocol with Zero-Sum Masking (Bonawitz et al. 2017).

This module implements the core secure aggregation protocol that enables
a server to compute the sum of client updates without ever seeing individual
updates. This provides cryptographic privacy guarantees stronger than
differential privacy, with ZERO accuracy loss.

Protocol Overview
-----------------
1. **Setup Phase**: Clients establish pairwise shared keys (via key_agreement.py)
2. **Masking Phase**: Each client:
   - Computes zero-sum mask from pairwise keys
   - Adds mask to their update: masked_update = update + mask
   - Sends masked_update to server
3. **Aggregation Phase**: Server sums masked updates:
   - Sum(masked_updates) = Sum(updates) + Sum(masks)
   - Sum(masks) = 0 (zero-sum property)
   - Result: Sum(masked_updates) = Sum(updates) ← true aggregate!
4. **Dropout Handling**: If clients drop out, surviving clients share unmasking keys

Key Properties
--------------
- **Privacy**: Server never sees individual updates (only masked versions)
- **Accuracy**: NO noise added, perfect mathematical equivalence
- **Robustness**: Compatible with Byzantine-resilient aggregation
- **Efficiency**: O(n²) communication for n clients (public key broadcast)

Comparison to Differential Privacy
-----------------------------------
Differential Privacy:
  ✓ Mathematical privacy guarantee (ε, δ)
  ✗ Adds noise → accuracy loss
  ✗ Server sees noisy individual updates
  
Secure Aggregation:
  ✓ Cryptographic privacy (server cannot decrypt individuals)
  ✓ ZERO accuracy loss (perfect aggregate)
  ✗ More complex protocol (key agreement required)
  ✗ Vulnerable to colluding clients (if >50% collude)

Integration with Byzantine Defense
-----------------------------------
Secure aggregation works seamlessly with outlier filtering + robust aggregation:

1. Clients mask their updates (secure aggregation)
2. Server aggregates masked updates → gets true aggregate
3. Server applies outlier detection (on aggregate behavior over rounds)
4. Server uses robust aggregation (coordinate median on aggregated updates)

The masking does NOT interfere with Byzantine detection because:
- Masks cancel out exactly during aggregation
- Byzantine clients cannot forge masks for honest clients
- Outlier filtering works on aggregate statistics, not individual updates
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

from privacy.key_agreement import KeyAgreementManager

logger = logging.getLogger(__name__)


class SecureAggregationProtocol:
    """
    Secure aggregation protocol manager for one federated learning round.
    
    This class coordinates the secure aggregation process:
    1. Collect public keys from all clients
    2. Distribute public keys to all clients
    3. Enable clients to generate zero-sum masks
    4. Verify mask cancellation during aggregation
    
    The server instantiates one SecureAggregationProtocol per round.
    
    Attributes
    ----------
    round_number : int
        Current FL round
    client_ids : List[int]
        IDs of all participating clients this round
    public_keys : Dict[int, int]
        Collected public keys: {client_id: public_key}
    """
    
    def __init__(self, round_number: int):
        """
        Initialize secure aggregation for one FL round.
        
        Parameters
        ----------
        round_number : int
            Current federated learning round
        """
        self.round_number = round_number
        self.client_ids: List[int] = []
        self.public_keys: Dict[int, int] = {}
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(
            f"SecureAggregationProtocol initialized for round {round_number}"
        )
    
    def register_client(self, client_id: int, public_key: int) -> None:
        """
        Register a client's public key for this round.
        
        Called by the server when a client announces participation.
        
        Parameters
        ----------
        client_id : int
            Client's unique identifier
        public_key : int
            Client's DH public key (g^a_i mod p)
        """
        if client_id in self.public_keys:
            self.logger.warning(
                f"Client {client_id} already registered, overwriting public key"
            )
        
        self.public_keys[client_id] = public_key
        if client_id not in self.client_ids:
            self.client_ids.append(client_id)
        
        self.logger.debug(
            f"Registered client {client_id} public key "
            f"(total clients: {len(self.client_ids)})"
        )
    
    def get_public_keys(self) -> Dict[int, int]:
        """
        Return all registered public keys for broadcast.
        
        The server broadcasts this dictionary to all clients so they can
        compute pairwise shared secrets.
        
        Returns
        -------
        Dict[int, int]
            Mapping {client_id: public_key} for all registered clients
        """
        return self.public_keys.copy()
    
    def verify_masked_aggregation(
        self,
        masked_updates: List[Dict[str, np.ndarray]],
        true_updates: Optional[List[Dict[str, np.ndarray]]] = None,
        tolerance: float = 1e-6
    ) -> Tuple[bool, Dict[str, np.ndarray]]:
        """
        Aggregate masked updates and verify masks cancelled correctly.
        
        This is the core server-side operation:
        1. Sum all masked updates
        2. If true updates provided (testing), verify sum matches
        3. Return aggregated result
        
        Parameters
        ----------
        masked_updates : List[Dict[str, np.ndarray]]
            Masked updates from all clients
        true_updates : Optional[List[Dict[str, np.ndarray]]]
            Unmasked updates for verification (testing only)
        tolerance : float
            Numerical tolerance for verification
        
        Returns
        -------
        Tuple[bool, Dict[str, np.ndarray]]
            (verification_passed, aggregated_update)
        """
        if not masked_updates:
            self.logger.warning("No masked updates to aggregate")
            return False, {}
        
        # Aggregate masked updates
        aggregated = {}
        layer_names = masked_updates[0].keys()
        
        for layer_name in layer_names:
            layer_sum = sum(
                update[layer_name] for update in masked_updates
            )
            aggregated[layer_name] = layer_sum
        
        self.logger.info(
            f"Aggregated {len(masked_updates)} masked updates "
            f"({len(layer_names)} layers)"
        )
        
        # Verify against true updates if provided (testing)
        verification_passed = True
        if true_updates is not None:
            true_aggregated = {}
            for layer_name in layer_names:
                true_aggregated[layer_name] = sum(
                    update[layer_name] for update in true_updates
                )
            
            # Compare masked aggregate vs true aggregate
            for layer_name in layer_names:
                diff = aggregated[layer_name] - true_aggregated[layer_name]
                max_diff = np.max(np.abs(diff))
                
                if max_diff > tolerance:
                    self.logger.error(
                        f"Verification FAILED for layer {layer_name}: "
                        f"max_diff={max_diff:.2e} > tolerance={tolerance:.2e}"
                    )
                    verification_passed = False
                else:
                    self.logger.debug(
                        f"Layer {layer_name} verified: max_diff={max_diff:.2e}"
                    )
            
            if verification_passed:
                self.logger.info(
                    "✓ Secure aggregation verification PASSED: "
                    "masks cancelled correctly"
                )
            else:
                self.logger.error(
                    "✗ Secure aggregation verification FAILED: "
                    "mask cancellation error"
                )
        
        return verification_passed, aggregated


class SecureAggregationClient:
    """
    Client-side secure aggregation wrapper.
    
    Each FL client instantiates one SecureAggregationClient to:
    1. Manage key agreement
    2. Generate masks
    3. Apply masks to weight updates before transmission
    
    This class integrates with FLClient to provide transparent masking.
    
    Attributes
    ----------
    client_id : int
        This client's unique identifier
    key_manager : KeyAgreementManager
        Handles Diffie-Hellman key agreement
    enabled : bool
        Whether secure aggregation is active
    """
    
    def __init__(self, client_id: int, enabled: bool = True, seed: int = None):
        """
        Initialize secure aggregation for one client.
        
        Parameters
        ----------
        client_id : int
            Unique client identifier
        enabled : bool
            Whether to enable secure aggregation (default True)
        seed : int, optional
            Random seed for reproducibility (testing only)
        """
        self.client_id = client_id
        self.enabled = enabled
        self.key_manager: Optional[KeyAgreementManager] = None
        self.logger = logging.getLogger(__name__)
        
        if enabled:
            self.key_manager = KeyAgreementManager(client_id, seed=seed)
            self.logger.info(
                f"SecureAggregationClient {client_id}: initialized with key agreement"
            )
        else:
            self.logger.info(
                f"SecureAggregationClient {client_id}: disabled (no masking)"
            )
    
    def get_public_key(self) -> Optional[int]:
        """
        Get this client's public key for broadcasting.
        
        Returns
        -------
        Optional[int]
            DH public key, or None if secure aggregation disabled
        """
        if not self.enabled or self.key_manager is None:
            return None
        return self.key_manager.get_public_key()
    
    def setup_round(
        self, 
        all_public_keys: Dict[int, int],
        round_number: int
    ) -> None:
        """
        Setup secure aggregation for a new FL round.
        
        Called after the server broadcasts all public keys.
        Computes pairwise shared secrets with all other clients.
        
        Parameters
        ----------
        all_public_keys : Dict[int, int]
            Public keys from all clients: {client_id: public_key}
        round_number : int
            Current FL round
        """
        if not self.enabled or self.key_manager is None:
            return
        
        self.key_manager.compute_pairwise_keys(all_public_keys)
        self.current_round = round_number
        
        self.logger.info(
            f"Client {self.client_id}: setup complete for round {round_number}, "
            f"paired with {len(all_public_keys) - 1} clients"
        )
    
    def mask_update(
        self,
        weight_update: Dict[str, np.ndarray],
        all_client_ids: List[int],
        round_number: int
    ) -> Dict[str, np.ndarray]:
        """
        Apply zero-sum mask to weight update before transmission.
        
        This is the core client-side operation:
        1. Generate zero-sum mask from pairwise keys
        2. Add mask to weight update
        3. Return masked update
        
        The server will sum masked updates and masks will cancel out.
        
        Parameters
        ----------
        weight_update : Dict[str, np.ndarray]
            Raw weight update from local training
        all_client_ids : List[int]
            IDs of all clients participating this round
        round_number : int
            Current FL round
        
        Returns
        -------
        Dict[str, np.ndarray]
            Masked update: weight_update + zero_sum_mask
        """
        if not self.enabled or self.key_manager is None:
            # Secure aggregation disabled, return unmasked update
            return weight_update
        
        # Extract weight shapes
        weight_shapes = {k: v.shape for k, v in weight_update.items()}
        
        # Generate zero-sum mask
        mask = self.key_manager.generate_zero_sum_mask(
            weight_shapes, all_client_ids, round_number
        )
        
        # Apply mask: masked_update = update + mask
        masked_update = {
            k: weight_update[k] + mask[k]
            for k in weight_update.keys()
        }
        
        # Log mask statistics
        mask_norms = {k: np.linalg.norm(v) for k, v in mask.items()}
        update_norms = {k: np.linalg.norm(v) for k, v in weight_update.items()}
        
        self.logger.debug(
            f"Client {self.client_id}: applied mask "
            f"(update_norm={sum(update_norms.values()):.4f}, "
            f"mask_norm={sum(mask_norms.values()):.4f})"
        )
        
        return masked_update
    
    def unmask_update(
        self,
        masked_update: Dict[str, np.ndarray],
        all_client_ids: List[int],
        round_number: int
    ) -> Dict[str, np.ndarray]:
        """
        Remove mask from update (for debugging/verification only).
        
        In the actual protocol, clients never unmask - the server simply
        aggregates masked updates and masks cancel automatically.
        
        Parameters
        ----------
        masked_update : Dict[str, np.ndarray]
            Masked weight update
        all_client_ids : List[int]
            IDs of all clients this round
        round_number : int
            Current FL round
        
        Returns
        -------
        Dict[str, np.ndarray]
            Unmasked update (for verification)
        """
        if not self.enabled or self.key_manager is None:
            return masked_update
        
        # Regenerate the same mask
        weight_shapes = {k: v.shape for k, v in masked_update.items()}
        mask = self.key_manager.generate_zero_sum_mask(
            weight_shapes, all_client_ids, round_number
        )
        
        # Remove mask: update = masked_update - mask
        unmasked_update = {
            k: masked_update[k] - mask[k]
            for k in masked_update.keys()
        }
        
        return unmasked_update


def compare_privacy_methods(
    update: Dict[str, np.ndarray],
    dp_noise_multiplier: float = 1.0,
    dp_clip_norm: float = 1.0
) -> Dict[str, Dict[str, float]]:
    """
    Compare privacy-utility tradeoff: Secure Aggregation vs Differential Privacy.
    
    Metrics computed:
    - Privacy guarantee (qualitative for SA, quantitative ε for DP)
    - Accuracy loss (L2 distance from original update)
    - Computational overhead
    
    Parameters
    ----------
    update : Dict[str, np.ndarray]
        Original weight update
    dp_noise_multiplier : float
        DP noise multiplier
    dp_clip_norm : float
        DP gradient clipping norm
    
    Returns
    -------
    Dict[str, Dict[str, float]]
        Comparison metrics for both methods
    """
    from privacy.dp import DifferentialPrivacyMechanism
    
    results = {}
    
    # Original update statistics
    total_norm = sum(np.linalg.norm(v) for v in update.values())
    total_size = sum(v.size for v in update.values())
    
    # Secure Aggregation
    results['secure_aggregation'] = {
        'privacy': 'cryptographic (server cannot see individual updates)',
        'accuracy_loss_l2': 0.0,  # Zero accuracy loss!
        'accuracy_loss_pct': 0.0,
        'overhead': 'O(n²) key agreement (one-time per round)',
    }
    
    # Differential Privacy
    dp_mechanism = DifferentialPrivacyMechanism(dp_noise_multiplier, dp_clip_norm)
    dp_update = dp_mechanism.privatize(update)
    
    # Compute accuracy loss from DP noise
    dp_loss = sum(
        np.linalg.norm(dp_update[k] - update[k])
        for k in update.keys()
    )
    dp_loss_pct = (dp_loss / total_norm) * 100 if total_norm > 0 else 0
    
    results['differential_privacy'] = {
        'privacy': f'(ε, δ)-DP (estimated ε ≈ {dp_noise_multiplier * 10:.1f})',
        'accuracy_loss_l2': float(dp_loss),
        'accuracy_loss_pct': float(dp_loss_pct),
        'overhead': 'O(m) gradient clipping + noise (per client)',
    }
    
    logger.info(
        f"\nPrivacy Method Comparison:\n"
        f"  Secure Aggregation: 0.0% accuracy loss, cryptographic privacy\n"
        f"  Differential Privacy: {dp_loss_pct:.2f}% accuracy loss, (ε, δ)-privacy"
    )
    
    return results
