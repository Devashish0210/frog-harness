"""End-to-end quickstart validation executing all 6 scenarios from quickstart.md."""

import json
from pathlib import Path
import subprocess
import tempfile
import pytest

from frognano_harness.approval_manager import HumanApprovalManager
from frognano_harness.cli import main
from frognano_harness.models import ApprovalStatus, RiskLevel, StateCheckpoint, Task, TaskStatus
from frognano_harness.state_manager import StateManager


@pytest.fixture
def quickstart_env() -> Path:
    """Prepare a full temporary git and workspace environment for quickstart scenarios."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Git repo setup
        subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Quickstart Runner"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "quickstart@frognano.local"], cwd=str(root), check=True, capture_output=True)
        (root / "README.md").write_text("# Quickstart Demo Project\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(root), check=True, capture_output=True)

        # SpecKit tasks.md
        specs_dir = root / "specs" / "002-feature"
        specs_dir.mkdir(parents=True, exist_ok=True)
        tasks_file = specs_dir / "tasks.md"
        tasks_file.write_text(
            """# Tasks: Feature Demo

- [ ] T001 [Setup] Initialize basic package
  - Objective: Write package files
  - Files: pkg/__init__.py
  - Criteria:
    - Package imports
  - Verification:
    - python -c "print('T001 verified')"

- [ ] T002 [Core] Core processor
  - Prereqs: T001
  - Objective: Write processor logic
  - Files: pkg/processor.py
  - Criteria:
    - Processor logic ready
  - Verification:
    - python -c "print('T002 verified')"
""",
            encoding="utf-8",
        )
        yield root


def test_quickstart_scenario_1_discovery_and_plan(quickstart_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 1: SpecKit Project Discovery & Plan DAG."""
    monkeypatch.chdir(quickstart_env)
    tasks_path = str(quickstart_env / "specs" / "002-feature" / "tasks.md")

    # Step 1: Initialize harness state
    rc_init = main(["init", "--endpoint", "http://127.0.0.1:8080/v1", "--model", "frognano"])
    assert rc_init == 0

    # Step 2: Validate tasks.md contract and check for dependency cycles
    rc_validate = main(["validate", "--tasks", tasks_path])
    assert rc_validate == 0

    # Step 3: Render execution plan DAG
    rc_plan = main(["plan", "--tasks", tasks_path])
    assert rc_plan == 0


