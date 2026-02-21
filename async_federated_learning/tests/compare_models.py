"""
Quick performance comparison: LSTM vs RNN on Shakespeare text.

Trains both models for a few iterations and compares:
- Training loss
- Perplexity
- Training speed
- Model capacity
"""

import sys
import os
import time
import torch
import torch.nn as nn
from torch.optim import Adam

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'async_federated_learning'))

from async_federated_learning.data.shakespeare_loader import ShakespearePartitioner
from async_federated_learning.models.lstm import LSTMTextModel
from async_federated_learning.models.rnn import RNNTextModel

print("=" * 80)
print("LSTM vs RNN PERFORMANCE COMPARISON")
print("=" * 80)

# Load data
print("\n[1] Loading Shakespeare dataset...")
data_path = "./data/raw/shakespeare_leaf_100.txt"
partitioner = ShakespearePartitioner(seq_length=80)
text = partitioner.load_dataset(data_path)
char_to_idx, idx_to_char, vocab_size = partitioner.build_vocabulary(text)

# Take a subset for training
train_text = text[:100000]  # First 100k characters
print(f"✅ Using {len(train_text):,} characters for training")

dataloader = partitioner.get_client_dataloader(train_text, batch_size=32, shuffle=True)
print(f"✅ Created DataLoader: {len(dataloader)} batches")

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"✅ Using device: {device}")

# Create models
print("\n[2] Creating models...")
lstm_model = LSTMTextModel(vocab_size, embedding_dim=128, hidden_dim=256, num_layers=2).to(device)
rnn_model = RNNTextModel(vocab_size, embedding_dim=128, hidden_dim=256, num_layers=2).to(device)

lstm_params = sum(p.numel() for p in lstm_model.parameters())
rnn_params = sum(p.numel() for p in rnn_model.parameters())

print(f"✅ LSTM: {lstm_params:,} parameters")
print(f"✅ RNN:  {rnn_params:,} parameters")
print(f"   Ratio: {lstm_params/rnn_params:.2f}x (LSTM is larger)")

# Training setup
criterion = nn.CrossEntropyLoss()
lstm_optimizer = Adam(lstm_model.parameters(), lr=0.001)
rnn_optimizer = Adam(rnn_model.parameters(), lr=0.001)

num_epochs = 2
print(f"\n[3] Training both models for {num_epochs} epochs...")

def train_model(model, optimizer, model_name):
    """Train a model and return metrics."""
    model.train()
    total_loss = 0.0
    total_correct = 0
    total_chars = 0
    start_time = time.time()
    
    for epoch in range(num_epochs):
        epoch_loss = 0.0
        for batch_idx, (inputs, targets) in enumerate(dataloader):
            inputs = inputs.to(device)
            targets = targets.to(device)
            
            batch_size = inputs.size(0)
            
            # Initialize hidden state
            if isinstance(model, LSTMTextModel):
                hidden = model.init_hidden(batch_size, device)
            else:
                hidden = model.init_hidden(batch_size, device)
            
            # Forward pass
            optimizer.zero_grad()
            logits, _ = model(inputs, hidden)
            
            # Compute loss
            logits_flat = logits.view(-1, vocab_size)
            targets_flat = targets.view(-1)
            loss = criterion(logits_flat, targets_flat)
            
            # Backward pass
            loss.backward()
            optimizer.step()
            
            # Track metrics
            epoch_loss += loss.item()
            predictions = torch.argmax(logits_flat, dim=1)
            correct = (predictions == targets_flat).sum().item()
            total_correct += correct
            total_chars += targets_flat.size(0)
            
            if batch_idx % 10 == 0:
                print(f"  {model_name} | Epoch {epoch+1}/{num_epochs} | Batch {batch_idx}/{len(dataloader)} | Loss: {loss.item():.4f}")
        
        total_loss += epoch_loss / len(dataloader)
    
    elapsed = time.time() - start_time
    avg_loss = total_loss / num_epochs
    perplexity = torch.exp(torch.tensor(avg_loss)).item()
    accuracy = total_correct / total_chars
    
    return {
        'loss': avg_loss,
        'perplexity': perplexity,
        'accuracy': accuracy,
        'time': elapsed,
    }

print("\n" + "-" * 80)
print("Training LSTM...")
print("-" * 80)
lstm_metrics = train_model(lstm_model, lstm_optimizer, "LSTM")

print("\n" + "-" * 80)
print("Training RNN...")
print("-" * 80)
rnn_metrics = train_model(rnn_model, rnn_optimizer, "RNN ")

# Results
print("\n" + "=" * 80)
print("RESULTS COMPARISON")
print("=" * 80)

print(f"\n{'Metric':<20} | {'LSTM':<15} | {'RNN':<15} | {'Winner':<10}")
print("-" * 80)

def compare(metric_name, lstm_val, rnn_val, lower_is_better=True):
    """Compare and print metric."""
    if lower_is_better:
        winner = "LSTM" if lstm_val < rnn_val else "RNN"
    else:
        winner = "LSTM" if lstm_val > rnn_val else "RNN"
    
    print(f"{metric_name:<20} | {lstm_val:<15.4f} | {rnn_val:<15.4f} | {winner:<10}")

compare("Loss", lstm_metrics['loss'], rnn_metrics['loss'], lower_is_better=True)
compare("Perplexity", lstm_metrics['perplexity'], rnn_metrics['perplexity'], lower_is_better=True)
compare("Accuracy", lstm_metrics['accuracy'], rnn_metrics['accuracy'], lower_is_better=False)
compare("Training Time (s)", lstm_metrics['time'], rnn_metrics['time'], lower_is_better=True)

print("-" * 80)
print(f"Parameters: LSTM={lstm_params:,}, RNN={rnn_params:,}")
print(f"Speedup: RNN is {lstm_metrics['time']/rnn_metrics['time']:.2f}x faster")
print(f"Accuracy gain: LSTM is {((lstm_metrics['accuracy']/rnn_metrics['accuracy'])-1)*100:.2f}% better")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if lstm_metrics['loss'] < rnn_metrics['loss'] * 0.95:
    print("✅ LSTM significantly outperforms RNN (>5% better loss)")
    print("   Recommendation: Use LSTM for production federated learning")
elif rnn_metrics['time'] < lstm_metrics['time'] * 0.7:
    print("✅ RNN is much faster than LSTM with similar accuracy")
    print("   Recommendation: Use RNN if speed is critical")
else:
    print("✅ Both models perform similarly")
    print("   Recommendation: Use LSTM for better accuracy, RNN for speed")

print("\n" + "=" * 80)
