"""Contract test for SQLite schema verification."""

import tempfile
from pathlib import Path
import pytest
from frognano_harness.models import ExecutionRun, StateCheckpoint, Task, TaskStatus
from frognano_harness.state_manager import StateManager


@pytest.fixture
def temp_db() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / ".harness" / "state.db"


def test_sqlite_schema_initialization(temp_db: Path) -> None:
    manager = StateManager(temp_db)
    with manager.get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        table_names = [t["name"] for t in tables]

        expected_tables = [
            "approvals",
            "audit_events",
            "authorizations",
            "checkpoints",
            "execution_runs",
            "schema_migrations",
            "task_attempts",
            "tasks",
            "tool_calls",
            "tool_executions",
            "verifications",
        ]
        for expected in expected_tables:
            assert expected in table_names, f"Missing table: {expected}"


def test_state_manager_run_and_task_lifecycle(temp_db: Path) -> None:
    manager = StateManager(temp_db)
    run = ExecutionRun(
        run_id="run-1",
        project_root="/path",
        git_branch="002-feature",
        model_endpoint="http://127.0.0.1:8080/v1",
        model_alias="frognano",
        started_at="2026-11-01T12:00:00Z",
    )
    manager.create_run(run)

    task = Task(
        task_id="T-001",
        title="Setup",
        objective="Run setup",
        description="Detailed description",
        dependencies=(),
        allowed_files=("setup.py",),
        acceptance_criteria=("Setup exists",),
        verification_commands=("pytest",),
    )
    manager.save_task(run.run_id, task)

    saved_task = manager.get_task("T-001")
    assert saved_task is not None
    assert saved_task.task_id == "T-001"
    assert saved_task.status == TaskStatus.PENDING

    # Transition and update
    completed_task = saved_task.with_status(TaskStatus.COMPLETED, commit_hash="abc1234")
    manager.save_task(run.run_id, completed_task)

    updated_task = manager.get_task("T-001")
    assert updated_task is not None
    assert updated_task.status == TaskStatus.COMPLETED
    assert updated_task.current_commit_hash == "abc1234"

    # Checkpoint
    checkpoint = StateCheckpoint(
        checkpoint_id="chk-1",
        run_id="run-1",
        task_id="T-001",
        git_commit_hash="abc1234",
        git_branch="002-feature",
        committed_at="2026-11-01T12:05:00Z",
    )
    manager.record_checkpoint(checkpoint)
    saved_chk = manager.get_checkpoint("T-001")
    assert saved_chk is not None
    assert saved_chk.git_commit_hash == "abc1234"
