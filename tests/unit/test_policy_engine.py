"""Unit tests for PolicyEngine."""

import tempfile
from pathlib import Path
import pytest
from frognano_harness.models import DecisionType, RiskLevel, Task
from frognano_harness.policy_engine import PolicyEngine


@pytest.fixture
def workspace() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "src").mkdir()
        (root / ".env").write_text("SECRET=123", encoding="utf-8")
        yield root


def test_policy_allow_low_risk_reads(workspace: Path) -> None:
    pe = PolicyEngine(workspace)
    task = Task("T-001", "Task", "Obj", "Desc", allowed_files=("src/main.py",))

    decision = pe.evaluate_tool_request("read_file", {"path": "src/main.py"}, task)
    assert decision.decision == DecisionType.ALLOW
    assert decision.risk_level == RiskLevel.LOW


def test_policy_deny_path_traversal(workspace: Path) -> None:
    pe = PolicyEngine(workspace)
    task = Task("T-001", "Task", "Obj", "Desc", allowed_files=("src/main.py",))

    decision = pe.evaluate_tool_request("read_file", {"path": "../../windows/system32"}, task)
    assert decision.decision == DecisionType.DENY
    assert "traversal" in decision.reason.lower() or "boundary" in decision.reason.lower()


def test_policy_deny_secrets(workspace: Path) -> None:
    pe = PolicyEngine(workspace)
    task = Task("T-001", "Task", "Obj", "Desc", allowed_files=(".env",))

    decision = pe.evaluate_tool_request("read_file", {"path": ".env"}, task)
    assert decision.decision == DecisionType.DENY
    assert "secret" in decision.reason.lower() or "protected" in decision.reason.lower()


def test_policy_deny_files_outside_allowed_files(workspace: Path) -> None:
    pe = PolicyEngine(workspace)
    task = Task("T-001", "Task", "Obj", "Desc", allowed_files=("src/a.py",))

    decision = pe.evaluate_tool_request("write_file", {"path": "src/unauthorized.py", "content": "x"}, task)
    assert decision.decision == DecisionType.DENY
    assert "allowed_files" in decision.reason.lower()


def test_policy_require_approval_for_high_risk_commands(workspace: Path) -> None:
    pe = PolicyEngine(workspace)
    task = Task("T-001", "Task", "Obj", "Desc")

    # Unlisted or high-risk command
    decision = pe.evaluate_tool_request("run_command", {"command": "curl", "args": ["http://evil.com"]}, task)
    assert decision.decision == DecisionType.REQUIRE_APPROVAL
    assert decision.risk_level == RiskLevel.HIGH


def test_policy_deny_model_git_commit(workspace: Path) -> None:
    """Constitution Article IX: Model direct commits must be rejected unconditionally."""
    pe = PolicyEngine(workspace)
    task = Task("T-001", "Task", "Obj", "Desc")

    decision = pe.evaluate("git_commit", {"message": "unauthorized commit"}, task=task)
    assert decision.decision == DecisionType.DENY
    assert decision.policy_rule == "MODEL_GIT_COMMIT_PROHIBITED"
    assert "prohibited" in decision.reason.lower()
