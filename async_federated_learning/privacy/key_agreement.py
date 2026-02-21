"""
privacy/key_agreement.py
========================
Pairwise key agreement for Secure Aggregation using Diffie-Hellman.

This module enables clients to establish shared secrets for zero-sum masking
without a trusted third party. Each pair of clients generates a shared key
that only they know, enabling them to create masks that cancel out during
aggregation.

Protocol Overview
-----------------
1. Each client generates a private/public key pair
2. Clients exchange public keys (via server broadcast)
3. Each pair (i, j) computes shared secret: K_ij = K_ji
4. Client i uses K_ij to generate mask for client j
5. Zero-sum property: sum of all pairwise masks = 0

Mathematical Foundation
-----------------------
Diffie-Hellman key exchange::

    Client i: private key a_i, public key A_i = g^(a_i) mod p
    Client j: private key a_j, public key A_j = g^(a_j) mod p
    
    Shared secret: K_ij = A_j^(a_i) mod p = A_i^(a_j) mod p = g^(a_i * a_j) mod p

Security Properties
-------------------
- Computational Diffie-Hellman assumption: hard to compute K_ij from A_i, A_j
- Server cannot compute pairwise keys (only sees public keys)
- Clients cannot forge keys for other pairs
"""

import hashlib
import logging
from typing import Dict, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# Diffie-Hellman parameters (1536-bit MODP group, RFC 3526)
# Using a standard group for efficiency and security
DH_PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA237327FFFFFFFFFFFFFFFF", 16
)
DH_GENERATOR = 2


