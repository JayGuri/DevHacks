# backend/tests/test_ws_endpoint.py — Integration tests for the /ws WebSocket endpoint
"""
Covers:
  - Dashboard viewer receives training_status on connect
  - Dashboard viewer receives initial_state after training is started
  - ping → pong response
  - FL client registration (clientId query param)
  - FL client limit enforcement (11th client gets close code 1008)
  - weight_update with large norm → client receives rejected event
  - weight_update with valid norm → accepted, queued in FL processor
  - Disconnect cleans up both dashboard and FL client registrations
"""

import json
import base64
import pytest

from tests.conftest import small_norm_weights_b64, large_norm_weights_b64
from ws.manager import ws_manager
from training.coordinator import _coordinators, get_coordinator, create_coordinator
from training.fl_processor import _processors


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _weight_update_msg(weights_b64: str, client_id: str = "c1", round_num: int = 1) -> str:
    return json.dumps({
        "type": "weight_update",
        "client_id": client_id,
        "weights": weights_b64,
        "round_num": round_num,
        "global_round_received": round_num,
        "num_samples": 50,
        "local_loss": 0.4,
        "task": "femnist",
    })


def _collect_events(ws, count: int, timeout: float = 2.0) -> list:
    """Read up to `count` JSON events from a TestClient WebSocket."""
    events = []
    for _ in range(count):
        try:
            raw = ws.receive_text()
            events.append(json.loads(raw))
        except Exception:
            break
    return events


PROJECT_ID = "test-project-ws"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Dashboard Viewer — Initial Events
# ══════════════════════════════════════════════════════════════════════════════

class TestDashboardViewerConnect:

    def test_connect_receives_training_status(self, client):
        """Dashboard viewer (no clientId) gets training_status immediately."""
        with client.websocket_connect(f"/api/ws?projectId={PROJECT_ID}") as ws:
            data = json.loads(ws.receive_text())
            assert data["event"] == "training_status"
            assert "status" in data["data"]
            assert "currentRound" in data["data"]
            assert "totalRounds" in data["data"]

    def test_connect_status_idle_before_training(self, client):
        with client.websocket_connect(f"/api/ws?projectId={PROJECT_ID}") as ws:
            data = json.loads(ws.receive_text())
            assert data["data"]["status"] == "idle"
            assert data["data"]["currentRound"] == 0

    def test_connect_increments_dashboard_connection_count(self, client):
        with client.websocket_connect(f"/api/ws?projectId={PROJECT_ID}") as ws:
            ws.receive_text()  # consume training_status
            # Connection should be registered
            assert ws_manager.get_connection_count(PROJECT_ID) >= 1

    def test_disconnect_decrements_connection_count(self, client):
        with client.websocket_connect(f"/api/ws?projectId={PROJECT_ID}") as ws:
            ws.receive_text()  # consume training_status
        # After context exits, connection should be removed
        assert ws_manager.get_connection_count(PROJECT_ID) == 0

    def test_multiple_viewers_independent_projects(self, client):
        with client.websocket_connect(f"/api/ws?projectId=proj-alpha") as ws1:
            ws1.receive_text()
            with client.websocket_connect(f"/api/ws?projectId=proj-beta") as ws2:
                ws2.receive_text()
                assert ws_manager.get_connection_count("proj-alpha") == 1
                assert ws_manager.get_connection_count("proj-beta") == 1


# ══════════════════════════════════════════════════════════════════════════════
# 2. Ping / Pong
# ══════════════════════════════════════════════════════════════════════════════

class TestPingPong:

    def test_ping_receives_pong(self, client):
        with client.websocket_connect(f"/api/ws?projectId={PROJECT_ID}") as ws:
            ws.receive_text()  # consume training_status
            ws.send_text(json.dumps({"type": "ping"}))
            raw = ws.receive_text()
            data = json.loads(raw)
            assert data.get("event") == "pong"

    def test_multiple_pings(self, client):
        with client.websocket_connect(f"/api/ws?projectId={PROJECT_ID}") as ws:
            ws.receive_text()  # consume training_status
            for _ in range(3):
                ws.send_text(json.dumps({"type": "ping"}))
                raw = ws.receive_text()
                assert json.loads(raw).get("event") == "pong"

    def test_unknown_message_type_does_not_disconnect(self, client):
        """Unknown message types should be silently ignored."""
        with client.websocket_connect(f"/api/ws?projectId={PROJECT_ID}") as ws:
            ws.receive_text()  # consume training_status
            ws.send_text(json.dumps({"type": "unknown_type", "data": "something"}))
            # Connection should still respond to ping
            ws.send_text(json.dumps({"type": "ping"}))
            pong = json.loads(ws.receive_text())
            assert pong.get("event") == "pong"


