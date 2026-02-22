# backend/tests/test_ws_manager.py — Unit tests for ConnectionManager
"""
Covers:
  - Dashboard connection lifecycle (connect, disconnect, broadcast)
  - Broadcast with dead connections (auto-cleanup)
  - send_personal
  - get_connection_count
  - FL client registration (success, MAX_FL_CLIENTS enforcement)
  - FL client unregistration
  - send_to_fl_client (success, missing client, send failure)
  - get_fl_client_count
"""

import asyncio
import json
import pytest

from ws.manager import ConnectionManager, MAX_FL_CLIENTS


# ──────────────────────────────────────────────────────────────────────────────
# Mock WebSocket
# ──────────────────────────────────────────────────────────────────────────────

class MockWebSocket:
    """Minimal WebSocket double that records sent text and can simulate errors."""

    def __init__(self, fail_on_send: bool = False):
        self.sent: list[str] = []
        self._fail_on_send = fail_on_send
        self.closed = False

    async def accept(self):
        pass

    async def send_text(self, text: str):
        if self._fail_on_send:
            raise ConnectionError("simulated send failure")
        self.sent.append(text)

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True

    def last_event(self) -> dict:
        return json.loads(self.sent[-1])

    def all_events(self) -> list:
        return [json.loads(s) for s in self.sent]


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mgr():
    return ConnectionManager()


PROJECT = "proj-abc"
OTHER_PROJECT = "proj-xyz"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Dashboard connection lifecycle
# ══════════════════════════════════════════════════════════════════════════════

class TestDashboardConnections:

    @pytest.mark.asyncio
    async def test_connect_registers_websocket(self, mgr):
        ws = MockWebSocket()
        await mgr.connect(ws, PROJECT)
        assert mgr.get_connection_count(PROJECT) == 1

    @pytest.mark.asyncio
    async def test_multiple_connects_same_project(self, mgr):
        ws1, ws2 = MockWebSocket(), MockWebSocket()
        await mgr.connect(ws1, PROJECT)
        await mgr.connect(ws2, PROJECT)
        assert mgr.get_connection_count(PROJECT) == 2

    @pytest.mark.asyncio
    async def test_connections_isolated_by_project(self, mgr):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await mgr.connect(ws1, PROJECT)
        await mgr.connect(ws2, OTHER_PROJECT)
        assert mgr.get_connection_count(PROJECT) == 1
        assert mgr.get_connection_count(OTHER_PROJECT) == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self, mgr):
        ws = MockWebSocket()
        await mgr.connect(ws, PROJECT)
        await mgr.disconnect(ws, PROJECT)
        assert mgr.get_connection_count(PROJECT) == 0

    @pytest.mark.asyncio
    async def test_disconnect_last_removes_project_key(self, mgr):
        ws = MockWebSocket()
        await mgr.connect(ws, PROJECT)
        await mgr.disconnect(ws, PROJECT)
        assert PROJECT not in mgr._connections

    @pytest.mark.asyncio
    async def test_disconnect_unknown_project_safe(self, mgr):
        ws = MockWebSocket()
        await mgr.disconnect(ws, "nonexistent")  # must not raise

    @pytest.mark.asyncio
    async def test_get_connection_count_zero_for_unknown(self, mgr):
        assert mgr.get_connection_count("unknown-project") == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. Broadcast
# ══════════════════════════════════════════════════════════════════════════════

