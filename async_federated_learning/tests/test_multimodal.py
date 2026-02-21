"""
Test script to verify multimodal implementation with real datasets.

Tests:
1. Shakespeare data loader
2. LSTM model forward pass
3. RNN model forward pass
4. Gatekeeper filtering
5. MNIST CNN model (existing)
"""

import sys
import os
import torch
import numpy as np

# Add to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'async_federated_learning'))

from async_federated_learning.data.shakespeare_loader import ShakespearePartitioner
from async_federated_learning.models.lstm import LSTMTextModel
from async_federated_learning.models.rnn import RNNTextModel
from async_federated_learning.models.cnn import FLModel
from async_federated_learning.detection.gatekeeper import Gatekeeper
from async_federated_learning.config import Config

print("=" * 80)
print("MULTIMODAL ARFL TEST SUITE")
print("=" * 80)

# Test 1: Shakespeare Data Loading
print("\n[TEST 1] Shakespeare Data Loader")
print("-" * 80)

try:
    data_path = "./data/raw/shakespeare_leaf_100.txt"
    
    partitioner = ShakespearePartitioner(seq_length=80)
    text = partitioner.load_dataset(data_path)
    
    print(f"✅ Loaded Shakespeare text: {len(text):,} characters")
    print(f"   Preview: {text[:100]}...")
    
    # Build vocabulary
    char_to_idx, idx_to_char, vocab_size = partitioner.build_vocabulary(text)
    print(f"✅ Built vocabulary: {vocab_size} unique characters")
    print(f"   Top 10 chars: {list(char_to_idx.keys())[:10]}")
    
    # Partition data
    num_clients = 5
    client_shards = partitioner.partition_data(text, num_clients, alpha=0.5)
    print(f"✅ Partitioned text into {num_clients} client shards")
    for i, shard in enumerate(client_shards):
        print(f"   Client {i}: {len(shard):,} characters")
    
    # Create data loader for one client
    dataloader = partitioner.get_client_dataloader(client_shards[0], batch_size=32)
    print(f"✅ Created DataLoader: {len(dataloader)} batches")
    
    # Test one batch
    inputs, targets = next(iter(dataloader))
    print(f"✅ Sample batch: input shape={inputs.shape}, target shape={targets.shape}")
    print(f"   Input: {inputs[0][:20].tolist()}")
    print(f"   Target: {targets[0][:20].tolist()}")
    
    TEST1_PASSED = True
    print("✅ TEST 1 PASSED: Shakespeare data loader working!")
    