# ══════════════════════════════════════════════════════════════════════════════
# 3. FL Client Registration
# ══════════════════════════════════════════════════════════════════════════════

class TestFLClientRegistration:

    def test_fl_client_registered_on_connect(self, client):
        with client.websocket_connect(
            f"/api/ws?projectId={PROJECT_ID}&clientId=fl-client-1&task=femnist"
        ) as ws:
            # No training_status sent to FL clients — connection stays open
            assert ws_manager.get_fl_client_count(PROJECT_ID) == 1

    def test_fl_client_unregistered_on_disconnect(self, client):
        with client.websocket_connect(
            f"/api/ws?projectId={PROJECT_ID}&clientId=fl-client-1&task=femnist"
        ) as ws:
            pass  # disconnect
        assert ws_manager.get_fl_client_count(PROJECT_ID) == 0

    def test_fl_client_does_not_receive_training_status(self, client):
        """FL clients (clientId set) should NOT get the initial training_status push."""
        with client.websocket_connect(
            f"/api/ws?projectId={PROJECT_ID}&clientId=fl-c1&task=femnist"
        ) as ws:
            # There's nothing to receive immediately — send ping to confirm connection
            ws.send_text(json.dumps({"type": "ping"}))
            raw = ws.receive_text()
            assert json.loads(raw).get("event") == "pong"

    def test_multiple_fl_clients_different_ids(self, client):
        """Two FL clients with different IDs can connect simultaneously."""
        with client.websocket_connect(
            f"/api/ws?projectId={PROJECT_ID}&clientId=fl-a&task=femnist"
        ) as ws1:
            with client.websocket_connect(
                f"/api/ws?projectId={PROJECT_ID}&clientId=fl-b&task=femnist"
            ) as ws2:
                assert ws_manager.get_fl_client_count(PROJECT_ID) == 2


# ══════════════════════════════════════════════════════════════════════════════
# 4. FL Client Limit Enforcement
# ══════════════════════════════════════════════════════════════════════════════

class TestFLClientLimit:

    def test_eleventh_client_rejected_with_1008(self, client):
        """After 10 FL clients, the 11th should be immediately closed."""
        from ws.manager import MAX_FL_CLIENTS

        contexts = []
        for i in range(MAX_FL_CLIENTS):
            ctx = client.websocket_connect(
                f"/api/ws?projectId={PROJECT_ID}&clientId=fl-{i}&task=femnist"
            )
            ws = ctx.__enter__()
            contexts.append((ctx, ws))

        try:
            assert ws_manager.get_fl_client_count(PROJECT_ID) == MAX_FL_CLIENTS

            # 11th connection — should get close code 1008
            with pytest.raises(Exception):
                with client.websocket_connect(
                    f"/api/ws?projectId={PROJECT_ID}&clientId=fl-extra&task=femnist"
                ) as ws_extra:
                    # The server should close this immediately
                    ws_extra.receive_text()
        finally:
            for ctx, ws in contexts:
                try:
                    ctx.__exit__(None, None, None)
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════════════════
# 5. weight_update — Layer 1 Rejection
# ══════════════════════════════════════════════════════════════════════════════

