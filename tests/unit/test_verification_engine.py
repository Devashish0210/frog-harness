"""Unit tests for IndependentVerificationEngine."""

import tempfile
from pathlib import Path
import pytest
from frognano_harness.models import Task, VerificationOutcome
from frognano_harness.verification_engine import IndependentVerificationEngine


@pytest.fixture
def workspace() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        yield root


def test_verification_success(workspace: Path) -> None:
    test_file = workspace / "pass.py"
    test_file.write_text("import sys; sys.exit(0)", encoding="utf-8")

    engine = IndependentVerificationEngine(workspace)
    task = Task(
        task_id="T-001",
        title="Passing",
        objective="Obj",
        description="Desc",
        verification_commands=(f"python {test_file}",),
    )

    records, is_passed = engine.verify_task(task)
    assert is_passed is True
    assert len(records) == 1
    assert records[0].outcome == VerificationOutcome.PASSED
    assert records[0].exit_code == 0


def test_verification_failure_exit_code(workspace: Path) -> None:
    test_file = workspace / "fail.py"
    test_file.write_text("import sys; sys.stderr.write('assertion error'); sys.exit(1)", encoding="utf-8")

    engine = IndependentVerificationEngine(workspace)
    task = Task(
        task_id="T-002",
        title="Failing",
        objective="Obj",
        description="Desc",
        verification_commands=(f"python {test_file}",),
    )

    records, is_passed = engine.verify_task(task)
    assert is_passed is False
    assert len(records) == 1
    assert records[0].outcome == VerificationOutcome.FAILED
    assert records[0].exit_code == 1
    assert "assertion error" in records[0].stderr


def test_verification_timeout(workspace: Path) -> None:
    test_file = workspace / "hang.py"
    test_file.write_text("import time; time.sleep(5)", encoding="utf-8")

    engine = IndependentVerificationEngine(workspace, default_timeout=1)
    task = Task(
        task_id="T-003",
        title="Hanging",
        objective="Obj",
        description="Desc",
        verification_commands=(f"python {test_file}",),
    )

    records, is_passed = engine.verify_task(task)
    assert is_passed is False
    assert len(records) == 1
    assert records[0].outcome == VerificationOutcome.FAILED
    assert records[0].exit_code == 124
    assert "timed out" in records[0].stderr.lower()


def test_validate_diff_boundaries(workspace: Path) -> None:
    engine = IndependentVerificationEngine(workspace)
    task = Task(
        task_id="T-004",
        title="Boundary check",
        objective="Obj",
        description="Desc",
        allowed_files=("src/allowed.py",),
    )

    valid_diff = "diff --git a/src/allowed.py b/src/allowed.py\n+++ b/src/allowed.py\n@@ -1 +1 @@\n+print(1)"
    is_valid, unauth = engine.validate_diff_boundaries(task, valid_diff)
    assert is_valid is True
    assert len(unauth) == 0

    invalid_diff = "diff --git a/src/secret.py b/src/secret.py\n+++ b/src/secret.py\n@@ -1 +1 @@\n+print(1)"
    is_valid2, unauth2 = engine.validate_diff_boundaries(task, invalid_diff)
    assert is_valid2 is False
    assert "src/secret.py" in unauth2
