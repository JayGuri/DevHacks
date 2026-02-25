#!/usr/bin/env python3
"""
Integration test: Dynamic node registration + data partitioning.

Tests:
1. NodeRegistry creates nodes with unique indices
2. JWT tokens are valid and contain correct claims
3. LEAFLoader gives different data partitions to different nodes
4. MAX_NODES_PER_TASK limit is enforced
5. Server endpoints (POST /nodes/register, GET /nodes) work end-to-end
"""
import os
import sys
import json
import tempfile
import asyncio

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jwt

# ============================================================================
# Test 1: NodeRegistry — node creation and uniqueness
# ============================================================================

def test_node_registry_basic():
    """Test that NodeRegistry assigns unique sequential indices."""
    from server.node_registry import NodeRegistry

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        reg_file = f.name

    try:
        nr = NodeRegistry(reg_file, "test_secret_abc123", max_nodes_per_task=5)

        # Register 3 femnist nodes
        nodes = []
        for i in range(3):
            result = nr.register("femnist", "legitimate_client", f"Node-{i}")
            nodes.append(result)

        # Verify sequential indices
        indices = [n["node_index"] for n in nodes]
        assert indices == [0, 1, 2], f"Expected [0, 1, 2], got {indices}"

        # Verify total_nodes matches max
        for n in nodes:
            assert n["total_nodes"] == 5, f"Expected total_nodes=5, got {n['total_nodes']}"

        # Verify unique node IDs
        ids = [n["node_id"] for n in nodes]
        assert len(set(ids)) == 3, f"Expected 3 unique IDs, got {ids}"

        # Verify all have tokens
        for n in nodes:
            assert n["token"], f"Node {n['node_id']} has no token"

        # Verify list_nodes
        all_nodes = nr.list_nodes()
        assert len(all_nodes) == 3, f"Expected 3 nodes, got {len(all_nodes)}"

        femnist_nodes = nr.list_nodes(task="femnist")
        assert len(femnist_nodes) == 3

        shakespeare_nodes = nr.list_nodes(task="shakespeare")
        assert len(shakespeare_nodes) == 0

        # Verify count
        assert nr.get_count("femnist") == 3
        assert nr.get_count("shakespeare") == 0

        print("✅ Test 1 PASSED: NodeRegistry basic creation and uniqueness")
    finally:
        os.unlink(reg_file)


# ============================================================================
# Test 2: JWT token validation
# ============================================================================

def test_jwt_tokens():
    """Test that minted JWT tokens contain correct claims."""
    from server.node_registry import NodeRegistry

    secret = "test_jwt_secret_xyz"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        reg_file = f.name

    try:
        nr = NodeRegistry(reg_file, secret, max_nodes_per_task=10)

        result = nr.register("femnist", "legitimate_client", "Alice")
        token = result["token"]

        # Decode and validate
        payload = jwt.decode(token, secret, algorithms=["HS256"])

        assert payload["sub"] == result["node_id"]
        assert payload["display_name"] == "Alice"
        assert payload["role"] == "legitimate_client"
        assert payload["task"] == "femnist"
        assert payload["node_index"] == 0
        assert payload["total_nodes"] == 10

        # Register malicious node
        result2 = nr.register(
            "femnist", "malicious_client", "Mallory",
            attack_type="sign_flip_amplified", attack_scale=-5.0,
        )
        payload2 = jwt.decode(result2["token"], secret, algorithms=["HS256"])
        assert payload2["role"] == "malicious_client"
        assert payload2["node_index"] == 1

        print("✅ Test 2 PASSED: JWT tokens contain correct claims")
    finally:
        os.unlink(reg_file)


# ============================================================================
# Test 3: MAX_NODES_PER_TASK enforcement
# ============================================================================

def test_max_nodes_limit():
    """Test that registering beyond max_nodes_per_task raises ValueError."""
    from server.node_registry import NodeRegistry

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        reg_file = f.name

    try:
        nr = NodeRegistry(reg_file, "test_secret", max_nodes_per_task=2)

        nr.register("femnist", "legitimate_client", "N0")
        nr.register("femnist", "legitimate_client", "N1")

        # Third should fail
        try:
            nr.register("femnist", "legitimate_client", "N2")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "2/2" in str(e), f"Error message should mention limit: {e}"

        # Different task should still work
        result = nr.register("shakespeare", "legitimate_client", "S0")
        assert result["node_index"] == 0

        print("✅ Test 3 PASSED: MAX_NODES_PER_TASK enforced correctly")
    finally:
        os.unlink(reg_file)