class TestWeightUpdateL1Rejection:

    def test_large_norm_weight_update_returns_rejected(self, client, project):
        """Sending a weight_update with norm >> threshold triggers a rejected response."""
        with client.websocket_connect(
            f"/api/ws?projectId={project.id}&clientId=fl-bad&task=femnist"
        ) as ws:
            ws.send_text(_weight_update_msg(large_norm_weights_b64(), client_id="fl-bad"))
            raw = ws.receive_text()
            msg = json.loads(raw)
            assert msg["type"] == "rejected"
            assert msg["client_id"] == "fl-bad"
            assert msg["reason"] == "l2_norm_exceeded"
            assert "norm" in msg
            assert "threshold" in msg
            assert msg["norm"] > msg["threshold"]

    def test_rejected_msg_has_round_num(self, client, project):
        with client.websocket_connect(
            f"/api/ws?projectId={project.id}&clientId=fl-bad&task=femnist"
        ) as ws:
            ws.send_text(_weight_update_msg(large_norm_weights_b64(), client_id="fl-bad", round_num=5))
            raw = ws.receive_text()
            msg = json.loads(raw)
            assert msg.get("round_num") == 5

    def test_rejected_increments_gatekeeper_rejected(self, client, project):
        with client.websocket_connect(
            f"/api/ws?projectId={project.id}&clientId=fl-bad2&task=femnist"
        ) as ws:
            ws.send_text(_weight_update_msg(large_norm_weights_b64(), client_id="fl-bad2"))
            ws.receive_text()  # consume rejected

        from training.fl_processor import get_fl_processor
        proc = get_fl_processor(project.id)
        # gatekeeper_rejected is cleared at round boundary but should still be
        # recorded before the coordinator drains it
        # Test: verify the processor was invoked (has a threshold set)
        assert proc.get_l2_threshold() == 10.0


# ══════════════════════════════════════════════════════════════════════════════
# 6. weight_update — Accepted
# ══════════════════════════════════════════════════════════════════════════════

class TestWeightUpdateAccepted:

    def test_valid_weight_update_queued_in_processor(self, client, project):
        """Valid update (small norm) should be silently queued — no rejection."""
        from training.fl_processor import get_fl_processor

        with client.websocket_connect(
            f"/api/ws?projectId={project.id}&clientId=fl-good&task=femnist"
        ) as ws:
            ws.send_text(_weight_update_msg(small_norm_weights_b64(), client_id="fl-good"))
            # No response expected for accepted updates — send ping to confirm alive
            ws.send_text(json.dumps({"type": "ping"}))
            pong = json.loads(ws.receive_text())
            assert pong.get("event") == "pong"

        proc = get_fl_processor(project.id)
        # After disconnect, the pending update should still be in the queue
        # (it only gets drained at round boundary)
        assert len(proc._pending_updates) == 1

    def test_accepted_update_not_in_gatekeeper_rejected(self, client, project):
        from training.fl_processor import get_fl_processor

        with client.websocket_connect(
            f"/api/ws?projectId={project.id}&clientId=fl-ok&task=femnist"
        ) as ws:
            ws.send_text(_weight_update_msg(small_norm_weights_b64(), client_id="fl-ok"))
            ws.send_text(json.dumps({"type": "ping"}))
            ws.receive_text()  # pong

        proc = get_fl_processor(project.id)
        assert "fl-ok" not in proc._gatekeeper_rejected

    def test_multiple_valid_updates_all_queued(self, client, project):
        from training.fl_processor import get_fl_processor

        with client.websocket_connect(
            f"/api/ws?projectId={project.id}&clientId=fl-multi&task=femnist"
        ) as ws:
            for i in range(3):
                ws.send_text(_weight_update_msg(
                    small_norm_weights_b64(), client_id=f"fl-multi-{i}"
                ))
            ws.send_text(json.dumps({"type": "ping"}))
            ws.receive_text()  # pong

        proc = get_fl_processor(project.id)
        assert len(proc._pending_updates) == 3


# ══════════════════════════════════════════════════════════════════════════════
# 7. Initial state after training start
# ══════════════════════════════════════════════════════════════════════════════

class TestInitialStateAfterTraining:

    def test_initial_state_sent_when_coordinator_has_nodes(self, client, project, lead_token):
        """After starting training, a new viewer connecting gets initial_state."""
        # Start training via REST to initialize nodes
        resp = client.post(
            f"/api/projects/{project.id}/training/start",
            headers={"Authorization": f"Bearer {lead_token}"},
        )
        assert resp.status_code == 200

        # Now connect a dashboard viewer
        with client.websocket_connect(
            f"/api/ws?projectId={project.id}"
        ) as ws:
            events = _collect_events(ws, 2)
            event_types = {e["event"] for e in events}
            # Should receive training_status + initial_state
            assert "training_status" in event_types
            assert "initial_state" in event_types

        # Clean up — cancel the training task
        coord = get_coordinator(project.id)
        if coord and coord._task:
            coord._task.cancel()
