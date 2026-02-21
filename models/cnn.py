# models/cnn.py — FEMNISTNet (CNN), ShakespeareNet (LSTM), model factory
import torch
import torch.nn as nn


VOCAB_SHAKESPEARE = (
    " !\"&'(),-.0123456789:;?ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
)  # 80 characters; unknown chars map to index 0


class FEMNISTNet(nn.Module):
    """CNN for 62-class FEMNIST image classification.
    Input: (B, 1, 28, 28) float32
    Output: (B, 62) logits
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
        x = x.view(x.size(0), -1)  # Flatten: 64*7*7 = 3136
        x = self.dropout(self.relu3(self.fc1(x)))
        x = self.fc2(x)
        return x


class ShakespeareNet(nn.Module):
    """LSTM for next-character prediction on Shakespeare text.
    Input: (B, 80) long — character indices
    Output: (B, 80, 80) logits — prediction for each position over 80-char vocab
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
        embedded = self.embedding(x)  # (B, 80, 8)
        lstm_out, _ = self.lstm(embedded)  # (B, 80, 256)
        logits = self.fc(lstm_out)  # (B, 80, 80)
        return logits


def get_model(task: str) -> nn.Module:
    """Returns FEMNISTNet() for 'femnist', ShakespeareNet() for 'shakespeare'."""
    if task == "femnist":
        return FEMNISTNet()
    elif task == "shakespeare":
        return ShakespeareNet()
    else:
        raise ValueError(f"Unknown task: {task}. Supported: 'femnist', 'shakespeare'.")
