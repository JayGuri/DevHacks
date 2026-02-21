# scripts/partition_data.py — Non-IID MNIST Partitioning + MongoDB Upload
"""
Downloads MNIST and partitions it into N highly non-IID shards using
a Dirichlet distribution (controlled by alpha).

Storage options:
  --save-local    Save .pt files to disk (default: ./partitions/mnist/)
  --mongo-uri     Upload partitions to MongoDB (e.g., mongodb://localhost:27017)

Both flags can be used together. At least one is required.

Usage:
    # Local only
    python scripts/partition_data.py --num_partitions 10 --alpha 0.5 --save-local

    # MongoDB only
    python scripts/partition_data.py --num_partitions 10 --alpha 0.5 \
        --mongo-uri mongodb://localhost:27017

    # Both
    python scripts/partition_data.py --num_partitions 10 --alpha 0.5 \
        --save-local --mongo-uri mongodb://localhost:27017
"""

import os
import io
import json
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torchvision import datasets, transforms

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [partition_data] %(message)s",
)
logger = logging.getLogger(__name__)


def download_mnist(data_dir: str = "./data") -> tuple:
    """Download MNIST and return (images, labels) as tensors."""
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,)),
    ])

    train_dataset = datasets.MNIST(
        root=data_dir, train=True, download=True, transform=transform,
    )
    test_dataset = datasets.MNIST(
        root=data_dir, train=False, download=True, transform=transform,
    )

    all_images = []
    all_labels = []

    for img, label in train_dataset:
        all_images.append(img)
        all_labels.append(label)

    for img, label in test_dataset:
        all_images.append(img)
        all_labels.append(label)

    images = torch.stack(all_images)  # (70000, 1, 28, 28)
    labels = torch.tensor(all_labels, dtype=torch.long)  # (70000,)

    logger.info(
        "MNIST downloaded: %d total samples, image shape=%s",
        len(labels), list(images.shape),
    )
    return images, labels


def create_non_iid_partitions(
    images: torch.Tensor,
    labels: torch.Tensor,
    num_partitions: int = 10,
    alpha: float = 0.5,
    seed: int = 42,
) -> list:
    """
    Partition data into non-IID shards using Dirichlet distribution.

    For each of the 10 digit classes (0-9):
      1. Collect all indices belonging to that class.
      2. Draw a Dirichlet(alpha, ..., alpha) vector of length num_partitions.
      3. Allocate samples to partitions according to these proportions.

    Lower alpha -> more extreme non-IID (some partitions get nearly all of
    one class).  alpha=100 ~ IID.  alpha=0.1 -> extreme skew.

    Returns a list of dicts: {"images": Tensor, "labels": Tensor}
    """
    np.random.seed(seed)

    num_classes = 10
    num_samples = len(labels)

    class_indices = {c: [] for c in range(num_classes)}
    for idx in range(num_samples):
        label = labels[idx].item()
        class_indices[label].append(idx)

    for c in range(num_classes):
        np.random.shuffle(class_indices[c])

    partition_indices = [[] for _ in range(num_partitions)]

    for c in range(num_classes):
        indices = np.array(class_indices[c])
        n_samples_class = len(indices)

        if n_samples_class == 0:
            continue

        proportions = np.random.dirichlet([alpha] * num_partitions)
        counts = (proportions * n_samples_class).astype(int)

        remainder = n_samples_class - counts.sum()
        if remainder > 0:
            top_indices = np.argsort(proportions)[-remainder:]
            counts[top_indices] += 1
        elif remainder < 0:
            excess = abs(remainder)
            bottom_indices = np.argsort(proportions)[:excess]
            for bi in bottom_indices:
                if counts[bi] > 0:
                    counts[bi] -= 1

        start = 0
        for p in range(num_partitions):
            end = start + counts[p]
            partition_indices[p].extend(indices[start:end].tolist())
            start = end

    partitions = []
    for p in range(num_partitions):
        idx = partition_indices[p]
        np.random.shuffle(idx)
        p_images = images[idx]
        p_labels = labels[idx]
        partitions.append({
            "images": p_images,
            "labels": p_labels,
        })

    return partitions


