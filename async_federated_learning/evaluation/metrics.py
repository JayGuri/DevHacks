"""
evaluation/metrics.py
=====================
Evaluation metrics for the federated learning pipeline.

Will contain:
- evaluate_model(model, dataloader, device) → (loss, accuracy) — standard
  cross-entropy loss and top-1 accuracy on a held-out test set.
- attack_success_rate(model, poisoned_loader, target_label) → float — fraction
  of poisoned inputs classified as the adversary's target class.
- PrivacyAccountant class: tracks cumulative (ε, δ) expenditure across T rounds
  using the moments accountant / Rényi DP composition.
- Logging and WandB metric push for all evaluation outputs.
"""
