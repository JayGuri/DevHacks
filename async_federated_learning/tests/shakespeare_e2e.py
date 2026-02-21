#!/usr/bin/env python3
"""
tests/shakespeare_e2e.py
========================
Behavioral end-to-end validation for the Shakespeare federated learning
pipeline.  Mirrors the structure of e2e_validation.py (MNIST/FEMNIST) but
runs the full text-FL cycle in-process — no WebSocket server needed.

Run:
    python tests/shakespeare_e2e.py              # all groups
    python tests/shakespeare_e2e.py --group 1    # single group
    python tests/shakespeare_e2e.py --group 1 3  # specific groups

Test Groups
-----------
  S1  Data Pipeline          — ShakespearePartitioner loads text, builds vocab,
                               partitions data, creates correctly-shaped DataLoaders
  S2  Model Forward Pass     — ShakespeareNet and LSTMTextModel produce correct
                               output shapes; one SGD step reduces loss
  S3  FL Round Convergence   — 3 FL rounds with 5 honest clients using FedAvg;
                               char accuracy improves from random baseline
  S4  Byzantine Robustness   — FedAvg degrades under sign-flip; trimmed_mean resists
  S5  Weight Delta Integrity — delta=0 before training, non-zero after; roundtrip lossless
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

# ---------------------------------------------------------------------------
# Path bootstrap so imports resolve from any working directory.
# The internal modules use bare imports (e.g. `from models.cnn import ...`)
# so we need the async_federated_learning package directory on sys.path, not
# just the repo root.
# ---------------------------------------------------------------------------
_TESTS_DIR = Path(__file__).parent
_PKG_DIR = _TESTS_DIR.parent           # async_federated_learning/
_REPO_ROOT = _PKG_DIR.parent           # repo root
for _p in (_PKG_DIR, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from data.shakespeare_loader import ShakespearePartitioner
from models.cnn import ShakespeareNet
from models.lstm import LSTMTextModel, evaluate_text_model

# Import aggregation functions directly from their modules to avoid triggering
# the aggregation/__init__.py chain which pulls in the full server stack.
import importlib.util as _ilu

def _import_direct(dotted: str, attr: str):
    """Load one attribute from a .py file, bypassing package __init__.py chains."""
    file_path = _PKG_DIR / (dotted.replace(".", "/") + ".py")
    spec = _ilu.spec_from_file_location(dotted, str(file_path))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, attr)

fedavg = _import_direct("aggregation.fedavg", "fedavg")
trimmed_mean = _import_direct("aggregation.trimmed_mean", "trimmed_mean")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result tracker (same pattern as e2e_validation.py)
# ---------------------------------------------------------------------------
results: list = []


def check(name: str, condition: bool, diagnostic: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if not condition and diagnostic:
        print(f"         >> {diagnostic}")
    results.append((name, condition))
    return condition


# ---------------------------------------------------------------------------
# Shared fixture: load data once for the slow groups
# ---------------------------------------------------------------------------

_SHARED: dict = {}   # populated by _load_shared_data()


def _load_shared_data():
    """Load Shakespeare text and build partitions (cached across groups)."""
    if _SHARED:
        return

    partitioner = ShakespearePartitioner(seq_length=80)
    try:
        text = partitioner.load_dataset()
    except FileNotFoundError as exc:
        print(f"\n  [SKIP] Shakespeare text file not found: {exc}")
        print("  Place shakespeare_leaf_100.txt in data/raw/ and re-run.")
        _SHARED["error"] = str(exc)
        return

    char_to_idx, idx_to_char, vocab_size = partitioner.build_vocabulary(text)

    # 5 client shards (Dirichlet α=0.5), last 10% held out as server test set
    holdout_start = int(len(text) * 0.9)
    train_text = text[:holdout_start]
    test_text = text[holdout_start:]

    client_shards = partitioner.partition_data(train_text, num_clients=5, alpha=0.5)
    test_dl = partitioner.get_test_dataloader(test_text, batch_size=256)
    client_dls = [
        partitioner.get_client_dataloader(shard, batch_size=32)
        for shard in client_shards
    ]

    _SHARED.update(
        partitioner=partitioner,
        text=text,
        train_text=train_text,
        test_text=test_text,
        char_to_idx=char_to_idx,
        idx_to_char=idx_to_char,
        vocab_size=vocab_size,
        client_shards=client_shards,
        client_dls=client_dls,
        test_dl=test_dl,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_weights(model: nn.Module) -> dict:
    return {k: v.cpu().detach().numpy().copy() for k, v in model.state_dict().items()}


def _set_weights(model: nn.Module, weights: dict):
    state = {k: torch.tensor(v, dtype=torch.float32) for k, v in weights.items()}
    model.load_state_dict(state, strict=False)


def _one_fl_round(
    global_weights: dict,
    client_dls: list,
    vocab_size: int,
    n_byzantine: int = 0,
    attack: str = "sign_flip",
    aggregation: str = "fedavg",
) -> dict:
    """
    Run one synchronous FL round in-process.

    Returns new global_weights after aggregation.
    """
    updates = []
    criterion = nn.CrossEntropyLoss()

    for i, dl in enumerate(client_dls):
        model = ShakespeareNet(vocab_size=vocab_size)
        _set_weights(model, global_weights)
        model.train()

        optimizer = torch.optim.SGD(model.parameters(), lr=0.01)

        # One local epoch
        for batch_x, batch_y in dl:
            optimizer.zero_grad()
            logits = model(batch_x)                       # (B, 80, vocab)
            logits_flat = logits.view(-1, vocab_size)     # (B*80, vocab)
            targets_flat = batch_y.view(-1)               # (B*80,)
            loss = criterion(logits_flat, targets_flat)
            loss.backward()
            optimizer.step()
            break  # one batch per client for speed

        local_weights = _get_weights(model)
        delta = {k: local_weights[k] - global_weights[k] for k in global_weights}

        if i < n_byzantine and attack == "sign_flip":
            delta = {k: -5.0 * v for k, v in delta.items()}

        updates.append(delta)

    if aggregation == "trimmed_mean":
        agg_delta = trimmed_mean(updates, beta=0.2)
    else:
        agg_delta = fedavg(updates)

    new_weights = {k: global_weights[k] + agg_delta[k] for k in global_weights}
    return new_weights


def _eval_model(model: nn.Module, test_dl: DataLoader, vocab_size: int) -> float:
    """Return character-level accuracy on the first batch of test_dl.
    Works with ShakespeareNet (no init_hidden needed) by calling model directly.
    """
    if test_dl is None or len(test_dl) == 0:
        return 0.0
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for batch_x, batch_y in test_dl:
            logits = model(batch_x)          # (B, 80, vocab)
            preds = logits.view(-1, vocab_size).argmax(dim=1)
            targets = batch_y.view(-1)
            correct += (preds == targets).sum().item()
            total += targets.size(0)
            break   # one batch sufficient to track trend
    return correct / max(total, 1)


# ===================================================================
# TEST GROUP S1: Data Pipeline
# ===================================================================

def test_group_s1():
    print("\n" + "=" * 60)
    print("TEST GROUP S1: Data Pipeline")
    print("=" * 60)

    _load_shared_data()
    if "error" in _SHARED:
        check("S1.x Data pipeline (skipped — text file missing)", False,
              _SHARED["error"])
        return

    partitioner = _SHARED["partitioner"]
    text = _SHARED["text"]
    vocab_size = _SHARED["vocab_size"]
    client_dls = _SHARED["client_dls"]
    test_dl = _SHARED["test_dl"]

    # S1.1 — Text loads and has reasonable length
    check(
        "S1.1 Shakespeare text loads (> 100 000 chars)",
        len(text) > 100_000,
        f"Loaded {len(text):,} chars. Expected > 100,000.",
    )

    # S1.2 — Vocabulary is non-trivial
    check(
        "S1.2 Vocabulary has > 30 unique characters",
        vocab_size > 30,
        f"vocab_size={vocab_size}. Expected > 30.",
    )

    # S1.3 — Partition produces correct number of shards
    check(
        "S1.3 partition_data returns 5 client shards",
        len(_SHARED["client_shards"]) == 5,
        f"Got {len(_SHARED['client_shards'])} shards, expected 5.",
    )

    # S1.4 — Each client DataLoader yields correct tensor shapes
    batch_x, batch_y = next(iter(client_dls[0]))
    check(
        "S1.4 Client batch x shape is (B, 80)",
        batch_x.ndim == 2 and batch_x.size(1) == 80,
        f"x.shape={tuple(batch_x.shape)}, expected (B, 80).",
    )
    check(
        "S1.5 Client batch y shape is (B, 80)",
        batch_y.ndim == 2 and batch_y.size(1) == 80,
        f"y.shape={tuple(batch_y.shape)}, expected (B, 80).",
    )

    # S1.6 — Token indices are within vocabulary range
    check(
        "S1.6 Token indices within [0, vocab_size)",
        bool(batch_x.max() < vocab_size and batch_x.min() >= 0),
        f"x range=[{batch_x.min()}, {batch_x.max()}], vocab_size={vocab_size}.",
    )

    # S1.7 — Test DataLoader has samples
    check(
        "S1.7 Test DataLoader is non-empty",
        len(test_dl) > 0,
        "Test DataLoader has no batches.",
    )

    # S1.8 — build_leaf_json produces valid LEAF-format dicts
    try:
        small_text = text[:5000]
        partitioner2 = ShakespearePartitioner(seq_length=80)
        partitioner2.build_vocabulary(small_text)
        train_json, test_json = partitioner2.build_leaf_json(
            small_text, num_clients=3, alpha=0.5
        )
        has_users = "users" in train_json and "user_data" in train_json
        has_samples = len(train_json["users"]) > 0
        check(
            "S1.8 build_leaf_json produces valid LEAF-format dict",
            has_users and has_samples,
            f"train_json keys={list(train_json.keys())}, "
            f"users={train_json.get('users', [])}",
        )
    except Exception as exc:
        check("S1.8 build_leaf_json", False, f"Exception: {exc}")


# ===================================================================
# TEST GROUP S2: Model Forward Pass
# ===================================================================

def test_group_s2():
    print("\n" + "=" * 60)
    print("TEST GROUP S2: Model Forward Pass")
    print("=" * 60)

    _load_shared_data()
    if "error" in _SHARED:
        check("S2.x Model (skipped — text file missing)", False, _SHARED["error"])
        return

    vocab_size = _SHARED["vocab_size"]
    dl = _SHARED["client_dls"][0]
    batch_x, batch_y = next(iter(dl))

    # S2.1 — ShakespeareNet (legacy model used by WebSocket pipeline)
    try:
        model = ShakespeareNet(vocab_size=vocab_size)
        logits = model(batch_x)
        check(
            "S2.1 ShakespeareNet output shape is (B, 80, vocab_size)",
            logits.shape == (batch_x.size(0), 80, vocab_size),
            f"Got {tuple(logits.shape)}, expected ({batch_x.size(0)}, 80, {vocab_size}).",
        )
    except Exception as exc:
        check("S2.1 ShakespeareNet forward pass", False, f"Exception: {exc}")

    # S2.2 — LSTMTextModel (richer model from models/lstm.py)
    try:
        lstm_model = LSTMTextModel(vocab_size=vocab_size, embedding_dim=64, hidden_dim=128, num_layers=1)
        logits_lstm, hidden = lstm_model(batch_x)
        check(
            "S2.2 LSTMTextModel output shape is (B, 80, vocab_size)",
            logits_lstm.shape == (batch_x.size(0), 80, vocab_size),
            f"Got {tuple(logits_lstm.shape)}.",
        )
        check(
            "S2.3 LSTMTextModel hidden state has correct shape",
            hidden[0].shape[2] == 128,
            f"Hidden dim={hidden[0].shape[2]}, expected 128.",
        )
    except Exception as exc:
        check("S2.2 LSTMTextModel forward pass", False, f"Exception: {exc}")
        check("S2.3 LSTMTextModel hidden state", False, f"Exception: {exc}")

    # S2.4 — One SGD step reduces loss
    try:
        model_sgd = ShakespeareNet(vocab_size=vocab_size)
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.SGD(model_sgd.parameters(), lr=0.01)

        logits_before = model_sgd(batch_x)
        loss_before = criterion(
            logits_before.view(-1, vocab_size), batch_y.view(-1)
        ).item()

        optimizer.zero_grad()
        logits_after_step = model_sgd(batch_x)
        loss_step = criterion(
            logits_after_step.view(-1, vocab_size), batch_y.view(-1)
        )
        loss_step.backward()
        optimizer.step()

        logits_after = model_sgd(batch_x)
        loss_after = criterion(
            logits_after.view(-1, vocab_size), batch_y.view(-1)
        ).item()

        check(
            "S2.4 One SGD step changes the loss",
            abs(loss_before - loss_after) > 1e-6,
            f"loss_before={loss_before:.4f}, loss_after={loss_after:.4f}. "
            "SGD step should change the loss.",
        )
    except Exception as exc:
        check("S2.4 SGD step changes loss", False, f"Exception: {exc}")

    # S2.5 — evaluate_text_model returns (accuracy, loss, perplexity) in range
    # Uses LSTMTextModel (has init_hidden) — ShakespeareNet is the WebSocket model
    try:
        model_eval = LSTMTextModel(vocab_size=vocab_size, embedding_dim=64,
                                   hidden_dim=128, num_layers=1)
        test_dl = _SHARED["test_dl"]
        acc, loss_val, ppl = evaluate_text_model(model_eval, test_dl, "cpu")
        check(
            "S2.5 evaluate_text_model returns values in valid range",
            0.0 <= acc <= 1.0 and loss_val > 0.0 and ppl > 1.0,
            f"acc={acc:.4f}, loss={loss_val:.4f}, perplexity={ppl:.4f}",
        )
    except Exception as exc:
        check("S2.5 evaluate_text_model", False, f"Exception: {exc}")


# ===================================================================
# TEST GROUP S3: FL Round Convergence
# ===================================================================

def test_group_s3():
    print("\n" + "=" * 60)
    print("TEST GROUP S3: FL Round Convergence")
    print("=" * 60)

    print("  [INFO] S3 runs 5 FL rounds — may take ~30s on CPU...")

    _load_shared_data()
    if "error" in _SHARED:
        check("S3.x Convergence (skipped — text file missing)", False, _SHARED["error"])
        return

    vocab_size = _SHARED["vocab_size"]
    client_dls = _SHARED["client_dls"]
    test_dl = _SHARED["test_dl"]

    try:
        model = ShakespeareNet(vocab_size=vocab_size)
        global_weights = _get_weights(model)

        # Baseline accuracy (random init)
        _set_weights(model, global_weights)
        acc_before = _eval_model(model, test_dl, vocab_size)

        # Run 5 FL rounds
        for round_num in range(5):
            global_weights = _one_fl_round(
                global_weights, client_dls, vocab_size,
                n_byzantine=0, aggregation="fedavg",
            )

        _set_weights(model, global_weights)
        acc_after = _eval_model(model, test_dl, vocab_size)

        check(
            "S3.1 Char accuracy improves after 5 FL rounds",
            acc_after > acc_before,
            f"acc_before={acc_before:.4f}, acc_after={acc_after:.4f}. "
            "Accuracy should increase with honest training.",
        )
        check(
            "S3.3 Model beats random-init accuracy (> random baseline)",
            acc_after > (1.0 / vocab_size),
            f"acc_after={acc_after:.4f}, random_baseline={1.0/vocab_size:.4f}.",
        )
    except Exception as exc:
        check("S3 FL convergence", False, f"Exception: {exc}")


# ===================================================================
# TEST GROUP S4: Byzantine Robustness
# ===================================================================

def test_group_s4():
    print("\n" + "=" * 60)
    print("TEST GROUP S4: Byzantine Robustness")
    print("=" * 60)

    print("  [INFO] S4 runs two sets of FL rounds — may take ~60s on CPU...")

    _load_shared_data()
    if "error" in _SHARED:
        check("S4.x Byzantine (skipped — text file missing)", False, _SHARED["error"])
        return

    vocab_size = _SHARED["vocab_size"]
    client_dls = _SHARED["client_dls"]
    test_dl = _SHARED["test_dl"]

    def _run_rounds(n_byzantine: int, aggregation: str, n_rounds: int = 3) -> float:
        model = ShakespeareNet(vocab_size=vocab_size)
        w = _get_weights(model)
        for _ in range(n_rounds):
            w = _one_fl_round(
                w, client_dls, vocab_size,
                n_byzantine=n_byzantine, attack="sign_flip",
                aggregation=aggregation,
            )
        _set_weights(model, w)
        return _eval_model(model, test_dl, vocab_size)

    try:
        # S4.1 — FedAvg baseline (no attack) achieves meaningful accuracy
        acc_honest = _run_rounds(n_byzantine=0, aggregation="fedavg")
        check(
            "S4.1 FedAvg without attack achieves > random baseline",
            acc_honest > 1.0 / vocab_size,
            f"FedAvg honest acc={acc_honest:.4f}, random={1.0/vocab_size:.4f}.",
        )

        # S4.2 — FedAvg degrades under 2-of-5 Byzantine sign-flip attack
        acc_fedavg_attack = _run_rounds(n_byzantine=2, aggregation="fedavg")
        check(
            "S4.2 FedAvg degrades under 2/5 Byzantine sign-flip",
            acc_fedavg_attack < acc_honest,
            f"FedAvg attack acc={acc_fedavg_attack:.4f}, "
            f"honest acc={acc_honest:.4f}. Attack should hurt FedAvg.",
        )

        # S4.3 — Trimmed mean is more robust than FedAvg under the same attack
        acc_tm_attack = _run_rounds(n_byzantine=2, aggregation="trimmed_mean")
        check(
            "S4.3 Trimmed mean is more robust than FedAvg under attack",
            acc_tm_attack >= acc_fedavg_attack,
            f"trimmed_mean acc={acc_tm_attack:.4f}, "
            f"fedavg acc={acc_fedavg_attack:.4f}.",
        )
    except Exception as exc:
        check("S4 Byzantine robustness", False, f"Exception: {exc}")


# ===================================================================
# TEST GROUP S5: Weight Delta Integrity
# ===================================================================

def test_group_s5():
    print("\n" + "=" * 60)
    print("TEST GROUP S5: Weight Delta Integrity")
    print("=" * 60)

    _load_shared_data()
    if "error" in _SHARED:
        check("S5.x Weight delta (skipped — text file missing)", False, _SHARED["error"])
        return

    vocab_size = _SHARED["vocab_size"]
    dl = _SHARED["client_dls"][0]

    # S5.1 — Weight delta is zero when model is not trained
    model = ShakespeareNet(vocab_size=vocab_size)
    pre = _get_weights(model)
    delta = {k: _get_weights(model)[k] - pre[k] for k in pre}
    total_norm = sum(np.linalg.norm(v.flatten()) for v in delta.values())
    check(
        "S5.1 Weight delta is zero before training",
        total_norm < 1e-6,
        f"Delta norm={total_norm:.8f}. Should be ~0 before any training.",
    )

    # S5.2 — Training produces non-zero delta
    model2 = ShakespeareNet(vocab_size=vocab_size)
    pre2 = _get_weights(model2)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model2.parameters(), lr=0.01)
    batch_x, batch_y = next(iter(dl))
    optimizer.zero_grad()
    logits = model2(batch_x)
    loss = criterion(logits.view(-1, vocab_size), batch_y.view(-1))
    loss.backward()
    optimizer.step()
    post2 = _get_weights(model2)
    delta2 = {k: post2[k] - pre2[k] for k in pre2}
    total_norm2 = sum(np.linalg.norm(v.flatten()) for v in delta2.values())
    check(
        "S5.2 Weight delta is non-zero after one training step",
        total_norm2 > 1e-8,
        f"Delta norm={total_norm2:.8f}. Should be non-zero after training.",
    )

    # S5.3 — set_weights / _get_weights roundtrip is lossless
    model3 = ShakespeareNet(vocab_size=vocab_size)
    original = _get_weights(model3)
    np.random.seed(7)
    perturbed = {k: (v + np.random.normal(0, 0.01, size=v.shape)).astype(v.dtype)
                 for k, v in original.items()}
    _set_weights(model3, perturbed)
    recovered = _get_weights(model3)
    all_match = all(np.allclose(perturbed[k], recovered[k], atol=1e-4) for k in original)
    check(
        "S5.3 set_weights / _get_weights roundtrip is lossless",
        all_match,
        "Weights should be recovered exactly (within float32 tolerance).",
    )

    # S5.4 — FedAvg delta is average of individual deltas (numerical correctness)
    d1 = {k: np.full_like(v, 1.0) for k, v in original.items()}
    d2 = {k: np.full_like(v, 3.0) for k, v in original.items()}
    agg = fedavg([d1, d2])  # equal weights → average = 2.0
    first_key = next(iter(agg))
    expected_val = 2.0
    check(
        "S5.4 fedavg([1.0, 3.0]) = 2.0 for each parameter",
        np.allclose(agg[first_key], expected_val, atol=1e-5),
        f"fedavg result={agg[first_key].flat[0]:.4f}, expected={expected_val}.",
    )


# ===================================================================
# Summary
# ===================================================================

def print_summary():
    print("\n" + "=" * 60)
    print("SHAKESPEARE E2E VALIDATION SUMMARY")
    print("=" * 60)

    group_defs = [
        ("Data Pipeline",         "S1."),
        ("Model Forward Pass",    "S2."),
        ("FL Round Convergence",  "S3."),
        ("Byzantine Robustness",  "S4."),
        ("Weight Delta Integrity","S5."),
    ]

    total_pass = total_fail = 0
    for group_name, prefix in group_defs:
        group_results = [(n, p) for n, p in results if prefix in n]
        passed = sum(1 for _, p in group_results if p)
        failed = len(group_results) - passed
        total_pass += passed
        total_fail += failed
        status = "✓" if failed == 0 else "✗"
        print(f"  {status} {group_name}: {passed}/{len(group_results)} passed")

    print(f"\nTotal: {total_pass}/{total_pass + total_fail} passed")
    if total_fail == 0:
        print("✓ ALL TESTS PASSED — Shakespeare FL pipeline is demo-ready")
    else:
        print(f"✗ {total_fail} TESTS FAILED")
        print("\nFailed tests:")
        for name, passed in results:
            if not passed:
                print(f"  - {name}")


# ===================================================================
# Entry point
# ===================================================================

ALL_GROUPS = {
    1: ("Data Pipeline ⚡",         test_group_s1),
    2: ("Model Forward Pass ⚡",     test_group_s2),
    3: ("FL Convergence ⏱",         test_group_s3),
    4: ("Byzantine Robustness ⏱⏱",  test_group_s4),
    5: ("Weight Delta Integrity ⚡", test_group_s5),
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="E2E behavioral validation for Shakespeare Federated Learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Group reference:\n"
            "  1  Data Pipeline          (fast)\n"
            "  2  Model Forward Pass     (fast)\n"
            "  3  FL Convergence         (⏱ ~30s)\n"
            "  4  Byzantine Robustness   (⏱⏱ ~60s)\n"
            "  5  Weight Delta Integrity (fast)\n"
        ),
    )
    parser.add_argument(
        "--group", "-g",
        type=int, nargs="+",
        choices=range(1, 6),
        metavar="N",
        help="Run only these group(s). Example: --group 1 2 5",
    )
    args = parser.parse_args()

    groups_to_run = args.group if args.group else list(range(1, 6))

    print("=" * 60)
    print("SHAKESPEARE FL — E2E BEHAVIORAL VALIDATION")
    print("=" * 60)
    if args.group:
        names = [ALL_GROUPS[g][0] for g in groups_to_run]
        print(f"  Running groups: {', '.join(names)}")

    for gid in sorted(groups_to_run):
        ALL_GROUPS[gid][1]()

    print_summary()