# ============================================================================
# Test 4: Registry persistence (save/load)
# ============================================================================

def test_persistence():
    """Test that registry survives save/load cycle."""
    from server.node_registry import NodeRegistry

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        reg_file = f.name

    try:
        # Create and register
        nr1 = NodeRegistry(reg_file, "persist_secret", max_nodes_per_task=10)
        nr1.register("femnist", "legitimate_client", "A")
        nr1.register("femnist", "legitimate_client", "B")
        nr1.register("shakespeare", "legitimate_client", "C")

        # Load fresh instance
        nr2 = NodeRegistry(reg_file, "persist_secret", max_nodes_per_task=10)

        assert len(nr2.list_nodes()) == 3
        assert nr2.get_count("femnist") == 2
        assert nr2.get_count("shakespeare") == 1

        # Next femnist node should get index 2
        result = nr2.register("femnist", "legitimate_client", "D")
        assert result["node_index"] == 2, f"Expected index 2 after reload, got {result['node_index']}"

        print("✅ Test 4 PASSED: Registry persists and reloads correctly")
    finally:
        os.unlink(reg_file)


# ============================================================================
# Test 5: LEAFLoader partitioning — different nodes get different data
# ============================================================================

def test_data_partitioning():
    """Test that different node_index values get different data partitions."""
    from client.fl_client import LEAFLoader

    total_nodes = 5

    # Create 3 loaders with different indices
    loaders = []
    for idx in range(3):
        loader = LEAFLoader("femnist", node_index=idx, total_nodes=total_nodes, batch_size=32)
        loaders.append(loader)

    # Verify params stored correctly
    for idx, loader in enumerate(loaders):
        assert loader.node_index == idx, f"Expected node_index={idx}, got {loader.node_index}"
        assert loader.total_nodes == total_nodes, f"Expected total_nodes={total_nodes}, got {loader.total_nodes}"
        # Internal aliases should match
        assert loader.data_partition == idx
        assert loader.partition_count == total_nodes

    # Test partition logic with synthetic user list
    fake_users = [f"user_{i:04d}" for i in range(100)]
    partitions = []
    for loader in loaders:
        partition_users = loader._get_partition_users(fake_users)
        partitions.append(set(partition_users))

    # Verify non-overlapping partitions
    for i in range(len(partitions)):
        for j in range(i + 1, len(partitions)):
            overlap = partitions[i] & partitions[j]
            assert len(overlap) == 0, (
                f"Partitions {i} and {j} overlap by {len(overlap)} users: {overlap}"
            )

    # Verify all partitions have users
    for idx, p in enumerate(partitions):
        assert len(p) > 0, f"Partition {idx} is empty!"

    # Verify total coverage (first 3 of 5 partitions)
    total_covered = sum(len(p) for p in partitions)
    # With 100 users and 5 partitions, each gets ~20
    expected_per_partition = 100 // 5
    for idx, p in enumerate(partitions):
        assert abs(len(p) - expected_per_partition) <= 1, (
            f"Partition {idx} has {len(p)} users, expected ~{expected_per_partition}"
        )

    print(f"✅ Test 5 PASSED: Data partitions are non-overlapping")
    for idx, p in enumerate(partitions):
        print(f"   Node {idx}/{total_nodes}: {len(p)} users")


# ============================================================================
# Test 6: Full pipeline — NodeRegistry → LEAFLoader end-to-end
# ============================================================================

def test_end_to_end_pipeline():
    """Simulate the full flow: register nodes → create LEAFLoaders → verify data."""
    from server.node_registry import NodeRegistry
    from client.fl_client import LEAFLoader

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        reg_file = f.name

    try:
        nr = NodeRegistry(reg_file, "e2e_secret", max_nodes_per_task=10)

        # Register 3 nodes (like add_node.py would do)
        node1 = nr.register("femnist", "legitimate_client", "Worker-1")
        node2 = nr.register("femnist", "legitimate_client", "Worker-2")
        node3 = nr.register("femnist", "malicious_client", "Attacker",
                            attack_type="sign_flip_amplified", attack_scale=-5.0)

        # Each node creates a LEAFLoader using its credentials
        loaders = []
        for node in [node1, node2, node3]:
            loader = LEAFLoader(
                dataset="femnist",
                node_index=node["node_index"],
                total_nodes=node["total_nodes"],
                batch_size=32,
            )
            loaders.append((node, loader))

        # Verify each loader has correct params
        for node, loader in loaders:
            assert loader.node_index == node["node_index"]
            assert loader.total_nodes == node["total_nodes"]

        # Verify partitions are different
        fake_users = [f"writer_{i:04d}" for i in range(200)]
        user_sets = []
        for node, loader in loaders:
            partition = loader._get_partition_users(fake_users)
            user_sets.append(set(partition))
            print(f"   {node['display_name']} (index={node['node_index']}): {len(partition)} users")

        # Non-overlapping check
        for i in range(len(user_sets)):
            for j in range(i + 1, len(user_sets)):
                overlap = user_sets[i] & user_sets[j]
                assert len(overlap) == 0, f"Nodes {i} and {j} share {len(overlap)} users!"

        print("✅ Test 6 PASSED: Full pipeline (registry → loader → data) works end-to-end")
    finally:
        os.unlink(reg_file)


