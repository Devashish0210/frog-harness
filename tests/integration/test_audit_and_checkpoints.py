"""Integration test for audit ledger hash chain and Git checkpoint commits."""

import subprocess
import tempfile
from pathlib import Path
import pytest

from frognano_harness.audit_ledger import AuditLedger
from frognano_harness.git_manager import GitManager
from frognano_harness.state_manager import StateManager


@pytest.fixture
def temp_git_repo() -> Path:
    """Create a temporary initialized git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "FrogNano Harness"],
            cwd=str(repo_path),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "harness@frognano.local"],
            cwd=str(repo_path),
            check=True,
            capture_output=True,
        )
        # Initial commit so HEAD exists
        readme = repo_path / "README.md"
        readme.write_text("# Test Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(repo_path),
            check=True,
            capture_output=True,
        )
        yield repo_path


def test_audit_ledger_and_git_checkpoint_lifecycle(temp_git_repo: Path) -> None:
    db_path = temp_git_repo / ".harness" / "state.db"
    sm = StateManager(db_path)
    ledger = AuditLedger(sm)
    git = GitManager(temp_git_repo)

    run_id = "run_test_001"
    with sm.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO execution_runs (
                run_id, project_root, git_branch, model_endpoint, model_alias, started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, str(temp_git_repo), "main", "http://127.0.0.1:8080/v1", "frognano", "2026-11-01T12:00:00Z", "RUNNING"),
        )
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, run_id, title, objective, description, dependencies_json,
                allowed_files_json, acceptance_criteria_json, verification_commands_json,
                status, retry_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "T001",
                run_id,
                "Setup package",
                "Setup package files",
                "Setup description",
                "[]",
                "[]",
                "[]",
                "[]",
                "RUNNING",
                0,
                "2026-11-01T12:00:00Z",
                "2026-11-01T12:00:00Z",
            ),
        )

    # 1. Audit start of task
    ledger.record_event("TASK_STATE", {"task_id": "T001", "status": "IN_PROGRESS"})

    # 2. Modify files and commit atomic task checkpoint
    src_file = temp_git_repo / "main.py"
    src_file.write_text("print('hello world')\n", encoding="utf-8")

    commit_hash = git.commit_task_changes(
        task_id="T001",
        title="Setup package",
        files=["main.py"],
    )
    assert len(commit_hash) == 40

    # 3. Record state checkpoint in SQLite
    with sm.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO checkpoints (checkpoint_id, run_id, task_id, git_commit_hash, git_branch, committed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("chk_001", run_id, "T001", commit_hash, git.get_current_branch(), "2026-11-01T12:05:00Z"),
        )
        conn.execute(
            "UPDATE tasks SET status = 'COMPLETED' WHERE task_id = 'T001'"
        )

    # 4. Audit git checkpoint event
    ledger.record_event(
        "GIT_CHECKPOINT",
        {"task_id": "T001", "commit_hash": commit_hash, "branch": git.get_current_branch()},
    )

    # 5. Verify git history
    status_log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=str(temp_git_repo),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[T001] Setup package" in status_log.stdout

    # 6. Verify audit chain integrity
    is_valid, count, err = ledger.verify_chain()
    assert is_valid is True
    assert count == 2
    assert err is None