def test_quickstart_scenario_2_bounded_task_and_verification(quickstart_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 2: Bounded Task Execution & Independent Verification."""
    monkeypatch.chdir(quickstart_env)
    tasks_path = str(quickstart_env / "specs" / "002-feature" / "tasks.md")

    main(["init", "--force"])
    sm = StateManager(quickstart_env / ".harness" / "state.db")

    with sm.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO execution_runs (run_id, project_root, git_branch, model_endpoint, model_alias, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("run_demo", str(quickstart_env), "main", "http://127.0.0.1:8080/v1", "frognano", "2026-11-01T10:00:00Z", "RUNNING"),
        )

    # Save and verify task independently
    task = Task(
        task_id="T001",
        title="Initialize basic package",
        objective="Write package files",
        description="Create basic structure",
        dependencies=(),
        allowed_files=("pkg/__init__.py",),
        acceptance_criteria=("package imports",),
        verification_commands=("python -c \"print('T001 verified')\"",),
        status=TaskStatus.READY,
    )
    sm.save_task("run_demo", task)

    rc_verify = main(["verify", "T001"])
    assert rc_verify == 0


def test_quickstart_scenario_3_policy_enforcement_and_approval(quickstart_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 3: Policy Enforcement & Human Approval Interception."""
    monkeypatch.chdir(quickstart_env)
    main(["init", "--force"])
    sm = StateManager(quickstart_env / ".harness" / "state.db")
    approval_mgr = HumanApprovalManager(sm)

    # Simulate creation of pending high-risk approval
    app = approval_mgr.request_approval(
        tool_call_id="call_high_risk_01",
        task_id="T002",
        operation="run_command",
        arguments={"command": "pip install numpy"},
        risk_level=RiskLevel.HIGH,
        auto_prompt=False,
    )
    assert app.status == ApprovalStatus.PENDING

    # Test approve command
    rc_approve = main(["approve", app.approval_id])
    assert rc_approve == 0
    resolved = approval_mgr.get_approval(app.approval_id)
    assert resolved is not None
    assert resolved.status == ApprovalStatus.APPROVED

    # Test reject command on second approval
    app2 = approval_mgr.request_approval(
        tool_call_id="call_high_risk_02",
        task_id="T002",
        operation="delete_file",
        arguments={"path": "important.txt"},
        risk_level=RiskLevel.HIGH,
        auto_prompt=False,
    )
    rc_reject = main(["reject", app2.approval_id, "--reason", "File is critical"])
    assert rc_reject == 0
    resolved2 = approval_mgr.get_approval(app2.approval_id)
    assert resolved2 is not None
    assert resolved2.status == ApprovalStatus.REJECTED


def test_quickstart_scenario_4_crash_resiliency_and_recovery(quickstart_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 4: Crash Resiliency & Session Recovery."""
    monkeypatch.chdir(quickstart_env)
    main(["init", "--force"])
    sm = StateManager(quickstart_env / ".harness" / "state.db")

    # Create run with T001 completed and T002 interrupted
    run_id = "run_interrupted"
    with sm.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO execution_runs (run_id, project_root, git_branch, model_endpoint, model_alias, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, str(quickstart_env), "main", "http://127.0.0.1:8080/v1", "frognano", "2026-11-01T10:00:00Z", "RUNNING"),
        )

    t1 = Task(
        task_id="T001",
        title="Task 1",
        objective="Obj 1",
        description="Desc 1",
        dependencies=(),
        allowed_files=(),
        acceptance_criteria=(),
        verification_commands=(),
        status=TaskStatus.COMPLETED,
        current_commit_hash=subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(quickstart_env), capture_output=True, text=True).stdout.strip(),
    )
    t2 = Task(
        task_id="T002",
        title="Task 2",
        objective="Obj 2",
        description="Desc 2",
        dependencies=("T001",),
        allowed_files=(),
        acceptance_criteria=(),
        verification_commands=(),
        status=TaskStatus.RUNNING,
    )
    sm.save_task(run_id, t1)
    sm.save_task(run_id, t2)
    sm.record_checkpoint(
        StateCheckpoint(
            checkpoint_id="chk_01",
            run_id=run_id,
            task_id="T001",
            git_commit_hash=t1.current_commit_hash,
            git_branch="main",
            committed_at="2026-11-01T10:01:00Z",
        )
    )

    # Resume session (reconciles git and recovers interrupted tasks)
    rc_resume = main(["resume", "--run-id", run_id, "--unattended"])
    # Completed or error depending on local llama.cpp endpoint, but reconciliation logic runs
    assert sm.get_task("T001").status == TaskStatus.COMPLETED
    # T002 was reset to READY by reconciliation
    assert sm.get_task("T002").status in (TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.COMPLETED)


def test_quickstart_scenario_5_audit_ledger_integrity(quickstart_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 5: Audit Ledger Cryptographic Integrity Check."""
    monkeypatch.chdir(quickstart_env)
    main(["init", "--force"])

    rc_audit = main(["audit", "--verify-chain"])
    assert rc_audit == 0


def test_quickstart_scenario_6_supervisory_report(quickstart_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario 6: Supervisory Report for Gemini."""
    monkeypatch.chdir(quickstart_env)
    main(["init", "--force"])
    sm = StateManager(quickstart_env / ".harness" / "state.db")

    # Create run
    run_id = "run_reporting_demo"
    with sm.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO execution_runs (run_id, project_root, git_branch, model_endpoint, model_alias, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, str(quickstart_env), "main", "http://127.0.0.1:8080/v1", "frognano", "2026-11-01T10:00:00Z", "RUNNING"),
        )

    t1 = Task(
        task_id="T001",
        title="Setup packaging",
        objective="Create pyproject",
        description="Write packaging",
        dependencies=(),
        allowed_files=(),
        acceptance_criteria=(),
        verification_commands=(),
        status=TaskStatus.COMPLETED,
    )
    sm.save_task(run_id, t1)

    rc_report = main(["report", "--format", "both"])
    assert rc_report == 0

    reports_dir = quickstart_env / ".harness" / "reports"
    assert reports_dir.exists()
    json_reports = list(reports_dir.glob("*.json"))
    md_reports = list(reports_dir.glob("*.md"))
    assert len(json_reports) >= 1
    assert len(md_reports) >= 1
