"""Unit tests for HumanApprovalManager."""

import tempfile
from pathlib import Path
import pytest
from frognano_harness.approval_manager import HumanApprovalManager
from frognano_harness.models import ApprovalStatus, RiskLevel
from frognano_harness.state_manager import StateManager


@pytest.fixture
def temp_db() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / ".harness" / "state.db"


def test_create_and_resolve_approval(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    am = HumanApprovalManager(sm)

    req = am.create_approval_request(
        tool_call_id="TC-101",
        task_id="T-001",
        operation="run_command",
        exact_arguments={"command": "pip", "args": ["install", "pytest"]},
        risk_level=RiskLevel.HIGH,
    )

    assert req.status == ApprovalStatus.PENDING
    assert req.approval_id.startswith("APP-")

    # Fetch pending
    pending = am.list_pending_approvals()
    assert len(pending) == 1
    assert pending[0].approval_id == req.approval_id

    # Approve
    approved = am.approve_request(req.approval_id, resolved_by="test-user")
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.resolved_by == "test-user"

    # Pending list now empty
    assert len(am.list_pending_approvals()) == 0


def test_reject_approval(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    am = HumanApprovalManager(sm)

    req = am.create_approval_request(
        tool_call_id="TC-102",
        task_id="T-001",
        operation="delete_file",
        exact_arguments={"path": "main.py"},
        risk_level=RiskLevel.HIGH,
    )

    rejected = am.reject_request(req.approval_id, reason="Not authorized", resolved_by="test-user")
    assert rejected.status == ApprovalStatus.REJECTED