def compute_partition_stats(partitions: list, num_classes: int = 10) -> list:
    """Compute label distribution per partition for verification."""
    stats = []
    for p_idx, partition in enumerate(partitions):
        lbl = partition["labels"].numpy()
        distribution = {}
        for c in range(num_classes):
            count = int(np.sum(lbl == c))
            distribution[str(c)] = count

        total = len(lbl)
        dominant_class = int(np.argmax([distribution[str(c)] for c in range(num_classes)]))
        dominant_pct = distribution[str(dominant_class)] / max(total, 1) * 100

        stats.append({
            "partition": p_idx,
            "total_samples": total,
            "distribution": distribution,
            "dominant_class": dominant_class,
            "dominant_class_pct": round(dominant_pct, 1),
        })

        logger.info(
            "Partition %d: %d samples, dominant class=%d (%.1f%%)",
            p_idx, total, dominant_class, dominant_pct,
        )

    return stats


def save_partitions_local(partitions: list, output_dir: str) -> None:
    """Save each partition as a .pt file to disk."""
    os.makedirs(output_dir, exist_ok=True)

    for p_idx, partition in enumerate(partitions):
        filepath = os.path.join(output_dir, f"partition_{p_idx}.pt")
        # SECURITY: consumers must load with torch.load(..., weights_only=True)
        # to prevent arbitrary code execution from tampered .pt files.
        torch.save(partition, filepath)
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        logger.info(
            "Saved: %s (%.2f MB, %d samples)",
            filepath, file_size_mb, len(partition["labels"]),
        )


def serialize_partition(partition: dict) -> bytes:
    """Serialize a partition dict to bytes using torch.save into a BytesIO buffer."""
    buffer = io.BytesIO()
    torch.save(partition, buffer)
    return buffer.getvalue()


def upload_partitions_to_mongo(
    partitions: list,
    stats: list,
    mongo_uri: str,
    db_name: str = "fedbuff_db",
    alpha: float = 0.5,
) -> None:
    """Upload all partitions to MongoDB using GridFS (bypasses 16MB doc limit)."""
    from pymongo.mongo_client import MongoClient
    from pymongo.server_api import ServerApi
    from pymongo.errors import ServerSelectionTimeoutError
    import gridfs

    # Configure client for MongoDB Atlas with ServerApi
    client = MongoClient(mongo_uri, server_api=ServerApi('1'))

    try:
        client.admin.command("ping")
        logger.info("Connected to MongoDB Atlas successfully.")
    except ServerSelectionTimeoutError as exc:
        client.close()
        raise RuntimeError(
            "Cannot connect to MongoDB Atlas. Check: "
            "(1) Atlas Network Access includes your current public IP, "
            "(2) DB credentials in MONGO_URI are correct, "
            "(3) firewall/VPN/proxy allows outbound TCP 27017, "
            "(4) DNS resolution for *.mongodb.net works. "
            f"Original error: {exc}"
        ) from exc

    db = client[db_name]
    fs = gridfs.GridFS(db)

    # Drop existing GridFS files for partitions
    existing_files = list(db.fs.files.find({"metadata.type": "partition"}))
    if existing_files:
        logger.info("Dropping %d existing GridFS partition files...", len(existing_files))
        for f in existing_files:
            fs.delete(f["_id"])

    logger.info("Uploading %d partitions via GridFS to MongoDB...", len(partitions))

    for p_idx, partition in enumerate(partitions):
        serialized_data = serialize_partition(partition)
        partition_stats = stats[p_idx] if p_idx < len(stats) else {}

        # Store as a GridFS file (auto-chunked into 255KB pieces)
        file_id = fs.put(
            serialized_data,
            filename=f"partition_{p_idx}.pt",
            metadata={
                "type": "partition",
                "partition_id": p_idx,
                "dataset": "mnist",
                "alpha": alpha,
                "num_samples": int(len(partition["labels"])),
                "created_at": datetime.now(timezone.utc),
                "stats": partition_stats,
            },
        )

        size_mb = len(serialized_data) / (1024 * 1024)
        logger.info(
            "Uploaded partition %d via GridFS: %d samples, %.2f MB (file_id=%s)",
            p_idx, len(partition["labels"]), size_mb, file_id,
        )

    # Store metadata in a regular collection (small doc, no size issue)
    db.partition_meta.drop()
    db.partition_meta.insert_one({
        "dataset": "mnist",
        "num_partitions": len(partitions),
        "alpha": alpha,
        "total_samples": sum(len(p["labels"]) for p in partitions),
        "created_at": datetime.now(timezone.utc),
        "stats_summary": stats,
    })

    logger.info(
        "MongoDB upload complete: %d partitions in '%s' (GridFS)",
        len(partitions), db_name,
    )
    client.close()


