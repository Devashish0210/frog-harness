"""Integration test for report generation and schema compliance."""

import json
from pathlib import Path
import subprocess
import tempfile
import jsonschema
import pytest

from frognano_harness.git_manager import GitManager
from frognano_harness.models import (
    ExecutionRun,
    StateCheckpoint,
    Task,
    TaskAttempt,
    TaskStatus,
)
from frognano_harness.reporting import ReportGenerator
from frognano_harness.state_manager import StateManager

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "specs" / "002-local-execution-harness" / "contracts" / "report-schema.json"


@pytest.fixture
def temp_git_repo() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        subprocess.run(["git", "init"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Reporter"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "reporter@frognano.local"], cwd=str(repo_path), check=True, capture_output=True)
        readme = repo_path / "README.md"
        readme.write_text("# Reporter Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=str(repo_path), check=True, capture_output=True)
        yield repo_path


def test_report_generation_lifecycle(temp_git_repo: Path) -> None:
    db_path = temp_git_repo / ".harness" / "state.db"
    sm = StateManager(db_path)
    git = GitManager(temp_git_repo)
    reports_dir = temp_git_repo / ".harness" / "reports"
    generator = ReportGenerator(sm, git, project_name="Frognano-Harness-Test", reports_dir=reports_dir)

    run_id = "run_rep_001"
    run = ExecutionRun(
        run_id=run_id,
        project_root=str(temp_git_repo),
        git_branch=git.get_current_branch(),
        model_endpoint="http://127.0.0.1:8080/v1",
        model_alias="frognano",
        started_at="2026-11-01T10:00:00Z",
        status="RUNNING",
    )
    sm.create_run(run)

    # Task 1: Completed
    t1 = Task(
        task_id="T001",
        title="Setup packaging",
        objective="Create pyproject.toml",
        description="Write packaging config",
        dependencies=(),
        allowed_files=("pyproject.toml",),
        acceptance_criteria=("file exists",),
        verification_commands=("pytest",),
        status=TaskStatus.COMPLETED,
        current_commit_hash=git.get_head_commit(),
    )
    sm.save_task(run_id, t1)
    sm.record_checkpoint(
        StateCheckpoint(
            checkpoint_id="chk_rep_1",
            run_id=run_id,
            task_id="T001",
            git_commit_hash=git.get_head_commit(),
            git_branch=git.get_current_branch(),
            committed_at="2026-11-01T10:05:00Z",
        )
    )

    # Task 2: Blocked after 2 retries
    t2 = Task(
        task_id="T002",
        title="Flaky module",
        objective="Pass integration test",
        description="Module has complex edge case",
        dependencies=("T001",),
        allowed_files=("module.py",),
        acceptance_criteria=("passes",),
        verification_commands=("pytest tests/test_mod.py",),
        status=TaskStatus.BLOCKED,
        retry_count=2,
    )
    sm.save_task(run_id, t2)

    # Task 3: Pending (depends on T002)
    t3 = Task(
        task_id="T003",
        title="Dependent module",
        objective="Depends on flaky",
        description="Downstream task",
        dependencies=("T002",),
        allowed_files=("downstream.py",),
        acceptance_criteria=("passes",),
        verification_commands=(),
        status=TaskStatus.PENDING,
    )
    sm.save_task(run_id, t3)

    # Export reports
    json_path, md_path = generator.export_reports(run_id)

    assert json_path.exists()
    assert md_path.exists()

    # Verify JSON content against JSON Schema
    with open(json_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    jsonschema.validate(instance=report_data, schema=schema)

    assert report_data["summary"]["total_tasks"] == 3
    assert report_data["summary"]["completed_tasks"] == 1
    assert report_data["summary"]["blocked_tasks"] == 1
    assert report_data["summary"]["pending_tasks"] == 1
    assert report_data["summary"]["status"] == "BLOCKED"
    assert len(report_data["completed_task_checkpoints"]) == 1
    assert len(report_data["blocked_tasks"]) == 1
    assert "T003" in report_data["blocked_tasks"][0]["cascaded_blocked_dependents"]

    # Verify Markdown content
    md_content = md_path.read_text(encoding="utf-8")
    assert "# Execution Report: Frognano-Harness-Test" in md_content
    assert "| `T001` | Setup packaging |" in md_content
    assert "Task `T002`: Flaky module" in md_content
    assert "**Cascaded Blocked Dependents**: T003" in md_content
