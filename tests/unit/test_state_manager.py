"""Unit tests for StateManager and crash recovery reconciliation."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from frognano_harness.models import (
    ExecutionRun,
    StateCheckpoint,
    Task,
    TaskAttempt,
    TaskStatus,
)
from frognano_harness.state_manager import StateManager


@pytest.fixture
def temp_db() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / ".harness" / "state.db"


def test_state_manager_run_crud(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    run = ExecutionRun(
        run_id="run_100",
        project_root="/path/to/project",
        git_branch="main",
        model_endpoint="http://127.0.0.1:8080/v1",
        model_alias="frognano",
        started_at="2026-11-01T10:00:00Z",
        status="RUNNING",
        total_tasks=5,
    )
    sm.create_run(run)

    fetched = sm.get_run("run_100")
    assert fetched is not None
    assert fetched.run_id == "run_100"
    assert fetched.status == "RUNNING"
    assert fetched.total_tasks == 5

    sm.update_run_status("run_100", "COMPLETED", completed_at="2026-11-01T10:30:00Z")
    updated = sm.get_run("run_100")
    assert updated is not None
    assert updated.status == "COMPLETED"
    assert updated.completed_at == "2026-11-01T10:30:00Z"


def test_state_manager_task_and_attempt_crud(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    run = ExecutionRun(
        run_id="run_101",
        project_root="/path/to/project",
        git_branch="main",
        model_endpoint="http://127.0.0.1:8080/v1",
        model_alias="frognano",
        started_at="2026-11-01T10:00:00Z",
        status="RUNNING",
    )
    sm.create_run(run)

    task = Task(
        task_id="T001",
        title="Setup project",
        objective="Initialize repo",
        description="Write pyproject.toml",
        dependencies=(),
        allowed_files=("pyproject.toml",),
        acceptance_criteria=("pyproject.toml exists",),
        verification_commands=("pytest",),
        status=TaskStatus.READY,
    )
    sm.save_task("run_101", task)

    # Fetch task
    t_fetched = sm.get_task("T001")
    assert t_fetched is not None
    assert t_fetched.status == TaskStatus.READY

    # Update task status
    sm.update_task_status("T001", TaskStatus.RUNNING)
    t_updated = sm.get_task("T001")
    assert t_updated is not None
    assert t_updated.status == TaskStatus.RUNNING

    # Record attempt
    attempt = TaskAttempt(
        attempt_id="att_1",
        run_id="run_101",
        task_id="T001",
        attempt_number=1,
        started_at="2026-11-01T10:05:00Z",
    )
    sm.record_attempt(attempt)

    attempts = sm.get_attempts("T001")
    assert len(attempts) == 1
    assert attempts[0].attempt_id == "att_1"
    assert attempts[0].outcome == "IN_PROGRESS"

    # Update attempt
    sm.update_attempt_outcome(
        attempt_id="att_1",
        outcome="SUCCESS",
        completed_at="2026-11-01T10:07:00Z",
        prompt_tokens=150,
        completion_tokens=50,
    )
    updated_attempts = sm.get_attempts("T001")
    assert updated_attempts[0].outcome == "SUCCESS"
    assert updated_attempts[0].prompt_tokens == 150


def test_state_manager_reconcile_with_git(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    run_id = "run_crash_test"
    run = ExecutionRun(
        run_id=run_id,
        project_root="/path/to/project",
        git_branch="main",
        model_endpoint="http://127.0.0.1:8080/v1",
        model_alias="frognano",
        started_at="2026-11-01T10:00:00Z",
        status="RUNNING",
    )
    sm.create_run(run)

    # Task 1: Completed with valid Git commit
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
        current_commit_hash="commit_hash_1",
    )
    sm.save_task(run_id, t1)
    sm.record_checkpoint(
        StateCheckpoint(
            checkpoint_id="chk_1",
            run_id=run_id,
            task_id="T001",
            git_commit_hash="commit_hash_1",
            git_branch="main",
            committed_at="2026-11-01T10:05:00Z",
        )
    )

    # Task 2: Was RUNNING when crash occurred
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
    sm.save_task(run_id, t2)

    # Task 3: Marked COMPLETED in DB, but commit is missing from Git
    t3 = Task(
        task_id="T003",
        title="Task 3",
        objective="Obj 3",
        description="Desc 3",
        dependencies=(),
        allowed_files=(),
        acceptance_criteria=(),
        verification_commands=(),
        status=TaskStatus.COMPLETED,
        current_commit_hash="ghost_commit",
    )
    sm.save_task(run_id, t3)
    sm.record_checkpoint(
        StateCheckpoint(
            checkpoint_id="chk_3",
            run_id=run_id,
            task_id="T003",
            git_commit_hash="ghost_commit",
            git_branch="main",
            committed_at="2026-11-01T10:15:00Z",
        )
    )

    # Mock GitManager
    mock_git = MagicMock()
    # "commit_hash_1" exists in git, "ghost_commit" does not
    def fake_verify_commit(commit_hash: str) -> bool:
        return commit_hash == "commit_hash_1"

    mock_git.verify_commit_exists.side_effect = fake_verify_commit

    # Reconcile
    result = sm.reconcile_and_resume(run_id, mock_git)

    assert "T001" in result.verified_completed
    assert "T002" in result.reset_to_ready
    assert "T003" in result.invalid_checkpoints

    # Check updated task statuses in SQLite
    assert sm.get_task("T001").status == TaskStatus.COMPLETED
    assert sm.get_task("T002").status == TaskStatus.READY
    assert sm.get_task("T003").status == TaskStatus.READY
