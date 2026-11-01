"""Integration test for independent verification and bounded retry loop."""

import tempfile
from pathlib import Path
from frognano_harness.context_manager import ContextManager
from frognano_harness.models import Task, TaskStatus, VerificationOutcome
from frognano_harness.verification_engine import IndependentVerificationEngine


def test_verification_and_retry_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        test_script = workspace / "test_sample.py"

        # Initially test fails
        test_script.write_text("import sys; sys.exit(1)", encoding="utf-8")

        task = Task(
            task_id="T-001",
            title="Sample Task",
            objective="Make test pass",
            description="Fix test_sample.py",
            verification_commands=(f"python {test_script}",),
        )

        engine = IndependentVerificationEngine(workspace)
        cm = ContextManager()

        # Attempt 1: Fails
        records1, passed1 = engine.verify_task(task)
        assert passed1 is False
        assert records1[0].exit_code == 1

        # Check clean retry context generation
        retry_task = task.with_incremented_retry()
        assert retry_task.retry_count == 1
        retry_msgs = cm.build_retry_messages(
            task=retry_task,
            failed_command=records1[0].command,
            exit_code=records1[0].exit_code,
            stdout=records1[0].stdout,
            stderr=records1[0].stderr,
            git_diff="--- a/test.py\n+++ b/test.py",
        )
        assert len(retry_msgs) == 3
        assert "VERIFICATION FAILED (Attempt 2)" in retry_msgs[2]["content"]

        # Attempt 2: Fix test, now passes
        test_script.write_text("import sys; sys.exit(0)", encoding="utf-8")
        records2, passed2 = engine.verify_task(retry_task)
        assert passed2 is True
        assert records2[0].outcome == VerificationOutcome.PASSED
        assert records2[0].exit_code == 0
