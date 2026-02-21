# client/mongo_loader.py — MongoDB GridFS DataLoader for non-IID partitions
"""
MongoPartitionLoader: Fetches a pre-partitioned MNIST shard from MongoDB
via GridFS by partition_id (== NODE_INDEX) and wraps it in a PyTorch DataLoader.

The partition was uploaded by scripts/partition_data.py as a serialized
torch tensor stored in GridFS (auto-chunked to bypass 16MB doc limit).

Environment variables:
    MONGO_URI   - MongoDB connection string (default: mongodb://localhost:27017)
    MONGO_DB    - Database name (default: fedbuff_db)
    NODE_INDEX  - Partition index to fetch (default: 0)
"""

import os
import io
import logging

import torch
from torch.utils.data import DataLoader, TensorDataset

logger = logging.getLogger("fedbuff.mongo_loader")


class MongoPartitionLoader:
    """
    Fetches a non-IID MNIST partition from MongoDB GridFS and wraps it as a DataLoader.

    Each partition is stored as a GridFS file with metadata:
        metadata.partition_id: int
        metadata.dataset: str
        metadata.num_samples: int
        metadata.stats: dict (label distribution)
    The file content is the serialized torch tensor (via torch.save).
    """

    def __init__(
        self,
        mongo_uri: str = None,
        db_name: str = None,
        partition_id: int = None,
        batch_size: int = 32,
        shuffle: bool = True,
    ):
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name or os.getenv("MONGO_DB", "fedbuff_db")
        self.partition_id = partition_id if partition_id is not None else int(
            os.getenv("NODE_INDEX", os.getenv("NODE_ID", "0"))
        )
        self.batch_size = batch_size
        self.shuffle = shuffle
        self._dataloader = None
        self._num_samples = 0
        self._stats = {}

    def get_dataloader(self) -> DataLoader:
        """Fetch the partition from MongoDB GridFS and return a DataLoader."""
        if self._dataloader is not None:
            return self._dataloader

        try:
            self._dataloader = self._load_from_gridfs()
            return self._dataloader
        except Exception as e:
            logger.error(
                "Failed to load partition %d from MongoDB (%s): %s. "
                "Falling back to synthetic data.",
                self.partition_id, self.mongo_uri, e,
            )
            self._dataloader = self._synthetic_fallback()
            return self._dataloader

    def _load_from_gridfs(self) -> DataLoader:
        """Connect to MongoDB, fetch partition from GridFS, deserialize tensors."""
        from pymongo.mongo_client import MongoClient
        from pymongo.server_api import ServerApi
        import gridfs

        logger.info(
            "Connecting to MongoDB: %s (db: %s, partition_id: %d)",
            self.mongo_uri, self.db_name, self.partition_id,
        )

        client = MongoClient(
            self.mongo_uri,
            serverSelectionTimeoutMS=15000,
            server_api=ServerApi('1'),
        )
        db = client[self.db_name]
        fs = gridfs.GridFS(db)

        # Find the GridFS file by metadata.partition_id
        grid_file = fs.find_one({"metadata.partition_id": self.partition_id})

        if grid_file is None:
            client.close()
            raise ValueError(
                f"Partition {self.partition_id} not found in GridFS "
                f"(db: {self.db_name}). "
                f"Run partition_data.py --mongo-uri first."
            )

        # Read the full file content and deserialize
        raw_data = grid_file.read()
        grid_file.close()

        # Extract metadata
        metadata = grid_file.metadata or {}
        self._stats = metadata.get("stats", {})

        client.close()

        buffer = io.BytesIO(raw_data)
        partition = torch.load(buffer, map_location="cpu", weights_only=False)

        # Extract tensors
        images = partition.get("images", partition.get("x", None))
        labels = partition.get("labels", partition.get("y", None))

        if images is None or labels is None:
            raise ValueError(
                f"Partition {self.partition_id} missing 'images' or 'labels' keys."
            )

        if images.dtype != torch.float32:
            images = images.float()
        if labels.dtype != torch.long:
            labels = labels.long()

        self._num_samples = len(labels)

        # Log class distribution
        class_counts = {}
        for c in range(10):
            count = int((labels == c).sum().item())
            if count > 0:
                class_counts[c] = count

        logger.info(
            "Partition %d loaded from MongoDB (GridFS): %d samples, classes=%s",
            self.partition_id, self._num_samples, class_counts,
        )

        dataset = TensorDataset(images, labels)
        return DataLoader(
            dataset,
            batch_size=self.batch_size,
            shuffle=self.shuffle,
            drop_last=False,
        )

    def _synthetic_fallback(self) -> DataLoader:
        """Generate synthetic MNIST-like data when MongoDB is unavailable."""
        logger.warning(
            "SYNTHETIC FALLBACK: Generating random MNIST-like data. "
            "This is for development/testing only!"
        )
        num_samples = 256
        images = torch.randn(num_samples, 1, 28, 28, dtype=torch.float32)
        labels = torch.randint(0, 10, (num_samples,), dtype=torch.long)
        self._num_samples = num_samples

        dataset = TensorDataset(images, labels)
        return DataLoader(dataset, batch_size=self.batch_size, shuffle=self.shuffle)

    @property
    def num_samples(self) -> int:
        if self._dataloader is None:
            self.get_dataloader()
        return self._num_samples

    @property
    def stats(self) -> dict:
        return self._stats

    def __repr__(self) -> str:
        return (
            f"MongoPartitionLoader("
            f"uri='{self.mongo_uri}', db='{self.db_name}', "
            f"partition={self.partition_id}, samples={self._num_samples})"
        )
