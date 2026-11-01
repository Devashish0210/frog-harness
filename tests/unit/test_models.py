"""Unit tests for frognano_harness models."""

import pytest
from frognano_harness.models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditEntry,
    DecisionType,
    RiskLevel,
    Task,
    TaskStatus,
    ToolCallRequest,
)


def test_task_creation_and_validation() -> None:
    task = Task(
        task_id="T-001",
        title="Setup project",
        objective="Initialize base project files",
        description="Detailed description",
        dependencies=("T-000",),
        allowed_files=("pyproject.toml",),
        acceptance_criteria=("Project initializes",),
        verification_commands=("pytest",),
    )
    assert task.task_id == "T-001"
    assert task.status == TaskStatus.PENDING
    assert task.retry_count == 0

    # Immutability
    with pytest.raises(Exception):
        task.status = TaskStatus.RUNNING  # type: ignore[misc]

    # State transition helper
    running_task = task.with_status(TaskStatus.RUNNING)
    assert running_task.status == TaskStatus.RUNNING
    assert task.status == TaskStatus.PENDING

    # Retry increment
    retried_task = task.with_incremented_retry()
    assert retried_task.retry_count == 1
    assert task.retry_count == 0


def test_task_invalid_id() -> None:
    with pytest.raises(ValueError, match="Invalid task_id"):
        Task(
            task_id="invalid task id with spaces!",
            title="Title",
            objective="Objective",
            description="Desc",
        )


def test_task_empty_objective() -> None:
    with pytest.raises(ValueError, match="objective must not be empty"):
        Task(
            task_id="T-001",
            title="Title",
            objective="   ",
            description="Desc",
        )


def test_tool_call_args_hash() -> None:
    args1 = {"path": "a.txt", "content": "hello"}
    args2 = {"content": "hello", "path": "a.txt"}
    # Sorting ensures identical hashes
    hash1 = ToolCallRequest.compute_args_hash(args1)
    hash2 = ToolCallRequest.compute_args_hash(args2)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_audit_entry_hash_chain() -> None:
    prev_hash = "0" * 64
    event_type = "TOOL_REQUEST"
    payload = '{"tool":"read_file"}'
    ts = "2026-11-01T12:00:00.000Z"

    entry_hash = AuditEntry.compute_hash(prev_hash, event_type, payload, ts)
    assert len(entry_hash) == 64
    assert entry_hash != prev_hash
