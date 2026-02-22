# backend/tests/test_training_api.py — Integration tests for training REST API
"""
Covers:
  POST   /api/projects/{id}/training/start
  POST   /api/projects/{id}/training/pause
  POST   /api/projects/{id}/training/resume
  POST   /api/projects/{id}/training/reset
  GET    /api/projects/{id}/training/status
  PATCH  /api/projects/{id}/config
  POST   /api/projects/{id}/nodes/{nodeId}/block
  POST   /api/projects/{id}/nodes/{nodeId}/unblock
  POST   /api/projects/{id}/training/submit-update
  GET    /api/projects/{id}/export

Tier enforcement:
  - FREE users cannot use PRO-only aggregation methods
  - FREE users are capped at FREE_TIER_MAX_NODES
  - Export requires PRO + TEAM_LEAD

RBAC:
  - block/unblock require TEAM_LEAD role
"""

import json
import pytest

from tests.conftest import small_norm_weights_b64
from training.coordinator import get_coordinator, _coordinators


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _start(client, project, token):
    return client.post(
        f"/api/projects/{project.id}/training/start",
        headers=_auth(token),
    )


def _cancel_training(project_id: str):
    """Cancel any running coordinator task to avoid lingering background tasks."""
    coord = get_coordinator(project_id)
    if coord and coord._task and not coord._task.done():
        coord._task.cancel()


# ══════════════════════════════════════════════════════════════════════════════
# 1. Training Start
# ══════════════════════════════════════════════════════════════════════════════

