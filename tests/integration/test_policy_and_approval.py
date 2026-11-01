"""Integration test for policy authorization and approval workflow."""

import tempfile
from pathlib import Path
from frognano_harness.approval_manager import HumanApprovalManager
from frognano_harness.models import ApprovalStatus, DecisionType, RiskLevel, Task
from frognano_harness.policy_engine import PolicyEngine
from frognano_harness.state_manager import StateManager


def test_end_to_end_policy_and_approval() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        db_path = workspace / ".harness" / "state.db"

        pe = PolicyEngine(workspace)
        sm = StateManager(db_path)
        am = HumanApprovalManager(sm)

        task = Task("T-001", "Task", "Obj", "Desc", allowed_files=("src/app.py",))

        # 1. Allowed operation
        dec1 = pe.evaluate_tool_request("write_file", {"path": "src/app.py", "content": "x=1"}, task)
        assert dec1.decision == DecisionType.ALLOW

        # 2. Denied operation (boundary escape)
        dec2 = pe.evaluate_tool_request("read_file", {"path": "../../secret.txt"}, task)
        assert dec2.decision == DecisionType.DENY

        # 3. Require approval operation
        dec3 = pe.evaluate_tool_request("run_command", {"command": "npm", "args": ["install"]}, task)
        assert dec3.decision == DecisionType.REQUIRE_APPROVAL
        assert dec3.risk_level == RiskLevel.HIGH

        # Create approval hold
        app_req = am.create_approval_request(
            tool_call_id="TC-001",
            task_id=task.task_id,
            operation="run_command",
            exact_arguments={"command": "npm", "args": ["install"]},
            risk_level=dec3.risk_level,
        )
        assert app_req.status == ApprovalStatus.PENDING

        # Resolve via approval manager
        approved = am.approve_request(app_req.approval_id, resolved_by="admin")
        assert approved.status == ApprovalStatus.APPROVED
        assert len(am.list_pending_approvals()) == 0
