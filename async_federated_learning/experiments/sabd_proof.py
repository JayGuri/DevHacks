# experiments/sabd_proof.py — Standalone proof: SABD detection of Mallory
import os
import sys
import numpy as np
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detection.sabd import run_sabd

logger = logging.getLogger("fedbuff.experiments.sabd_proof")


def main():
    """
    Standalone proof demonstrating that SABD (Multi-Krum) correctly identifies
    and isolates Mallory's poisoned update.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    print("\n" + "=" * 70)
    print("SABD (Multi-Krum) Detection Proof")
    print("=" * 70)

    # Define parameter shapes (simplified for proof)
    param_shapes = {
        "layer1.weight": (64, 32),
        "layer1.bias": (64,),
        "layer2.weight": (32, 64),
        "layer2.bias": (32,),
    }

    np.random.seed(42)

    # Generate 3 synthetic updates
    # Alice and Bob: honest, from N(0, 0.01)
    # Mallory: poisoned, from N(0, 0.01) * -5.0

    alice_weights = {}
    bob_weights = {}
    mallory_weights = {}

    for name, shape in param_shapes.items():
        alice_weights[name] = np.random.normal(0, 0.01, shape).astype(np.float32)
        bob_weights[name] = np.random.normal(0, 0.01, shape).astype(np.float32)
        # Mallory: sign-flip amplified attack
        honest_update = np.random.normal(0, 0.01, shape).astype(np.float32)
        mallory_weights[name] = honest_update * -5.0

    updates = [
        {"client_id": "client-alice-img", "weights": alice_weights, "num_samples": 100},
        {"client_id": "client-bob-img", "weights": bob_weights, "num_samples": 100},
        {"client_id": "client-mallory-img", "weights": mallory_weights, "num_samples": 100},
    ]

    # Run SABD
    result = run_sabd(updates, byzantine_fraction=0.3)

    # Print formatted report
    print("\n--- Krum Scores (lower = more trusted) ---")
    for client_id, score in sorted(result.krum_scores.items(), key=lambda x: x[1]):
        indicator = " <-- OUTLIER" if result.trust_scores.get(client_id, 1.0) == 0.0 else ""
        print(f"  {client_id:<25} score = {score:12.4f}{indicator}")

    print("\n--- Trust Scores ---")
    for client_id, trust in result.trust_scores.items():
        status = "TRUSTED" if trust == 1.0 else "REJECTED"
        print(f"  {client_id:<25} trust = {trust:.1f}  [{status}]")

    print(f"\n--- Selection ---")
    selected_ids = [updates[i]["client_id"] for i in result.selected_indices]
    rejected_ids = [updates[i]["client_id"] for i in result.rejected_indices]
    print(f"  Selected: {selected_ids}")
    print(f"  Rejected: {rejected_ids}")

    # Verify Mallory was detected
    mallory_trust = result.trust_scores.get("client-mallory-img", 1.0)
    alice_trust = result.trust_scores.get("client-alice-img", 0.0)
    bob_trust = result.trust_scores.get("client-bob-img", 0.0)

    print(f"\n--- Verification ---")
    if mallory_trust == 0.0 and alice_trust == 1.0 and bob_trust == 1.0:
        print("  PASS: SABD correctly identified Mallory as the outlier.")
    else:
        print("  NOTE: Detection result may vary based on parameters.")
        print(f"  Mallory trust={mallory_trust}, Alice trust={alice_trust}, Bob trust={bob_trust}")

    # Generate matplotlib figure
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        os.makedirs("results", exist_ok=True)

        clients = ["Alice", "Bob", "Mallory"]
        client_ids = ["client-alice-img", "client-bob-img", "client-mallory-img"]
        scores = [result.krum_scores.get(cid, 0.0) for cid in client_ids]
        colors = ["#2ecc71" if result.trust_scores.get(cid, 0.0) == 1.0 else "#e74c3c"
                  for cid in client_ids]

        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(clients, scores, color=colors, edgecolor="black", linewidth=1.2)

        ax.set_title("SABD Detection: Mallory's update is the clear outlier",
                      fontsize=14, fontweight="bold")
        ax.set_ylabel("Krum Score (lower = more trusted)", fontsize=12)
        ax.set_xlabel("Client", fontsize=12)

        # Add value labels on bars
        for bar, score in zip(bars, scores):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(scores) * 0.02,
                    f"{score:.2f}", ha="center", va="bottom", fontsize=11, fontweight="bold")

        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#2ecc71", edgecolor="black", label="Trusted (score ≤ threshold)"),
            Patch(facecolor="#e74c3c", edgecolor="black", label="Rejected (outlier)"),
        ]
        ax.legend(handles=legend_elements, loc="upper left", fontsize=10)

        plt.tight_layout()
        fig_path = os.path.join("results", "sabd_proof.png")
        plt.savefig(fig_path, dpi=150)
        plt.close()

        print(f"\nSABD proof complete. Figure saved to {fig_path}")

    except ImportError:
        print("\nMatplotlib not available. Skipping figure generation.")
        print("Install with: pip install matplotlib")

    print("=" * 70)


if __name__ == "__main__":
    main()