class TestBroadcast:

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_connections(self, mgr):
        ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
        await mgr.connect(ws1, PROJECT)
        await mgr.connect(ws2, PROJECT)
        await mgr.connect(ws3, PROJECT)
        await mgr.broadcast(PROJECT, "test_event", {"key": "value"})
        for ws in (ws1, ws2, ws3):
            assert len(ws.sent) == 1
            event = ws.last_event()
            assert event["event"] == "test_event"
            assert event["data"]["key"] == "value"
            assert event["projectId"] == PROJECT

    @pytest.mark.asyncio
    async def test_broadcast_skips_other_projects(self, mgr):
        ws_a = MockWebSocket()
        ws_b = MockWebSocket()
        await mgr.connect(ws_a, PROJECT)
        await mgr.connect(ws_b, OTHER_PROJECT)
        await mgr.broadcast(PROJECT, "ev", {})
        assert len(ws_a.sent) == 1
        assert len(ws_b.sent) == 0

    @pytest.mark.asyncio
    async def test_broadcast_no_connections_is_safe(self, mgr):
        # Must not raise when no clients connected
        await mgr.broadcast("empty-project", "ev", {})

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self, mgr):
        ws_good = MockWebSocket()
        ws_dead = MockWebSocket(fail_on_send=True)
        await mgr.connect(ws_good, PROJECT)
        await mgr.connect(ws_dead, PROJECT)
        await mgr.broadcast(PROJECT, "ev", {})
        # Dead ws should be removed
        assert ws_dead not in mgr._connections.get(PROJECT, set())
        # Good ws still gets the message
        assert len(ws_good.sent) == 1

    @pytest.mark.asyncio
    async def test_broadcast_json_structure(self, mgr):
        ws = MockWebSocket()
        await mgr.connect(ws, PROJECT)
        await mgr.broadcast(PROJECT, "round_complete", {"round": 1, "accuracy": 0.9})
        parsed = ws.last_event()
        assert parsed["event"] == "round_complete"
        assert parsed["projectId"] == PROJECT
        assert parsed["data"]["round"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 3. send_personal
# ══════════════════════════════════════════════════════════════════════════════

class TestSendPersonal:

    @pytest.mark.asyncio
    async def test_send_personal_delivers_event(self, mgr):
        ws = MockWebSocket()
        await mgr.send_personal(ws, "training_status", {"status": "running"})
        assert len(ws.sent) == 1
        parsed = ws.last_event()
        assert parsed["event"] == "training_status"
        assert parsed["data"]["status"] == "running"

    @pytest.mark.asyncio
    async def test_send_personal_dead_socket_does_not_raise(self, mgr):
        ws = MockWebSocket(fail_on_send=True)
        await mgr.send_personal(ws, "ev", {})  # must not propagate exception


# ══════════════════════════════════════════════════════════════════════════════
# 4. FL Client Registration
# ══════════════════════════════════════════════════════════════════════════════

class TestFLClientRegistration:

    @pytest.mark.asyncio
    async def test_register_returns_true_on_success(self, mgr):
        ws = MockWebSocket()
        result = await mgr.register_fl_client("c1", PROJECT, ws)
        assert result is True

    @pytest.mark.asyncio
    async def test_register_increments_count(self, mgr):
        for i in range(3):
            ws = MockWebSocket()
            await mgr.register_fl_client(f"c{i}", PROJECT, ws)
        assert mgr.get_fl_client_count(PROJECT) == 3

    @pytest.mark.asyncio
    async def test_register_limit_exactly_at_max(self, mgr):
        for i in range(MAX_FL_CLIENTS):
            ws = MockWebSocket()
            ok = await mgr.register_fl_client(f"c{i}", PROJECT, ws)
            assert ok is True
        assert mgr.get_fl_client_count(PROJECT) == MAX_FL_CLIENTS

    @pytest.mark.asyncio
    async def test_register_returns_false_when_limit_exceeded(self, mgr):
        for i in range(MAX_FL_CLIENTS):
            await mgr.register_fl_client(f"c{i}", PROJECT, MockWebSocket())
        ws_extra = MockWebSocket()
        result = await mgr.register_fl_client("c_extra", PROJECT, ws_extra)
        assert result is False

    @pytest.mark.asyncio
    async def test_register_limits_are_per_project(self, mgr):
        for i in range(MAX_FL_CLIENTS):
            await mgr.register_fl_client(f"c{i}", PROJECT, MockWebSocket())
        # A different project should still accept
        ws = MockWebSocket()
        result = await mgr.register_fl_client("c0", OTHER_PROJECT, ws)
        assert result is True

    @pytest.mark.asyncio
    async def test_get_fl_client_count_zero_for_unknown(self, mgr):
        assert mgr.get_fl_client_count("unknown") == 0


# ══════════════════════════════════════════════════════════════════════════════
# 5. FL Client Unregistration
# ══════════════════════════════════════════════════════════════════════════════

class TestFLClientUnregistration:

    @pytest.mark.asyncio
    async def test_unregister_decrements_count(self, mgr):
        ws = MockWebSocket()
        await mgr.register_fl_client("c1", PROJECT, ws)
        await mgr.unregister_fl_client("c1", PROJECT)
        assert mgr.get_fl_client_count(PROJECT) == 0

    @pytest.mark.asyncio
    async def test_unregister_last_removes_project_key(self, mgr):
        ws = MockWebSocket()
        await mgr.register_fl_client("c1", PROJECT, ws)
        await mgr.unregister_fl_client("c1", PROJECT)
        assert PROJECT not in mgr._fl_clients

    @pytest.mark.asyncio
    async def test_unregister_unknown_client_safe(self, mgr):
        await mgr.unregister_fl_client("ghost", PROJECT)  # must not raise

    @pytest.mark.asyncio
    async def test_unregister_frees_slot_for_new_client(self, mgr):
        # Fill to limit
        for i in range(MAX_FL_CLIENTS):
            await mgr.register_fl_client(f"c{i}", PROJECT, MockWebSocket())
        # Unregister one
        await mgr.unregister_fl_client("c0", PROJECT)
        # New client should now fit
        result = await mgr.register_fl_client("new_client", PROJECT, MockWebSocket())
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# 6. send_to_fl_client
# ══════════════════════════════════════════════════════════════════════════════

class TestSendToFLClient:

    @pytest.mark.asyncio
    async def test_send_success_returns_true(self, mgr):
        ws = MockWebSocket()
        await mgr.register_fl_client("c1", PROJECT, ws)
        result = await mgr.send_to_fl_client("c1", PROJECT, {"type": "rejected"})
        assert result is True
        assert len(ws.sent) == 1

    @pytest.mark.asyncio
    async def test_sent_payload_is_json(self, mgr):
        ws = MockWebSocket()
        await mgr.register_fl_client("c1", PROJECT, ws)
        await mgr.send_to_fl_client("c1", PROJECT, {"type": "rejected", "norm": 15.5})
        parsed = json.loads(ws.sent[0])
        assert parsed["type"] == "rejected"
        assert parsed["norm"] == 15.5

    @pytest.mark.asyncio
    async def test_send_missing_client_returns_false(self, mgr):
        result = await mgr.send_to_fl_client("ghost", PROJECT, {})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_missing_project_returns_false(self, mgr):
        result = await mgr.send_to_fl_client("c1", "nonexistent-project", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_failure_returns_false(self, mgr):
        ws = MockWebSocket(fail_on_send=True)
        await mgr.register_fl_client("c1", PROJECT, ws)
        result = await mgr.send_to_fl_client("c1", PROJECT, {"type": "test"})
        assert result is False
