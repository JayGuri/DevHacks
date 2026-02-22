# server/chunk_manager.py — MongoDB-backed chunk registry for federated data partitions
"""
ChunkManager
============
Manages data-chunk ↔ client assignments in MongoDB so that:
 • No two clients ever train on the same chunk simultaneously.
 • Disconnected clients' chunks are released atomically.
 • All critical events are logged with structured messages matching
   the spec: ASSIGNED / REJECTED / RELEASED / ERROR.

Mongo collection: ``fl_chunks``  (configurable)

Document schema
---------------
{
    "chunk_id":      3,
    "status":        "in_use",        // "available" | "in_use"
    "assigned_to":   "node_7",        // client_id or null
    "sample_count":  2847,
    "dataset":       "femnist",
    "classes":       [0, 1, ..., 61], // unique label list (populated on first load)
    "loaded_from":   "mongodb",
    "assigned_at":   ISODate(...),
    "released_at":   ISODate(...)
}
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger("fedbuff.chunk_manager")


class ChunkManager:
    """Manages chunk ↔ client assignments with MongoDB-backed state.

    Parameters
    ----------
    mongo_uri : str
        MongoDB connection string.
    db_name : str
        Database name (same DB that holds GridFS partitions).
    total_chunks : int
        Total number of data chunks (== MAX_NODES_PER_TASK).
    max_clients : int
        Maximum concurrent clients allowed (== total_chunks by default).
    collection_name : str
        Name of the Mongo collection for chunk tracking.
    """

    def __init__(
        self,
        mongo_uri: str,
        db_name: str,
        total_chunks: int = 10,
        max_clients: int = 10,
        collection_name: str = "fl_chunks",
    ):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.total_chunks = total_chunks
        self.max_clients = max_clients
        self.collection_name = collection_name

        # In-memory mirror for fast reads (source of truth is Mongo)
        self._assignments: Dict[int, Optional[str]] = {}  # chunk_id -> client_id | None
        self._client_chunks: Dict[str, int] = {}          # client_id -> chunk_id

        self._mongo_available = False
        self._collection = None  # type: ignore[assignment]

        self._init_mongo()

    # ------------------------------------------------------------------
    # MongoDB initialisation
    # ------------------------------------------------------------------

    def _init_mongo(self) -> None:
        """Connect to MongoDB and ensure the fl_chunks collection is seeded."""
        try:
            from pymongo.mongo_client import MongoClient
            from pymongo.server_api import ServerApi

            client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=10_000,
                server_api=ServerApi("1"),
            )
            # Verify connectivity
            client.admin.command("ping")

            db = client[self.db_name]
            self._collection = db[self.collection_name]

            # Create unique index on chunk_id for atomic find_one_and_update
            self._collection.create_index("chunk_id", unique=True)

            # Seed missing chunks as "available"
            existing_ids = {
                doc["chunk_id"]
                for doc in self._collection.find({}, {"chunk_id": 1})
            }

            for cid in range(self.total_chunks):
                if cid not in existing_ids:
                    self._collection.insert_one({
                        "chunk_id": cid,
                        "status": "available",
                        "assigned_to": None,
                        "sample_count": 0,
                        "dataset": "",
                        "classes": [],
                        "loaded_from": "mongodb",
                        "assigned_at": None,
                        "released_at": None,
                    })

            # On startup, reset any stale "in_use" chunks (server crash recovery)
            stale = self._collection.update_many(
                {"status": "in_use"},
                {"$set": {
                    "status": "available",
                    "assigned_to": None,
                    "released_at": datetime.now(timezone.utc),
                }},
            )
            if stale.modified_count:
                logger.warning(
                    "Reset %d stale in_use chunks on startup (crash recovery).",
                    stale.modified_count,
                )

            # Populate in-memory mirror
            for doc in self._collection.find():
                cid = doc["chunk_id"]
                self._assignments[cid] = doc.get("assigned_to")

            self._mongo_available = True
            logger.info(
                "ChunkManager initialised: total_chunks=%d, max_clients=%d, "
                "collection=%s, available=%d",
                self.total_chunks,
                self.max_clients,
                self.collection_name,
                self.available_count,
            )
        except Exception as exc:
            logger.error("ChunkManager: MongoDB unavailable (%s). Using in-memory fallback.", exc)
            self._mongo_available = False
            # Seed in-memory
            for cid in range(self.total_chunks):
                self._assignments[cid] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign_chunk(
        self,
        client_id: str,
        dataset: str = "",
        preferred_chunk: Optional[int] = None,
    ) -> Tuple[bool, int, str]:
        """Atomically assign an available chunk to *client_id*.

        Returns
        -------
        (success, chunk_id, message)
        """
        # Guard: max clients
        active = self.active_count
        if active >= self.max_clients:
            msg = f"REJECTED: Max clients ({active}/{self.max_clients}) reached"
            logger.warning("[SERVER] %s — client=%s", msg, client_id)
            return False, -1, msg

        # Guard: client already has a chunk
        if client_id in self._client_chunks:
            existing = self._client_chunks[client_id]
            msg = f"Client {client_id} already assigned chunk {existing}"
            logger.info("[SERVER] %s", msg)
            return True, existing, msg

        # Determine which chunk to assign
        if preferred_chunk is not None and self._is_available(preferred_chunk):
            target_chunk = preferred_chunk
        else:
            target_chunk = self._next_available()

        if target_chunk is None:
            avail = self.available_count
            msg = f"REJECTED: No chunks available (available={avail}, in_use={self.active_count})"
            logger.warning("[SERVER] %s — client=%s", msg, client_id)
            return False, -1, msg

        # Atomic Mongo update (find available → set in_use)
        if self._mongo_available:
            result = self._collection.find_one_and_update(
                {"chunk_id": target_chunk, "status": "available"},
                {"$set": {
                    "status": "in_use",
                    "assigned_to": client_id,
                    "dataset": dataset,
                    "assigned_at": datetime.now(timezone.utc),
                    "released_at": None,
                }},
            )
            if result is None:
                # Race: another request grabbed it first — try again
                alt = self._next_available_mongo()
                if alt is None:
                    msg = "REJECTED: Chunk assignment race — no chunks left"
                    logger.warning("[SERVER] %s — client=%s", msg, client_id)
                    return False, -1, msg
                target_chunk = alt
                self._collection.find_one_and_update(
                    {"chunk_id": target_chunk, "status": "available"},
                    {"$set": {
                        "status": "in_use",
                        "assigned_to": client_id,
                        "dataset": dataset,
                        "assigned_at": datetime.now(timezone.utc),
                        "released_at": None,
                    }},
                )

        # Update in-memory mirror
        self._assignments[target_chunk] = client_id
        self._client_chunks[client_id] = target_chunk

        logger.info(
            "[SERVER] New client connected: client_id=%s, assigned_chunk=%d/%d",
            client_id, target_chunk, self.total_chunks,
        )
        logger.info(
            "[SERVER] Active clients: %d/%d | Available chunks: %d remaining",
            self.active_count, self.max_clients, self.available_count,
        )
        return True, target_chunk, f"Assigned chunk {target_chunk}/{self.total_chunks}"

    def release_chunk(self, client_id: str) -> Optional[int]:
        """Release the chunk held by *client_id*. Returns chunk_id or None."""
        chunk_id = self._client_chunks.pop(client_id, None)
        if chunk_id is None:
            logger.debug("release_chunk: client %s had no chunk assigned.", client_id)
            return None

        # Mongo atomic release
        if self._mongo_available:
            self._collection.find_one_and_update(
                {"chunk_id": chunk_id, "assigned_to": client_id},
                {"$set": {
                    "status": "available",
                    "assigned_to": None,
                    "released_at": datetime.now(timezone.utc),
                }},
            )

        self._assignments[chunk_id] = None

        logger.info(
            "[SERVER] %s disconnected → chunk_%d released → available again",
            client_id, chunk_id,
        )
        logger.info(
            "[SERVER] Active clients: %d/%d | Available chunks: %d remaining",
            self.active_count, self.max_clients, self.available_count,
        )
        return chunk_id

    def update_chunk_metadata(
        self,
        chunk_id: int,
        sample_count: int = 0,
        classes: Optional[List[int]] = None,
        dataset: str = "",
    ) -> None:
        """Update sample_count / class list after the chunk is loaded from Mongo GridFS."""
        if self._mongo_available:
            update_doc: dict = {"sample_count": sample_count, "loaded_from": "mongodb"}
            if dataset:
                update_doc["dataset"] = dataset
            if classes is not None:
                update_doc["classes"] = classes
            self._collection.update_one(
                {"chunk_id": chunk_id},
                {"$set": update_doc},
            )

        logger.info(
            "[SERVER] Chunk %d: %d samples, classes=%s, loaded_from=mongodb",
            chunk_id, sample_count, classes or "unknown",
        )

    def get_chunk_for_client(self, client_id: str) -> Optional[int]:
        """Return the chunk_id currently assigned to *client_id*, or None."""
        return self._client_chunks.get(client_id)

    def get_chunk_info(self, chunk_id: int) -> Optional[dict]:
        """Return the full chunk document from Mongo (or in-memory stub)."""
        if self._mongo_available:
            return self._collection.find_one({"chunk_id": chunk_id}, {"_id": 0})
        return {
            "chunk_id": chunk_id,
            "status": "in_use" if self._assignments.get(chunk_id) else "available",
            "assigned_to": self._assignments.get(chunk_id),
        }

    def validate_no_duplicates(self) -> List[str]:
        """Integrity check: ensure no chunk is assigned to two clients.

        Returns a list of error messages (empty == healthy).
        """
        errors: List[str] = []
        seen: Dict[int, str] = {}
        for client_id, chunk_id in self._client_chunks.items():
            if chunk_id in seen:
                msg = f"ERROR: Chunk {chunk_id} already assigned to {seen[chunk_id]}"
                logger.error("[SERVER] %s — duplicate from %s", msg, client_id)
                errors.append(msg)
            seen[chunk_id] = client_id
        return errors

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def active_count(self) -> int:
        return len(self._client_chunks)

    @property
    def available_count(self) -> int:
        return self.total_chunks - self.active_count

    @property
    def status_summary(self) -> dict:
        return {
            "total_chunks": self.total_chunks,
            "chunks_in_use": self.active_count,
            "chunks_available": self.available_count,
            "max_clients": self.max_clients,
            "assignments": dict(self._client_chunks),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_available(self, chunk_id: int) -> bool:
        return self._assignments.get(chunk_id) is None

    def _next_available(self) -> Optional[int]:
        for cid in range(self.total_chunks):
            if self._assignments.get(cid) is None:
                return cid
        return None

    def _next_available_mongo(self) -> Optional[int]:
        """Query Mongo directly for an available chunk (handles race conditions)."""
        if not self._mongo_available:
            return self._next_available()
        doc = self._collection.find_one({"status": "available"}, {"chunk_id": 1})
        return doc["chunk_id"] if doc else None