class TestTrainingStart:

    def test_start_returns_200(self, client, project, lead_token):
        resp = _start(client, project, lead_token)
        assert resp.status_code == 200
        _cancel_training(project.id)

    def test_start_response_has_status_running(self, client, project, lead_token):
        resp = _start(client, project, lead_token)
        data = resp.json()
        assert data.get("status") in ("running", "already_running")
        _cancel_training(project.id)

    def test_start_creates_coordinator(self, client, project, lead_token):
        _start(client, project, lead_token)
        assert get_coordinator(project.id) is not None
        _cancel_training(project.id)

    def test_start_twice_returns_already_running(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = _start(client, project, lead_token)
        assert resp.status_code == 200
        assert resp.json()["status"] == "already_running"
        _cancel_training(project.id)

    def test_start_unauthenticated_returns_401(self, client, project):
        resp = client.post(f"/api/projects/{project.id}/training/start")
        assert resp.status_code == 401

    def test_start_missing_project_returns_404(self, client, lead_token):
        resp = client.post(
            "/api/projects/nonexistent-proj-id/training/start",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 2. Training Pause / Resume
# ══════════════════════════════════════════════════════════════════════════════

class TestPauseResume:

    def test_pause_returns_200(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/pause",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200
        _cancel_training(project.id)

    def test_pause_changes_status_to_paused(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/pause",
            headers=_auth(lead_token),
        )
        assert resp.json()["status"] == "paused"
        _cancel_training(project.id)

    def test_resume_after_pause(self, client, project, lead_token):
        _start(client, project, lead_token)
        client.post(
            f"/api/projects/{project.id}/training/pause",
            headers=_auth(lead_token),
        )
        resp = client.post(
            f"/api/projects/{project.id}/training/resume",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"
        _cancel_training(project.id)

    def test_resume_when_not_paused(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/resume",
            headers=_auth(lead_token),
        )
        # Should return current status (running) — not an error
        assert resp.status_code == 200
        _cancel_training(project.id)

    def test_pause_unauthenticated_returns_401(self, client, project):
        resp = client.post(f"/api/projects/{project.id}/training/pause")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 3. Training Reset
# ══════════════════════════════════════════════════════════════════════════════

class TestTrainingReset:

    def test_reset_returns_200(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/reset",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200

    def test_reset_sets_status_to_idle(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/reset",
            headers=_auth(lead_token),
        )
        data = resp.json()
        assert data["status"] == "idle"
        assert data["currentRound"] == 0

    def test_reset_without_start_still_works(self, client, project, lead_token):
        """Reset on idle coordinator should not error."""
        resp = client.post(
            f"/api/projects/{project.id}/training/reset",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# 4. Training Status
# ══════════════════════════════════════════════════════════════════════════════

class TestTrainingStatus:

    def test_status_before_start_returns_idle(self, client, project, lead_token):
        resp = client.get(
            f"/api/projects/{project.id}/training/status",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "idle"
        assert data["currentRound"] == 0

    def test_status_after_start_returns_running(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = client.get(
            f"/api/projects/{project.id}/training/status",
            headers=_auth(lead_token),
        )
        assert resp.json()["status"] == "running"
        _cancel_training(project.id)

    def test_status_after_pause_returns_paused(self, client, project, lead_token):
        _start(client, project, lead_token)
        client.post(
            f"/api/projects/{project.id}/training/pause",
            headers=_auth(lead_token),
        )
        resp = client.get(
            f"/api/projects/{project.id}/training/status",
            headers=_auth(lead_token),
        )
        assert resp.json()["status"] == "paused"
        _cancel_training(project.id)

    def test_status_unauthenticated_returns_401(self, client, project):
        resp = client.get(f"/api/projects/{project.id}/training/status")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 5. Config Update (PATCH /config)
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigUpdate:

    def test_update_aggregation_method_success(self, client, project, lead_token):
        resp = client.patch(
            f"/api/projects/{project.id}/config",
            json={"aggregationMethod": "fedavg"},
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200

    def test_update_sabd_alpha(self, client, project, lead_token):
        resp = client.patch(
            f"/api/projects/{project.id}/config",
            json={"sabdAlpha": 0.7},
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200

    def test_pro_method_blocked_for_free_user(self, client, project, free_user, free_token, db):
        """FREE users cannot select PRO-only aggregation methods."""
        from auth.settings import ENFORCE_TIER_RESTRICTIONS, PRO_ADVANCED_AGGREGATIONS
        if not ENFORCE_TIER_RESTRICTIONS:
            pytest.skip("Tier restrictions not enabled in this config")

        pro_method = next(iter(PRO_ADVANCED_AGGREGATIONS))
        resp = client.patch(
            f"/api/projects/{project.id}/config",
            json={"aggregationMethod": pro_method},
            headers=_auth(free_token),
        )
        assert resp.status_code == 403
        assert "Pro subscription" in resp.json()["detail"]

    def test_pro_user_can_use_advanced_method(self, client, project, lead_token):
        """PRO users can select advanced aggregation methods."""
        from auth.settings import PRO_ADVANCED_AGGREGATIONS
        if not PRO_ADVANCED_AGGREGATIONS:
            pytest.skip("No PRO aggregation methods configured")

        pro_method = next(iter(PRO_ADVANCED_AGGREGATIONS))
        resp = client.patch(
            f"/api/projects/{project.id}/config",
            json={"aggregationMethod": pro_method},
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200

    def test_config_update_missing_project(self, client, lead_token):
        resp = client.patch(
            "/api/projects/nonexistent/config",
            json={"aggregationMethod": "fedavg"},
            headers=_auth(lead_token),
        )
        assert resp.status_code == 404

    def test_config_update_persisted_to_coordinator(self, client, project, lead_token):
        """Config changes propagate to an active coordinator."""
        _start(client, project, lead_token)
        client.patch(
            f"/api/projects/{project.id}/config",
            json={"aggregationMethod": "fedavg"},
            headers=_auth(lead_token),
        )
        coord = get_coordinator(project.id)
        assert coord.config.get("aggregationMethod") == "fedavg"
        _cancel_training(project.id)


# ══════════════════════════════════════════════════════════════════════════════
# 6. Block / Unblock Node (RBAC: TEAM_LEAD only)
# ══════════════════════════════════════════════════════════════════════════════

class TestBlockUnblockNode:

    def _get_first_node_id(self, project) -> str:
        coord = get_coordinator(project.id)
        if coord and coord.node_manager.nodes:
            return next(iter(coord.node_manager.nodes))
        return "NODE_0"

    def test_block_requires_team_lead(self, client, project, free_token, lead_token):
        _start(client, project, lead_token)
        node_id = self._get_first_node_id(project)
        resp = client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/block",
            headers=_auth(free_token),
        )
        assert resp.status_code == 403
        _cancel_training(project.id)

    def test_block_node_success(self, client, project, lead_token):
        _start(client, project, lead_token)
        node_id = self._get_first_node_id(project)
        resp = client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/block",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodeId" in data
        _cancel_training(project.id)

    def test_block_no_active_training_returns_404(self, client, project, lead_token):
        resp = client.post(
            f"/api/projects/{project.id}/nodes/NODE_0/block",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 404

    def test_unblock_requires_team_lead(self, client, project, free_token, lead_token):
        _start(client, project, lead_token)
        node_id = self._get_first_node_id(project)
        # Block first
        client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/block",
            headers=_auth(lead_token),
        )
        # Try to unblock as free user
        resp = client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/unblock",
            headers=_auth(free_token),
        )
        assert resp.status_code == 403
        _cancel_training(project.id)

    def test_unblock_node_success(self, client, project, lead_token):
        _start(client, project, lead_token)
        node_id = self._get_first_node_id(project)
        client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/block",
            headers=_auth(lead_token),
        )
        resp = client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/unblock",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200
        _cancel_training(project.id)

    def test_block_unknown_node_returns_404(self, client, project, lead_token):
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/nodes/GHOST_NODE_9999/block",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 404
        _cancel_training(project.id)

    def test_block_creates_notification(self, client, project, lead_token, db):
        _start(client, project, lead_token)
        node_id = self._get_first_node_id(project)
        client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/block",
            headers=_auth(lead_token),
        )
        from db.models import Notification
        notifs = db.query(Notification).filter_by(project_id=project.id).all()
        assert len(notifs) >= 1
        _cancel_training(project.id)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Submit Gradient Update (HTTP POST contributor flow)
# ══════════════════════════════════════════════════════════════════════════════

class TestSubmitGradientUpdate:

    def test_submit_update_success(self, client, project, lead_token, membership):
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/submit-update",
            json={
                "nodeId": "NODE_T1",
                "gradients": {"layer1": [0.1, 0.2, 0.3]},
                "dataSize": 100,
            },
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert "l2Norm" in data
        assert "clippedNorm" in data
        assert "clipFactor" in data
        _cancel_training(project.id)

    def test_submit_update_not_member_returns_403(self, client, project, lead_token):
        """User without project membership should be rejected."""
        # lead_user has no membership in this test (membership fixture not used)
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/submit-update",
            json={"nodeId": "NODE_T1", "gradients": {"layer1": [0.1]}, "dataSize": 10},
            headers=_auth(lead_token),
        )
        assert resp.status_code == 403
        _cancel_training(project.id)

    def test_submit_update_without_active_training(self, client, project, lead_token, membership):
        resp = client.post(
            f"/api/projects/{project.id}/training/submit-update",
            json={"nodeId": "NODE_T1", "gradients": {"layer1": [0.1]}, "dataSize": 10},
            headers=_auth(lead_token),
        )
        assert resp.status_code == 400

    def test_submit_update_trust_data_not_in_response(self, client, project, lead_token, membership):
        """Trust scores and SABD data must NOT be returned to contributors."""
        _start(client, project, lead_token)
        resp = client.post(
            f"/api/projects/{project.id}/training/submit-update",
            json={"nodeId": "NODE_T1", "gradients": {"layer1": [0.01, 0.02]}, "dataSize": 50},
            headers=_auth(lead_token),
        )
        data = resp.json()
        # These internal fields must be absent
        assert "trust" not in data
        assert "sabd" not in data
        assert "cosine_distance" not in data
        assert "trustScore" not in data
        _cancel_training(project.id)

    def test_submit_update_unauthenticated_returns_401(self, client, project):
        resp = client.post(
            f"/api/projects/{project.id}/training/submit-update",
            json={"nodeId": "NODE_T1", "gradients": {}, "dataSize": 0},
        )
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 8. Export Metrics (PRO + TEAM_LEAD only)
# ══════════════════════════════════════════════════════════════════════════════

class TestExportMetrics:

    def test_export_requires_pro_team_lead(self, client, project, lead_token):
        """PRO TEAM_LEAD can export."""
        resp = client.get(
            f"/api/projects/{project.id}/export",
            headers=_auth(lead_token),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_export_blocked_for_free_user(self, client, project, free_token):
        """FREE user should be blocked (403) when tier restrictions are on."""
        from auth.settings import ENFORCE_TIER_RESTRICTIONS
        if not ENFORCE_TIER_RESTRICTIONS:
            pytest.skip("Tier restrictions not enabled")
        resp = client.get(
            f"/api/projects/{project.id}/export",
            headers=_auth(free_token),
        )
        assert resp.status_code == 403

    def test_export_empty_before_training(self, client, project, lead_token):
        resp = client.get(
            f"/api/projects/{project.id}/export",
            headers=_auth(lead_token),
        )
        assert resp.json() == []

    def test_export_unauthenticated_returns_401(self, client, project):
        resp = client.get(f"/api/projects/{project.id}/export")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 9. Free-Tier Node Cap
# ══════════════════════════════════════════════════════════════════════════════

class TestFreeTierNodeCap:

    def test_free_tier_capped_at_max_nodes(self, client, db, free_user, free_token):
        """FREE users: numClients > FREE_TIER_MAX_NODES is clamped silently."""
        from auth.settings import ENFORCE_TIER_RESTRICTIONS, FREE_TIER_MAX_NODES
        if not ENFORCE_TIER_RESTRICTIONS:
            pytest.skip("Tier restrictions not enabled")

        from db.models import Project as ProjectModel
        big_project = ProjectModel(
            name="Big Project",
            description="",
            created_by=free_user.id,
            config={"numClients": FREE_TIER_MAX_NODES + 5, "numRounds": 2},
        )
        db.add(big_project)
        db.commit()
        db.refresh(big_project)

        resp = client.post(
            f"/api/projects/{big_project.id}/training/start",
            headers=_auth(free_token),
        )
        assert resp.status_code == 200

        coord = get_coordinator(big_project.id)
        # Coordinator's config must have numClients clamped
        assert coord.config.get("numClients") <= FREE_TIER_MAX_NODES
        _cancel_training(big_project.id)


# ══════════════════════════════════════════════════════════════════════════════
# 10. Activity Log
# ══════════════════════════════════════════════════════════════════════════════

class TestActivityLog:

    def test_start_creates_activity_log(self, client, project, lead_token, db):
        _start(client, project, lead_token)
        from db.models import ActivityLog
        logs = db.query(ActivityLog).filter_by(project_id=project.id).all()
        assert len(logs) >= 1
        _cancel_training(project.id)

    def test_block_node_creates_activity_log(self, client, project, lead_token, db):
        _start(client, project, lead_token)
        node_id = next(iter(get_coordinator(project.id).node_manager.nodes))
        client.post(
            f"/api/projects/{project.id}/nodes/{node_id}/block",
            headers=_auth(lead_token),
        )
        from db.models import ActivityLog
        logs = db.query(ActivityLog).filter_by(project_id=project.id, type="block").all()
        assert len(logs) >= 1
        _cancel_training(project.id)
