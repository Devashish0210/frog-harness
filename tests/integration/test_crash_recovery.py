"""Integration test for process interruption and session resumption."""

import subprocess
import tempfile
from pathlib import Path
import pytest

from frognano_harness.git_manager import GitManager
from frognano_harness.models import (
    ExecutionRun,
    StateCheckpoint,
    Task,
    TaskAttempt,
    TaskStatus,
)
from frognano_harness.scheduler import TaskScheduler
from frognano_harness.state_manager import StateManager


@pytest.fixture
def temp_git_repo() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=str(repo_path), check=True, capture_output=True)
        readme = repo_path / "README.md"
        readme.write_text("# Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=str(repo_path), check=True, capture_output=True)
        yield repo_path


def test_crash_recovery_and_session_resumption(temp_git_repo: Path) -> None:
    db_path = temp_git_repo / ".harness" / "state.db"
    sm = StateManager(db_path)
    git = GitManager(temp_git_repo)

    run_id = "run_session_recover"
    run = ExecutionRun(
        run_id=run_id,
        project_root=str(temp_git_repo),
        git_branch=git.get_current_branch(),
        model_endpoint="http://127.0.0.1:8080/v1",
        model_alias="frognano",
        started_at="2026-11-01T12:00:00Z",
        status="RUNNING",
    )
    sm.create_run(run)

    # 1. Setup 3 tasks in dependency order: T001 -> T002 -> T003
    t1 = Task(
        task_id="T001",
        title="Setup config",
        objective="Create config.py",
        description="Write config file",
        dependencies=(),
        allowed_files=("config.py",),
        acceptance_criteria=("config.py exists",),
        verification_commands=(),
        status=TaskStatus.READY,
    )
    t2 = Task(
        task_id="T002",
        title="Implement parser",
        objective="Create parser.py",
        description="Write parser logic",
        dependencies=("T001",),
        allowed_files=("parser.py",),
        acceptance_criteria=("parser.py exists",),
        verification_commands=(),
        status=TaskStatus.PENDING,
    )
    t3 = Task(
        task_id="T003",
        title="Implement CLI",
        objective="Create cli.py",
        description="Write CLI entrypoint",
        dependencies=("T002",),
        allowed_files=("cli.py",),
        acceptance_criteria=("cli.py exists",),
        verification_commands=(),
        status=TaskStatus.PENDING,
    )
    sm.save_task(run_id, t1)
    sm.save_task(run_id, t2)
    sm.save_task(run_id, t3)

    # 2. Simulate successful execution of T001
    config_file = temp_git_repo / "config.py"
    config_file.write_text("DEBUG = True\n", encoding="utf-8")
    commit_1 = git.commit_task_changes("T001", "Setup config", ["config.py"])

    sm.update_task_status("T001", TaskStatus.COMPLETED, commit_hash=commit_1)
    sm.record_checkpoint(
        StateCheckpoint(
            checkpoint_id="chk_001",
            run_id=run_id,
            task_id="T001",
            git_commit_hash=commit_1,
            git_branch=git.get_current_branch(),
            committed_at="2026-11-01T12:05:00Z",
        )
    )

    # 3. Simulate T002 running when crash occurs
    sm.update_task_status("T002", TaskStatus.RUNNING)
    attempt_t2 = TaskAttempt(
        attempt_id="att_t2_1",
        run_id=run_id,
        task_id="T002",
        attempt_number=1,
        started_at="2026-11-01T12:06:00Z",
    )
    sm.record_attempt(attempt_t2)

    # CRASH OCCURS HERE: Terminal killed, process exited mid-execution
    # State in SQLite has T001 COMPLETED, T002 RUNNING, T003 PENDING

    # 4. Now harness resume is invoked
    reconciliation = sm.reconcile_and_resume(run_id, git)

    assert "T001" in reconciliation.verified_completed
    assert "T002" in reconciliation.reset_to_ready
    assert len(reconciliation.invalid_checkpoints) == 0

    # Verify task states after reconciliation
    task1 = sm.get_task("T001")
    task2 = sm.get_task("T002")
    task3 = sm.get_task("T003")

    assert task1.status == TaskStatus.COMPLETED
    assert task2.status == TaskStatus.READY
    assert task3.status == TaskStatus.PENDING

    # 5. Verify Scheduler correctly determines next executable task
    all_tasks = sm.list_tasks(run_id)
    scheduler = TaskScheduler(all_tasks)
    ready_tasks = scheduler.get_ready_tasks()

    assert len(ready_tasks) == 1
    assert ready_tasks[0].task_id == "T002"