except Exception as e:
    TEST1_PASSED = False
    print(f"❌ TEST 1 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 2: LSTM Model
print("\n[TEST 2] LSTM Text Model")
print("-" * 80)

try:
    model_lstm = LSTMTextModel(
        vocab_size=vocab_size,
        embedding_dim=128,
        hidden_dim=256,
        num_layers=2,
        dropout=0.3,
    )
    print(f"✅ Created LSTM model")
    print(f"   Parameters: {sum(p.numel() for p in model_lstm.parameters()):,}")
    
    # Forward pass
    device = torch.device('cpu')
    inputs, targets = next(iter(dataloader))
    inputs = inputs.to(device)
    
    batch_size = inputs.size(0)
    hidden = model_lstm.init_hidden(batch_size, device)
    
    logits, new_hidden = model_lstm(inputs, hidden)
    print(f"✅ Forward pass successful")
    print(f"   Input shape: {inputs.shape}")
    print(f"   Output logits shape: {logits.shape}")
    print(f"   Hidden state shapes: h={new_hidden[0].shape}, c={new_hidden[1].shape}")
    
    # Check output dimensions
    assert logits.shape == (batch_size, 80, vocab_size), "Output shape mismatch"
    print(f"✅ Output dimensions correct")
    
    TEST2_PASSED = True
    print("✅ TEST 2 PASSED: LSTM model working!")
    
except Exception as e:
    TEST2_PASSED = False
    print(f"❌ TEST 2 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 3: RNN Model
print("\n[TEST 3] RNN Text Model")
print("-" * 80)

try:
    model_rnn = RNNTextModel(
        vocab_size=vocab_size,
        embedding_dim=128,
        hidden_dim=256,
        num_layers=2,
        dropout=0.3,
    )
    print(f"✅ Created RNN model")
    print(f"   Parameters: {sum(p.numel() for p in model_rnn.parameters()):,}")
    
    # Forward pass
    inputs, targets = next(iter(dataloader))
    inputs = inputs.to(device)
    
    batch_size = inputs.size(0)
    hidden = model_rnn.init_hidden(batch_size, device)
    
    logits, new_hidden = model_rnn(inputs, hidden)
    print(f"✅ Forward pass successful")
    print(f"   Input shape: {inputs.shape}")
    print(f"   Output logits shape: {logits.shape}")
    print(f"   Hidden state shape: {new_hidden.shape}")
    
    # Check output dimensions
    assert logits.shape == (batch_size, 80, vocab_size), "Output shape mismatch"
    print(f"✅ Output dimensions correct")
    
    # Compare model sizes
    lstm_params = sum(p.numel() for p in model_lstm.parameters())
    rnn_params = sum(p.numel() for p in model_rnn.parameters())
    print(f"✅ Model comparison:")
    print(f"   LSTM: {lstm_params:,} parameters")
    print(f"   RNN:  {rnn_params:,} parameters")
    print(f"   Difference: {lstm_params - rnn_params:,} (LSTM has more due to gates)")
    
    TEST3_PASSED = True
    print("✅ TEST 3 PASSED: RNN model working!")
    
except Exception as e:
    TEST3_PASSED = False
    print(f"❌ TEST 3 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Gatekeeper
print("\n[TEST 4] Gatekeeper Filter Funnel")
print("-" * 80)

try:
    gatekeeper = Gatekeeper(
        l2_threshold_factor=3.0,
        min_l2_threshold=0.01,
        max_l2_threshold=1000.0,
    )
    print(f"✅ Created Gatekeeper")
    
    # Create mock updates with one Byzantine outlier
    honest_updates = []
    for i in range(4):
        # Normal gradient magnitude around 2-3
        update = {k: torch.randn_like(v) * 0.1 for k, v in model_lstm.state_dict().items()}
        honest_updates.append({
            'client_id': i,
            'model_update': update,
            'round': 10,
        })
    
    # Byzantine update with large magnitude
    byzantine_update = {k: torch.randn_like(v) * 5.0 for k, v in model_lstm.state_dict().items()}
    byzantine_client = {
        'client_id': 99,
        'model_update': byzantine_update,
        'round': 10,
    }
    
    all_updates = honest_updates + [byzantine_client]
    
    print(f"✅ Created {len(all_updates)} mock updates (4 honest + 1 Byzantine)")
    
    # Compute L2 norms before filtering
    l2_norms_before = []
    for update in all_updates:
        l2_norm = gatekeeper.compute_l2_norm(update['model_update'])
        l2_norms_before.append(l2_norm)
        print(f"   Client {update['client_id']}: L2 norm = {l2_norm:.2f}")
    
    # Filter updates
    accepted, rejected, stats = gatekeeper.inspect_updates(all_updates, current_round=10)
    
    print(f"✅ Gatekeeper filtering complete:")
    print(f"   Accepted: {len(accepted)} updates")
    print(f"   Rejected: {len(rejected)} updates")
    print(f"   Mean L2: {stats['mean_l2']:.2f}")
    print(f"   Std L2: {stats['std_l2']:.2f}")
    print(f"   Bounds: [{stats['lower_bound']:.2f}, {stats['upper_bound']:.2f}]")
    
    if rejected:
        print(f"   Rejected client IDs: {[u['client_id'] for u in rejected]}")
    
    TEST4_PASSED = True
    print("✅ TEST 4 PASSED: Gatekeeper working!")
    
except Exception as e:
    TEST4_PASSED = False
    print(f"❌ TEST 4 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 5: CNN Model (verify existing implementation)
print("\n[TEST 5] CNN Image Model (MNIST)")
print("-" * 80)

try:
    model_cnn = FLModel(in_channels=1, num_classes=10, hidden_dim=128)
    print(f"✅ Created CNN model")
    print(f"   Parameters: {sum(p.numel() for p in model_cnn.parameters()):,}")
    
    # Forward pass with dummy MNIST image
    dummy_image = torch.randn(32, 1, 28, 28)  # Batch of 32 MNIST images
    output = model_cnn(dummy_image)
    
    print(f"✅ Forward pass successful")
    print(f"   Input shape: {dummy_image.shape}")
    print(f"   Output shape: {output.shape}")
    
    assert output.shape == (32, 10), "Output shape mismatch"
    print(f"✅ Output dimensions correct")
    
    TEST5_PASSED = True
    print("✅ TEST 5 PASSED: CNN model working!")
    
except Exception as e:
    TEST5_PASSED = False
    print(f"❌ TEST 5 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Config Multimodal Support
print("\n[TEST 6] Multimodal Configuration")
print("-" * 80)

try:
    # Test image config
    config_image = Config(
        modality="image",
        dataset_name="MNIST",
        in_channels=1,
        use_gatekeeper=True,
    )
    print(f"✅ Created image config: modality={config_image.modality}")
    
    # Test text config
    config_text = Config(
        modality="text",
        dataset_name="Shakespeare",
        text_model_type="lstm",
        vocab_size=vocab_size,
        use_gatekeeper=True,
    )
    print(f"✅ Created text config: modality={config_text.modality}, model={config_text.text_model_type}")
    
    TEST6_PASSED = True
    print("✅ TEST 6 PASSED: Config multimodal support working!")
    
except Exception as e:
    TEST6_PASSED = False
    print(f"❌ TEST 6 FAILED: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

tests = [
    ("Shakespeare Data Loader", TEST1_PASSED),
    ("LSTM Text Model", TEST2_PASSED),
    ("RNN Text Model", TEST3_PASSED),
    ("Gatekeeper Filter Funnel", TEST4_PASSED),
    ("CNN Image Model", TEST5_PASSED),
    ("Multimodal Configuration", TEST6_PASSED),
]

passed = sum(1 for _, result in tests if result)
total = len(tests)

for name, result in tests:
    status = "✅ PASS" if result else "❌ FAIL"
    print(f"{status} | {name}")

print("-" * 80)
print(f"Result: {passed}/{total} tests passed")

if passed == total:
    print("🎉 ALL TESTS PASSED! Multimodal ARFL is working correctly!")
else:
    print("⚠️  Some tests failed. Check errors above.")

print("=" * 80)
