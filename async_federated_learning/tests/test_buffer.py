# tests/test_buffer.py — Tests for AsyncBuffer
import os
import sys
import asyncio
import pytest
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.fl_server import AsyncBuffer


def make_fake_update(client_id, task="femnist"):
    """Create a minimal fake update dict for buffer testing."""
    return {
        "client_id": client_id,
        "task": task,
        "round_num": 1,
        "global_round_received": 0,
        "weights": {"w": [1, 2, 3]},
        "num_samples": 100,
        "local_loss": 0.5,
        "timestamp": time.time(),
    }


async def noop_callback(updates, task):
    """No-op aggregation callback for buffer tests."""
    pass


@pytest.mark.asyncio
class TestAsyncBuffer:
    """Tests for task-aware async buffer."""

    async def test_per_task_drain_at_k(self):
        """Test 1: Buffer drains exactly K items when K are available."""
        buffer = AsyncBuffer(
            buffer_size_k=3,
            supported_tasks=["femnist", "shakespeare"],
            aggregation_callback=noop_callback,
        )

        # Put 2 into femnist
        await buffer.put(make_fake_update("a", "femnist"), "femnist")
        await buffer.put(make_fake_update("b", "femnist"), "femnist")
        assert buffer.size("femnist") == 2

        # Drain should return empty (< K)
        result = await buffer.drain("femnist")
        assert result == []

        # Put 1 more
        await buffer.put(make_fake_update("c", "femnist"), "femnist")
        assert buffer.size("femnist") == 3

        # Drain should return 3
        result = await buffer.drain("femnist")
        assert len(result) == 3
        assert buffer.size("femnist") == 0
        assert buffer.size("shakespeare") == 0

    async def test_task_independence(self):
        """Test 2: Tasks are independent — draining one doesn't affect the other."""
        buffer = AsyncBuffer(
            buffer_size_k=3,
            supported_tasks=["femnist", "shakespeare"],
            aggregation_callback=noop_callback,
        )

        # Put 3 femnist, 2 shakespeare
        for i in range(3):
            await buffer.put(make_fake_update(f"f{i}", "femnist"), "femnist")
        for i in range(2):
            await buffer.put(make_fake_update(f"s{i}", "shakespeare"), "shakespeare")

        assert buffer.size("femnist") == 3
        assert buffer.size("shakespeare") == 2

        # Drain femnist
        result = await buffer.drain("femnist")
        assert len(result) == 3
        assert buffer.size("femnist") == 0

        # Shakespeare should be unaffected
        assert buffer.size("shakespeare") == 2

    async def test_concurrent_puts(self):
        """Test 3: Concurrent puts should all be enqueued correctly."""
        buffer = AsyncBuffer(
            buffer_size_k=3,
            supported_tasks=["femnist", "shakespeare"],
            aggregation_callback=noop_callback,
        )

        # asyncio.gather 6 puts (3 per task)
        tasks = []
        for i in range(3):
            tasks.append(buffer.put(make_fake_update(f"f{i}", "femnist"), "femnist"))
            tasks.append(buffer.put(make_fake_update(f"s{i}", "shakespeare"), "shakespeare"))

        await asyncio.gather(*tasks)

        assert buffer.size("femnist") == 3
        assert buffer.size("shakespeare") == 3

    async def test_atomic_drain(self):
        """Test 4: Concurrent drains — one gets items, other gets empty, no duplicates."""
        buffer = AsyncBuffer(
            buffer_size_k=3,
            supported_tasks=["femnist", "shakespeare"],
            aggregation_callback=noop_callback,
        )

        # Fill femnist with K=3
        for i in range(3):
            await buffer.put(make_fake_update(f"f{i}", "femnist"), "femnist")

        # Launch 2 concurrent drains
        results = await asyncio.gather(
            buffer.drain("femnist"),
            buffer.drain("femnist"),
        )

        # One should return 3, the other empty
        sizes = sorted([len(r) for r in results])
        assert sizes == [0, 3], f"Expected [0, 3] but got {sizes}"

        # No duplicates: combine all items
        all_items = []
        for r in results:
            all_items.extend(r)
        client_ids = [item["client_id"] for item in all_items]
        assert len(client_ids) == len(set(client_ids)), "Duplicate items found!"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
