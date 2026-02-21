"""
attacks/byzantine.py
====================
Byzantine attack implementations for adversarial FL experiments.

Will contain:
- ByzantineAttacker class: wraps a client update and applies one of the
  following attack strategies (selected via AttackType enum):
    • LabelFlip    — corrupts training labels before local training.
    • GaussianNoise — adds large-variance Gaussian noise to the update delta.
    • SignFlip     — negates all gradient values (sign-flip / reverse gradient).
    • Scaling      — amplifies the update by a large scalar factor.
- apply(update) → poisoned_update method.
- Logging of attack type, magnitude, and affected client id.
"""
