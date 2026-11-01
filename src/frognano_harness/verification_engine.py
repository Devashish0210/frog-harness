"""Independent Verification Engine: validates implementations via subprocess test runners."""

from datetime import datetime, timezone
from pathlib import Path
import re
import shlex
import subprocess
import time
from typing import Optional
import uuid

from frognano_harness.models import Task, VerificationOutcome, VerificationRecord

DIFF_FILE_REGEX = re.compile(r"^\+\+\+\s+b/(.*)$", re.MULTILINE)


class IndependentVerificationEngine:
    """Executes prescribed verification commands independently of model assertions."""

    def __init__(self, project_root: Optional[Path] = None, default_timeout: int = 120) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.default_timeout = default_timeout

    def verify_task(
        self,
        task: Task,
        attempt_id: Optional[str] = None,
    ) -> tuple[list[VerificationRecord], bool]:
        """
        Execute all prescribed verification commands for a task.
        Returns a list of verification records and overall passed flag.
        """
        records: list[VerificationRecord] = []
        overall_passed = True
        att_id = attempt_id or f"ATT-{uuid.uuid4().hex[:6].upper()}"

        commands = task.verification_commands or ("pytest",)

        for cmd_str in commands:
            now = datetime.now(timezone.utc).isoformat()
            ver_id = f"VER-{uuid.uuid4().hex[:8].upper()}"
            start_time = time.perf_counter()

            # Execute command safely via subprocess
            try:
                res = subprocess.run(
                    cmd_str,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=self.default_timeout,
                    shell=True,
                    encoding="utf-8",
                    errors="replace",
                )
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                outcome = VerificationOutcome.PASSED if res.returncode == 0 else VerificationOutcome.FAILED

                record = VerificationRecord(
                    verification_id=ver_id,
                    attempt_id=att_id,
                    command=cmd_str,
                    exit_code=res.returncode,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    duration_ms=duration_ms,
                    outcome=outcome,
                    verified_at=now,
                )
            except subprocess.TimeoutExpired:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                record = VerificationRecord(
                    verification_id=ver_id,
                    attempt_id=att_id,
                    command=cmd_str,
                    exit_code=124,
                    stdout="",
                    stderr=f"Verification command timed out after {self.default_timeout} seconds: {cmd_str}",
                    duration_ms=duration_ms,
                    outcome=VerificationOutcome.FAILED,
                    verified_at=now,
                )
            except Exception as e:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                record = VerificationRecord(
                    verification_id=ver_id,
                    attempt_id=att_id,
                    command=cmd_str,
                    exit_code=1,
                    stdout="",
                    stderr=f"Verification execution error: {e}",
                    duration_ms=duration_ms,
                    outcome=VerificationOutcome.FAILED,
                    verified_at=now,
                )

            records.append(record)
            if record.outcome != VerificationOutcome.PASSED:
                overall_passed = False

        return records, overall_passed

    def validate_diff_boundaries(self, task: Task, diff_text: str) -> tuple[bool, list[str]]:
        """
        Verify that all modified files in the git diff reside within task.allowed_files.
        Returns (is_valid, list_of_unauthorized_files).
        """
        if not task.allowed_files:
            return True, []

        normalized_allowed = {
            f.replace("\\", "/").lstrip("./") for f in task.allowed_files
        }
        modified_files = set(DIFF_FILE_REGEX.findall(diff_text))
        unauthorized: list[str] = []

        for m_file in modified_files:
            norm_m = m_file.replace("\\", "/").lstrip("./")
            if norm_m not in normalized_allowed:
                unauthorized.append(norm_m)

        return len(unauthorized) == 0, unauthorized