class KeyAgreementManager:
    """
    Manages Diffie-Hellman key agreement for secure aggregation.
    
    Each client instantiates one KeyAgreementManager to:
    1. Generate their own DH key pair
    2. Receive public keys from other clients
    3. Compute pairwise shared secrets
    4. Derive pseudorandom masks from shared secrets
    
    Attributes
    ----------
    client_id : int
        This client's unique identifier
    private_key : int
        Secret DH exponent (a_i)
    public_key : int
        Public DH value (g^a_i mod p)
    pairwise_keys : Dict[int, bytes]
        Shared secrets with other clients: {client_j: K_ij}
    """
    
    def __init__(self, client_id: int, seed: int = None):
        """
        Initialize key agreement for one client.
        
        Parameters
        ----------
        client_id : int
            Unique identifier for this client
        seed : int, optional
            Random seed for reproducibility (testing only)
        """
        self.client_id = client_id
        self.pairwise_keys: Dict[int, bytes] = {}
        
        # Generate private key (random 256-bit exponent)
        if seed is not None:
            np.random.seed(seed + client_id)
        
        # Private key: random integer in [2, 2^256]
        # Use Python's random for large integers
        import random as py_random
        if seed is not None:
            py_random.seed(seed + client_id)
        
        self.private_key = py_random.randint(2, 2**256)
        
        # Public key: g^private_key mod p
        self.public_key = pow(DH_GENERATOR, self.private_key, DH_PRIME)
        
        logger.debug(
            f"KeyAgreement client {client_id}: generated DH key pair "
            f"(public_key={self.public_key % 10000}...)"
        )
    
    def get_public_key(self) -> int:
        """
        Return this client's public DH value for broadcasting.
        
        Returns
        -------
        int
            Public key g^a_i mod p
        """
        return self.public_key
    
    def compute_pairwise_keys(self, public_keys: Dict[int, int]) -> None:
        """
        Compute shared secrets with all other clients.
        
        For each client j ≠ i, computes:
            K_ij = (A_j)^(a_i) mod p = g^(a_i * a_j) mod p
        
        Then derives a 32-byte shared secret using SHA256.
        
        Parameters
        ----------
        public_keys : Dict[int, int]
            Mapping {client_id: public_key} for ALL clients (including self)
        """
        self.pairwise_keys.clear()
        
        for other_id, other_public_key in public_keys.items():
            if other_id == self.client_id:
                continue  # Skip self
            
            # Compute shared secret: other_public_key^private_key mod p
            shared_secret_int = pow(other_public_key, self.private_key, DH_PRIME)
            
            # Hash to get fixed-size key (32 bytes)
            # Include both client IDs to ensure deterministic but unique derivation
            hash_input = (
                str(shared_secret_int) + 
                f":{min(self.client_id, other_id)}:{max(self.client_id, other_id)}"
            ).encode('utf-8')
            
            shared_secret_bytes = hashlib.sha256(hash_input).digest()
            self.pairwise_keys[other_id] = shared_secret_bytes
            
            logger.debug(
                f"KeyAgreement client {self.client_id}: computed key with client {other_id} "
                f"(hash={shared_secret_bytes[:4].hex()}...)"
            )
        
        logger.info(
            f"Client {self.client_id}: established {len(self.pairwise_keys)} pairwise keys"
        )
    
    def generate_pairwise_mask(
        self, 
        other_client_id: int, 
        shape: Tuple[int, ...],
        round_number: int
    ) -> np.ndarray:
        """
        Generate a pseudorandom mask for pairing with another client.
        
        Uses the shared secret K_ij to seed a PRNG, ensuring both clients
        can reproduce the same mask. The mask direction (+ or -) is determined
        by client ID ordering to guarantee zero-sum property.
        
        Zero-sum property::
        
            For clients i, j where i < j:
            - Client i adds mask_ij = PRNG(K_ij, +1)
            - Client j adds mask_ji = PRNG(K_ij, -1)
            - Result: mask_ij + mask_ji = 0
        
        Parameters
        ----------
        other_client_id : int
            The paired client's ID
        shape : Tuple[int, ...]
            Shape of the mask (should match weight update shape)
        round_number : int
            Current FL round (used to vary masks per round)
        
        Returns
        -------
        np.ndarray
            Pseudorandom mask with zero sum across all pairs
        """
        if other_client_id not in self.pairwise_keys:
            raise ValueError(
                f"No pairwise key for client {other_client_id}. "
                "Call compute_pairwise_keys() first."
            )
        
        # Get shared secret
        shared_key = self.pairwise_keys[other_client_id]
        
        # Derive round-specific seed from shared key
        seed_input = shared_key + str(round_number).encode('utf-8')
        seed_hash = hashlib.sha256(seed_input).digest()
        seed = int.from_bytes(seed_hash[:8], byteorder='big') % (2**32)
        
        # Generate pseudorandom mask
        rng = np.random.RandomState(seed)
        mask = rng.standard_normal(shape)
        
        # Determine sign: lower ID adds positive, higher ID adds negative
        # This ensures masks cancel: mask_ij + mask_ji = mask_ij - mask_ij = 0
        if self.client_id < other_client_id:
            sign = +1.0
        else:
            sign = -1.0
        
        return sign * mask
    
    def generate_zero_sum_mask(
        self, 
        weight_shape_dict: Dict[str, Tuple[int, ...]],
        all_client_ids: list,
        round_number: int
    ) -> Dict[str, np.ndarray]:
        """
        Generate complete zero-sum mask by aggregating all pairwise masks.
        
        For each layer in the model, sum up masks from all pairwise keys.
        The total mask has the zero-sum property across ALL clients.
        
        Mathematical guarantee::
        
            Sum over all clients i of mask_i = Sum over all pairs (i,j) of (mask_ij + mask_ji)
                                              = Sum over all pairs (i,j) of 0
                                              = 0
        
        Parameters
        ----------
        weight_shape_dict : Dict[str, Tuple[int, ...]]
            Model parameter shapes: {layer_name: shape}
        all_client_ids : list
            List of ALL client IDs in this round
        round_number : int
            Current FL round
        
        Returns
        -------
        Dict[str, np.ndarray]
            Complete mask for this client: {layer_name: mask_array}
        """
        total_mask = {}
        
        for layer_name, shape in weight_shape_dict.items():
            layer_mask = np.zeros(shape, dtype=np.float64)
            
            # Sum pairwise masks with all other clients
            for other_id in all_client_ids:
                if other_id == self.client_id:
                    continue
                
                pairwise_mask = self.generate_pairwise_mask(
                    other_id, shape, round_number
                )
                layer_mask += pairwise_mask
            
            total_mask[layer_name] = layer_mask
        
        logger.debug(
            f"Client {self.client_id}: generated zero-sum mask for {len(total_mask)} layers "
            f"(paired with {len(all_client_ids) - 1} clients)"
        )
        
        return total_mask


def verify_zero_sum_property(
    client_masks: Dict[int, Dict[str, np.ndarray]],
    tolerance: float = 1e-10
) -> bool:
    """
    Verify that masks sum to zero across all clients (testing utility).
    
    Parameters
    ----------
    client_masks : Dict[int, Dict[str, np.ndarray]]
        Masks from all clients: {client_id: {layer: mask}}
    tolerance : float
        Numerical tolerance for zero check
    
    Returns
    -------
    bool
        True if sum of all masks ≈ 0 for all layers
    """
    if not client_masks:
        return True
    
    # Get layer names from first client
    first_client_id = next(iter(client_masks.keys()))
    layer_names = client_masks[first_client_id].keys()
    
    for layer_name in layer_names:
        # Sum masks across all clients
        total_mask = sum(
            client_masks[cid][layer_name] 
            for cid in client_masks.keys()
        )
        
        # Check if sum is close to zero
        max_abs = np.max(np.abs(total_mask))
        if max_abs > tolerance:
            logger.warning(
                f"Zero-sum verification FAILED for layer {layer_name}: "
                f"max_abs={max_abs:.2e} > tolerance={tolerance:.2e}"
            )
            return False
    
    logger.info(
        f"Zero-sum verification PASSED: {len(layer_names)} layers, "
        f"{len(client_masks)} clients"
    )
    return True