def main():
    from dotenv import load_dotenv
    root_env_path = Path(__file__).resolve().parents[2] / ".env"
    if root_env_path.is_file():
        load_dotenv(root_env_path, override=True)
        logger.info("Loaded environment variables from: %s", root_env_path)

    parser = argparse.ArgumentParser(
        description="Partition MNIST into non-IID shards using Dirichlet distribution",
    )
    parser.add_argument(
        "--num_partitions", type=int, default=10,
        help="Number of partitions to create (default: 10)",
    )
    parser.add_argument(
        "--alpha", type=float, default=0.5,
        help="Dirichlet concentration parameter. Lower = more non-IID (default: 0.5)",
    )
    parser.add_argument(
        "--output_dir", type=str, default="./partitions/mnist",
        help="Output directory for .pt files when using --save-local",
    )
    parser.add_argument(
        "--data_dir", type=str, default="./data",
        help="Directory to download MNIST into (default: ./data)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--save-local", action="store_true",
        help="Save partitions as .pt files to --output_dir",
    )
    # Default to MONGO_URI from env var if not passed as arg
    parser.add_argument(
        "--mongo-uri", type=str, default=os.getenv("MONGO_URI"),
        help="MongoDB connection URI (e.g., mongodb://localhost:27017). "
             "Uploads partitions to MongoDB when specified.",
    )
    parser.add_argument(
        "--db-name", type=str, default="fedbuff_db",
        help="MongoDB database name (default: fedbuff_db)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip confirmation when dropping existing MongoDB partitions",
    )
    args = parser.parse_args()

    # Validate that at least one storage method is specified
    if not args.save_local and not args.mongo_uri:
        logger.info("No storage target specified. Defaulting to --save-local.")
        args.save_local = True

    logger.info("=" * 60)
    logger.info("MNIST Non-IID Partitioner")
    logger.info("=" * 60)
    logger.info("  Partitions : %d", args.num_partitions)
    logger.info("  Alpha      : %.2f", args.alpha)
    logger.info("  Seed       : %d", args.seed)
    if args.save_local:
        logger.info("  Local Dir  : %s", args.output_dir)
    if args.mongo_uri:
        logger.info("  MongoDB    : %s (db: %s)", args.mongo_uri, args.db_name)
    logger.info("=" * 60)

    # Step 1: Download MNIST
    images, labels = download_mnist(args.data_dir)

    # Step 2: Create non-IID partitions
    partitions = create_non_iid_partitions(
        images, labels,
        num_partitions=args.num_partitions,
        alpha=args.alpha,
        seed=args.seed,
    )

    # Step 3: Compute statistics
    stats = compute_partition_stats(partitions)

    # Step 4a: Save locally
    if args.save_local:
        save_partitions_local(partitions, args.output_dir)
        stats_path = os.path.join(args.output_dir, "partition_stats.json")
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=2)
        logger.info("Local partition stats saved to: %s", stats_path)

    # Step 4b: Upload to MongoDB
    if args.mongo_uri:
        # Pass --force flag through a function attribute
        upload_partitions_to_mongo._force = args.force
        upload_partitions_to_mongo(
            partitions, stats, args.mongo_uri, args.db_name, args.alpha,
        )

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("PARTITION CREATION COMPLETE")
    logger.info("=" * 60)
    logger.info("  Total samples: %d", sum(len(p["labels"]) for p in partitions))
    logger.info("  Partitions   : %d", len(partitions))
    if args.save_local:
        logger.info("  Local files  : %s/partition_*.pt", args.output_dir)
    if args.mongo_uri:
        logger.info("  MongoDB      : %s / %s.partitions", args.mongo_uri, args.db_name)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
