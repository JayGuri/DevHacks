"""
models/cnn.py
=============
Shared global model for the async federated learning pipeline.

Contains:
- FLModel(nn.Module): lightweight two-block CNN suitable for both MNIST and
  CIFAR-10.  Used as the single shared architecture that every client trains
  locally and the server aggregates.
- evaluate_model(): standalone function to compute accuracy and loss of any
  FLModel-compatible model on a DataLoader.
"""

import logging

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class FLModel(nn.Module):
    """
    Lightweight convolutional model shared across all FL clients and server.

    Role in pipeline
    ----------------
    The server holds the authoritative global copy of this model.  Each client
    receives a copy, trains it locally for ``local_epochs`` rounds, and sends
    back either a full state_dict or a weight delta.  The server aggregates
    those updates and writes the result back into its own FLModel instance.

    Architecture
    ------------
    conv_block1   : Conv2d(C_in, 32, 3, pad=1) → BN → ReLU → MaxPool2d(2)
    conv_block2   : Conv2d(32, 64, 3, pad=1)   → BN → ReLU → MaxPool2d(2)
    adaptive_pool : AdaptiveAvgPool2d((4, 4))   — makes input-size agnostic
    classifier    : Flatten → Linear(1024, H) → ReLU → Dropout(0.3)
                    → Linear(H, num_classes)

    AdaptiveAvgPool2d decouples the classifier head from spatial resolution so
    the same architecture works for 28×28 (MNIST) and 32×32 (CIFAR-10) inputs.

    Parameters
    ----------
    in_channels : int  — 1 for MNIST/greyscale, 3 for CIFAR-10/RGB.
    num_classes : int  — number of output logits (10 for both standard tasks).
    hidden_dim  : int  — width of the hidden FC layer (default 128).
    """

    def __init__(
        self,
        in_channels: int = 1,
        num_classes: int = 10,
        hidden_dim: int = 128,
    ) -> None:
        super().__init__()

        self.in_channels = in_channels
        self.num_classes = num_classes
        self.hidden_dim  = hidden_dim

        # ------------------------------------------------------------------
        # Block 1: 32 feature maps, spatial dim halved by MaxPool
        # ------------------------------------------------------------------
        self.conv_block1 = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2),
        )

        # ------------------------------------------------------------------
        # Block 2: 64 feature maps, spatial dim halved again
        # ------------------------------------------------------------------
        self.conv_block2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2),
        )

        # ------------------------------------------------------------------
        # Adaptive pooling → fixed 4×4 spatial output regardless of input size
        # ------------------------------------------------------------------
        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))

        # ------------------------------------------------------------------
        # Classifier head
        # 64 channels × 4 × 4 spatial = 1024-dim flattened feature vector
        # ------------------------------------------------------------------
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 4 * 4, hidden_dim),
            nn.ReLU(),
            nn.Dropout(p=0.3),
            nn.Linear(hidden_dim, num_classes),
        )

        logger.info(
            "FLModel initialised — in_channels=%d, num_classes=%d, "
            "hidden_dim=%d, params=%d",
            in_channels, num_classes, hidden_dim, self.count_parameters(),
        )

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Compute logits for a batch of images.

        Parameters
        ----------
        x : Tensor of shape (B, C, H, W)

        Returns
        -------
        logits : Tensor of shape (B, num_classes)  — raw (pre-softmax) scores.
        """
        x = self.conv_block1(x)     # (B, 32, H/2, W/2)
        x = self.conv_block2(x)     # (B, 64, H/4, W/4)
        x = self.adaptive_pool(x)   # (B, 64,   4,   4)
        x = self.classifier(x)      # (B, num_classes)
        return x

    # ------------------------------------------------------------------
    # Weight serialisation helpers
    # ------------------------------------------------------------------

    def get_weights(self) -> dict:
        """
        Return a copy of the model's parameters as plain numpy arrays.

        Each tensor is moved to CPU and detached from the autograd graph before
        conversion, so the returned dict is safe to send across thread boundaries
        or pickle for inter-process communication.

        Returns
        -------
        dict[str, np.ndarray]
            Keys match state_dict() parameter names.
        """
        return {
            # .copy() breaks the shared-memory link between the numpy array
            # and the underlying parameter tensor — without it, in-place
            # modifications to the tensor (e.g. p.add_()) would silently
            # mutate the "snapshot", making get_weight_delta() return zeros.
            name: tensor.cpu().detach().numpy().copy()
            for name, tensor in self.state_dict().items()
        }

    def set_weights(self, weights_dict: dict) -> None:
        """
        Load parameters from a dict of numpy arrays.

        Each array is converted back to a tensor that matches the original
        parameter's dtype and device, then loaded with strict=True to guard
        against shape / key mismatches.

        Parameters
        ----------
        weights_dict : dict[str, np.ndarray]
            Must contain exactly the same keys as state_dict().
        """
        current_state = self.state_dict()
        device = next(self.parameters()).device

        new_state = {
            name: torch.tensor(
                arr,
                dtype=current_state[name].dtype,
                device=device,
            )
            for name, arr in weights_dict.items()
        }
        self.load_state_dict(new_state, strict=True)
        logger.debug("set_weights — loaded %d parameter tensors.", len(new_state))

    def get_weight_delta(self, pre_train_weights: dict) -> dict:
        """
        Compute the element-wise difference between current and pre-training weights.

        Returns ``{name: current_array - pre_array}`` for every parameter key.

        Why deltas instead of full weights in async FL?
        -----------------------------------------------
        (1) **Communication efficiency**: Deltas are sparse when local updates
            are small — they compress better than absolute weight matrices.

        (2) **Staleness safety**: In async FL, the server's global model may
            have advanced several rounds while a slow client was training.
            Applying a delta (Δ = w_after − w_before) to the *current* global
            model is safer than overwriting it with the client's stale absolute
            weights, because the delta only encodes *what changed locally*.

        (3) **Marginal privacy**: The server observes the direction and
            magnitude of the local update rather than the absolute parameter
            state, providing a slight information-theoretic advantage that
            complements differential privacy mechanisms.

        Parameters
        ----------
        pre_train_weights : dict[str, np.ndarray]
            Snapshot from get_weights() captured *before* local training.

        Returns
        -------
        dict[str, np.ndarray]
            Same keys as state_dict(); values are signed float64 arrays.
        """
        current_weights = self.get_weights()
        delta = {
            name: current_weights[name] - pre_train_weights[name]
            for name in current_weights
        }
        total_norm = float(
            np.sqrt(sum(np.sum(d ** 2) for d in delta.values()))
        )
        logger.debug(
            "get_weight_delta — L2 norm of update: %.6f", total_norm
        )
        return delta

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def count_parameters(self) -> int:
        """
        Return the total number of trainable scalar parameters.

        Uses ``p.numel()`` on every parameter for which ``requires_grad=True``.

        Returns
        -------
        int
        """
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Standalone evaluation function
# ---------------------------------------------------------------------------

def evaluate_model(model: FLModel, dataloader, device) -> tuple:
    """
    Evaluate a model on a full DataLoader and return accuracy and average loss.

    Sets the model to ``eval`` mode (disabling BatchNorm running-stat updates
    and Dropout), computes metrics under ``torch.no_grad()``, then restores
    ``train`` mode before returning so the caller's training loop is unaffected.

    Loss function: ``nn.CrossEntropyLoss(reduction='mean')`` — computes the
    mean over all samples in each batch, then this function averages those
    batch means weighted by batch size to get the true sample-level mean.

    Parameters
    ----------
    model      : FLModel (or any nn.Module returning logits of shape (B, C))
    dataloader : DataLoader yielding (inputs, labels) batches
    device     : torch.device or str — e.g. ``torch.device('cpu')``

    Returns
    -------
    (accuracy, avg_loss) : (float, float)
        accuracy  — fraction of correctly classified samples in [0, 1].
        avg_loss  — sample-weighted mean cross-entropy loss.
    """
    model.eval()
    criterion = nn.CrossEntropyLoss(reduction="mean")

    total_correct = 0
    total_loss    = 0.0
    total_samples = 0

    with torch.no_grad():
        for inputs, labels in dataloader:
            inputs = inputs.to(device)
            labels = labels.to(device)

            logits = model(inputs)

            # Batch loss: mean over B samples in this batch
            batch_loss = criterion(logits, labels)

            # Accumulate sample-weighted loss so the final average is
            # over all samples, not over batches (handles unequal batch sizes)
            batch_size   = inputs.size(0)
            total_loss  += batch_loss.item() * batch_size
            total_samples += batch_size

            # Predicted class = argmax of logit vector
            preds = logits.argmax(dim=1)
            total_correct += (preds == labels).sum().item()

    accuracy = total_correct / total_samples      # TP / N   ∈ [0, 1]
    avg_loss = total_loss   / total_samples       # Σ(loss_i) / N

    logger.info(
        "evaluate_model — samples=%d, accuracy=%.4f, avg_loss=%.6f",
        total_samples, accuracy, avg_loss,
    )

    model.train()
    return accuracy, avg_loss
