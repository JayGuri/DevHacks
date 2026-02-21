# models/cnn.py — FLModel: lightweight CNN shared across all FL clients and server
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
- get_model(): factory function returning the correct model for a given task.
"""

import logging

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


# Shakespeare vocabulary (shared between LSTM and legacy)
VOCAB_SHAKESPEARE = (
    " !\"&'(),-.0123456789:;?ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
)  # 80 characters; unknown chars map to index 0


class FLModel(nn.Module):
    """
    Lightweight convolutional model shared across all FL clients and server.

    Architecture
    ------------
    conv_block1   : Conv2d(C_in, 32, 3, pad=1) -> BN -> ReLU -> MaxPool2d(2)
    conv_block2   : Conv2d(32, 64, 3, pad=1)   -> BN -> ReLU -> MaxPool2d(2)
    adaptive_pool : AdaptiveAvgPool2d((4, 4))   — makes input-size agnostic
    classifier    : Flatten -> Linear(1024, H) -> ReLU -> Dropout(0.3)
                    -> Linear(H, num_classes)

    AdaptiveAvgPool2d decouples the classifier head from spatial resolution so
    the same architecture works for 28x28 (MNIST) and 32x32 (CIFAR-10) inputs.

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
        self.hidden_dim = hidden_dim

        # Block 1: 32 feature maps, spatial dim halved by MaxPool
        self.conv_block1 = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2),
        )

        # Block 2: 64 feature maps, spatial dim halved again
        self.conv_block2 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2),
        )

        # Adaptive pooling -> fixed 4x4 spatial output regardless of input size
        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))

        # Classifier head: 64 channels x 4 x 4 spatial = 1024-dim
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
        """Compute logits for a batch of images.
        Input: (B, C, H, W) -> Output: (B, num_classes) raw logits.
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
        """Return a copy of the model's parameters as plain numpy arrays.
        Safe for cross-thread/process use.
        """
        return {
            name: tensor.cpu().detach().numpy().copy()
            for name, tensor in self.state_dict().items()
        }

    def set_weights(self, weights_dict: dict) -> None:
        """Load parameters from a dict of numpy arrays.
        Arrays converted to tensors matching original dtype/device.
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
        """Compute element-wise difference: current - pre_train_weights.
        Returns {name: current_array - pre_array} for every parameter key.
        """
        current_weights = self.get_weights()
        delta = {
            name: current_weights[name] - pre_train_weights[name]
            for name in current_weights
        }
        total_norm = float(
            np.sqrt(sum(np.sum(d ** 2) for d in delta.values()))
        )
        logger.debug("get_weight_delta — L2 norm of update: %.6f", total_norm)
        return delta

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def count_parameters(self) -> int:
        """Return total number of trainable scalar parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Legacy akshat models (kept for backward compatibility with websocket client)
# ---------------------------------------------------------------------------

class FEMNISTNet(nn.Module):
    """CNN for 62-class FEMNIST image classification.
    Input: (B, 1, 28, 28) float32  Output: (B, 62) logits
    """

    def __init__(self):
        super(FEMNISTNet, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, padding=1)
        self.relu1 = nn.ReLU()
        self.pool1 = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.relu2 = nn.ReLU()
        self.pool2 = nn.MaxPool2d(2, 2)
        self.fc1 = nn.Linear(64 * 7 * 7, 512)
        self.relu3 = nn.ReLU()
        self.dropout = nn.Dropout(0.5)
        self.fc2 = nn.Linear(512, 62)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool1(self.relu1(self.conv1(x)))
        x = self.pool2(self.relu2(self.conv2(x)))
        x = x.view(x.size(0), -1)
        x = self.dropout(self.relu3(self.fc1(x)))
        x = self.fc2(x)
        return x


class ShakespeareNet(nn.Module):
    """LSTM for next-character prediction on Shakespeare text.
    Input: (B, 80) long  Output: (B, 80, 80) logits
    """

    def __init__(self, vocab_size: int = 80, embed_dim: int = 8,
                 hidden_dim: int = 256, num_layers: int = 2):
        super(ShakespeareNet, self).__init__()
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, num_layers=num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(x)    # (B, 80, 8)
        lstm_out, _ = self.lstm(embedded)  # (B, 80, 256)
        logits = self.fc(lstm_out)       # (B, 80, 80)
        return logits


class VanillaRNNNet(nn.Module):
    """Vanilla RNN baseline for text sequence learning comparison.
    Input: (B, 80) long  Output: (B, 80, 80) logits
    """

    def __init__(self, vocab_size: int = 80, embed_dim: int = 8,
                 hidden_dim: int = 256, num_layers: int = 2):
        super(VanillaRNNNet, self).__init__()
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.embedding = nn.Embedding(vocab_size, embed_dim)
        self.rnn = nn.RNN(embed_dim, hidden_dim, num_layers=num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        embedded = self.embedding(x)    # (B, 80, 8)
        rnn_out, _ = self.rnn(embedded)  # (B, 80, 256)
        logits = self.fc(rnn_out)        # (B, 80, 80)
        return logits


# ---------------------------------------------------------------------------
# Standalone evaluation function
# ---------------------------------------------------------------------------

def evaluate_model(model, dataloader, device) -> tuple:
    """Evaluate a model on a full DataLoader and return (accuracy, avg_loss).
    Sets model to eval mode, computes metrics under no_grad, restores train mode.
    """
    model.eval()
    criterion = nn.CrossEntropyLoss(reduction="mean")

    total_correct = 0
    total_loss = 0.0
    total_samples = 0

    with torch.no_grad():
        for inputs, labels in dataloader:
            inputs = inputs.to(device)
            labels = labels.to(device)

            logits = model(inputs)

            batch_loss = criterion(logits, labels)
            batch_size = inputs.size(0)
            total_loss += batch_loss.item() * batch_size
            total_samples += batch_size

            preds = logits.argmax(dim=1)
            total_correct += (preds == labels).sum().item()

    accuracy = total_correct / total_samples
    avg_loss = total_loss / total_samples

    logger.info(
        "evaluate_model — samples=%d, accuracy=%.4f, avg_loss=%.6f",
        total_samples, accuracy, avg_loss,
    )

    model.train()
    return accuracy, avg_loss


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def get_model(task: str, **kwargs) -> nn.Module:
    """Returns the appropriate model for a given task string.

    Supported tasks:
      - 'femnist'      -> FEMNISTNet() (62 classes, 1-channel CNN)
      - 'shakespeare'  -> ShakespeareNet() (LSTM)
      - 'rnn'          -> VanillaRNNNet() (Vanilla RNN baseline)
      - 'MNIST'        -> FLModel(in_channels=1, num_classes=10)
      - 'CIFAR10'      -> FLModel(in_channels=3, num_classes=10)
    """
    if task == "femnist":
        return FEMNISTNet()
    elif task == "shakespeare":
        return ShakespeareNet()
    elif task == "rnn":
        return VanillaRNNNet()
    elif task == "MNIST":
        return FLModel(in_channels=kwargs.get("in_channels", 1),
                       num_classes=kwargs.get("num_classes", 10),
                       hidden_dim=kwargs.get("hidden_dim", 128))
    elif task == "CIFAR10":
        return FLModel(in_channels=kwargs.get("in_channels", 3),
                       num_classes=kwargs.get("num_classes", 10),
                       hidden_dim=kwargs.get("hidden_dim", 128))
    else:
        raise ValueError(f"Unknown task: {task}. Supported: 'femnist', 'shakespeare', 'rnn', 'MNIST', 'CIFAR10'.")