# ============================================================================
# Test 7: FastAPI endpoints (in-process)
# ============================================================================

def test_fastapi_endpoints():
    """Test /nodes/register and /nodes endpoints via TestClient."""
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        print("⚠️  Test 7 SKIPPED: fastapi[testclient] not installed")
        return

    # Set required env vars before importing main
    os.environ.setdefault("JWT_SECRET", "test_integration_secret_12345")
    os.environ.setdefault("NODE_REGISTRY_FILE", "/tmp/test_node_registry_integration.json")
    os.environ.setdefault("MAX_NODES_PER_TASK", "10")

    # Clean up any leftover registry
    reg_path = os.environ["NODE_REGISTRY_FILE"]
    if os.path.exists(reg_path):
        os.unlink(reg_path)

    try:
        from main import app
        import main as main_module
        from server.node_registry import NodeRegistry

        # Manually initialize — TestClient may not run lifespan
        jwt_secret = os.environ["JWT_SECRET"]
        main_module.node_registry = NodeRegistry(
            registry_file=reg_path,
            jwt_secret=jwt_secret,
            max_nodes_per_task=int(os.environ["MAX_NODES_PER_TASK"]),
        )

        client = TestClient(app)

        # Register first node
        resp = client.post("/nodes/register", json={
            "task": "femnist",
            "role": "legitimate_client",
            "display_name": "IntegrationNode1",
        })
        assert resp.status_code == 200, f"Register failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert data["node_index"] == 0
        assert data["total_nodes"] == 10
        assert data["task"] == "femnist"
        assert "token" in data
        print(f"   Registered: {data['node_id']} (index={data['node_index']})")

        # Register second node
        resp2 = client.post("/nodes/register", json={
            "task": "femnist",
            "role": "malicious_client",
            "display_name": "IntegrationAttacker",
            "attack_type": "sign_flip_amplified",
            "attack_scale": -5.0,
        })
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["node_index"] == 1
        print(f"   Registered: {data2['node_id']} (index={data2['node_index']})")

        # List nodes
        resp3 = client.get("/nodes")
        assert resp3.status_code == 200
        nodes_data = resp3.json()
        assert nodes_data["count"] == 2

        # List filtered by task
        resp4 = client.get("/nodes?task=shakespeare")
        assert resp4.status_code == 200
        assert resp4.json()["count"] == 0

        resp5 = client.get("/nodes?task=femnist")
        assert resp5.status_code == 200
        assert resp5.json()["count"] == 2

        # Register with invalid task
        resp6 = client.post("/nodes/register", json={
            "task": "invalid_task",
            "role": "legitimate_client",
            "display_name": "Bad",
        })
        assert resp6.status_code == 400

        # Health check should still work
        resp7 = client.get("/health")
        assert resp7.status_code == 200

        print("✅ Test 7 PASSED: FastAPI endpoints work correctly")
    finally:
        if os.path.exists(reg_path):
            os.unlink(reg_path)


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Dynamic Node Integration Tests")
    print("=" * 60)
    print()

    tests = [
        ("1. NodeRegistry basic", test_node_registry_basic),
        ("2. JWT tokens", test_jwt_tokens),
        ("3. Max nodes limit", test_max_nodes_limit),
        ("4. Persistence", test_persistence),
        ("5. Data partitioning", test_data_partitioning),
        ("6. End-to-end pipeline", test_end_to_end_pipeline),
        ("7. FastAPI endpoints", test_fastapi_endpoints),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for name, test_func in tests:
        print(f"\n--- {name} ---")
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {name} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)
