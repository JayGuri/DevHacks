"""
models/rnn.py
=============
Simple RNN model for text (Shakespeare character prediction).

Simpler baseline compared to LSTM - lacks gating mechanisms.
"""

import logging
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class RNNTextModel(nn.Module):
    """
    Simple RNN-based model for character-level text prediction.
    
    Simpler architecture than LSTM - no gates, just tanh activation.
    Used as baseline to compare with LSTM performance.
    
    Architecture
    ------------
    embedding     : Embedding(vocab_size, embedding_dim)
    rnn           : RNN(embedding_dim, hidden_dim, num_layers, dropout)
    fc            : Linear(hidden_dim, vocab_size)
    
    Parameters
    ----------
    vocab_size    : int  — Size of character vocabulary
    embedding_dim : int  — Dimension of character embeddings (default 128)
    hidden_dim    : int  — RNN hidden state dimension (default 256)
    num_layers    : int  — Number of RNN layers (default 2)
    dropout       : float — Dropout probability between layers (default 0.3)
    """
    
    def __init__(
        self,
        vocab_size: int,
        embedding_dim: int = 128,
        hidden_dim: int = 256,
        num_layers: int = 2,
        dropout: float = 0.3,
    ):
        super().__init__()
        
        self.vocab_size = vocab_size
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        # Character embedding layer
        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        
        # Multi-layer RNN (vanilla, not LSTM)
        self.rnn = nn.RNN(
            embedding_dim,
            hidden_dim,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            nonlinearity='tanh',  # Standard RNN uses tanh
        )
        
        # Output projection to vocabulary
        self.fc = nn.Linear(hidden_dim, vocab_size)
        
        logger.info(
            f"RNNTextModel initialized: vocab_size={vocab_size}, "
            f"embedding_dim={embedding_dim}, hidden_dim={hidden_dim}, "
            f"num_layers={num_layers}, dropout={dropout}"
        )
    
    def forward(self, x, hidden=None):
        """
        Forward pass through RNN.
        
        Parameters
        ----------
        x : torch.Tensor
            Input character indices, shape (batch_size, seq_length)
        hidden : torch.Tensor | None
            Previous RNN hidden state or None to use zeros
            
        Returns
        -------
        tuple
            (logits, hidden_state) where:
            - logits: (batch_size, seq_length, vocab_size)
            - hidden_state: hidden state for next time step
        """
        batch_size = x.size(0)
        
        # Embed characters: (batch, seq_len) -> (batch, seq_len, embed_dim)
        embedded = self.embedding(x)
        
        # RNN forward: (batch, seq_len, embed_dim) -> (batch, seq_len, hidden_dim)
        rnn_out, hidden = self.rnn(embedded, hidden)
        
        # Project to vocabulary: (batch, seq_len, hidden_dim) -> (batch, seq_len, vocab_size)
        logits = self.fc(rnn_out)
        
        return logits, hidden
    
    def init_hidden(self, batch_size, device):
        """
        Initialize RNN hidden state with zeros.
        
        Parameters
        ----------
        batch_size : int
            Batch size for hidden state
        device : torch.device
            Device to create tensors on
            
        Returns
        -------
        torch.Tensor
            h0 zero-initialized hidden state
        """
        h0 = torch.zeros(self.num_layers, batch_size, self.hidden_dim).to(device)
        return h0


def evaluate_text_model(model, dataloader, device):
    """
    Evaluate RNN model on text dataset.
    
    Parameters
    ----------
    model : RNNTextModel
        Model to evaluate
    dataloader : DataLoader
        Validation/test data
    device : torch.device
        Device for computation
        
    Returns
    -------
    tuple
        (accuracy, loss, perplexity)
    """
    model.eval()
    criterion = nn.CrossEntropyLoss()
    
    total_loss = 0.0
    total_correct = 0
    total_chars = 0
    
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(dataloader):
            inputs = inputs.to(device)
            targets = targets.to(device)
            
            batch_size = inputs.size(0)
            hidden = model.init_hidden(batch_size, device)
            
            # Forward pass
            logits, _ = model(inputs, hidden)
            
            # Reshape for loss computation
            logits_flat = logits.view(-1, model.vocab_size)
            targets_flat = targets.view(-1)
            
            loss = criterion(logits_flat, targets_flat)
            total_loss += loss.item()
            
            # Compute accuracy
            predictions = torch.argmax(logits_flat, dim=1)
            correct = (predictions == targets_flat).sum().item()
            total_correct += correct
            total_chars += targets_flat.size(0)
    
    accuracy = total_correct / total_chars if total_chars > 0 else 0.0
    avg_loss = total_loss / len(dataloader) if len(dataloader) > 0 else 0.0
    perplexity = torch.exp(torch.tensor(avg_loss)).item()
    
    logger.info(
        f"RNN evaluation: accuracy={accuracy:.4f}, loss={avg_loss:.4f}, "
        f"perplexity={perplexity:.4f}"
    )
    
    return accuracy, avg_loss, perplexity
