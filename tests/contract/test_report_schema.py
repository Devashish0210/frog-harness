"""Contract test for supervisory report schema."""

import json
from pathlib import Path
import jsonschema
import pytest

from frognano_harness.reporting import ReportGenerator

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "specs" / "002-local-execution-harness" / "contracts" / "report-schema.json"


@pytest.fixture
def report_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_supervisory_report_validates_against_json_schema(report_schema: dict) -> None:
    sample_report = {
        "report_version": "1.0.0",
        "generated_at": "2026-11-01T12:00:00Z",
        "run_id": "run_test_001",
        "project_name": "Frognano-harness",
        "git_branch": "002-local-execution-harness",
        "head_commit": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        "summary": {
            "status": "PARTIAL",
            "total_tasks": 10,
            "completed_tasks": 5,
            "blocked_tasks": 1,
            "failed_tasks": 0,
            "pending_tasks": 4,
            "progress_percentage": 50.0,
        },
        "completed_task_checkpoints": [
            {
                "task_id": "T001",
                "title": "Setup package layout",
                "git_commit_hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                "completed_at": "2026-11-01T12:05:00Z",
                "attempts": 1,
            }
        ],
        "blocked_tasks": [
            {
                "task_id": "T006",
                "title": "Complex feature",
                "reason": "Exceeded maximum retry limit (2/2)",
                "failed_attempts": 2,
                "verification_errors": [
                    {
                        "command": "pytest tests/unit/test_feature.py",
                        "exit_code": 1,
                        "stderr_snippet": "AssertionError: Expected 42 but got 0",
                    }
                ],
                "cascaded_blocked_dependents": ["T007", "T008"],
            }
        ],
        "policy_violations": [
            {
                "task_id": "T006",
                "tool_name": "run_command",
                "denied_path_or_command": "rm -rf /",
                "policy_rule": "DESTRUCTIVE_COMMAND_PROHIBITED",
                "timestamp": "2026-11-01T12:08:00Z",
            }
        ],
        "recommended_actions": [
            "Review verification failure in task T006 and update prompt or tests.",
            "Run 'harness retry T006' after resolving root cause.",
        ],
    }

    # Must validate cleanly without exception
    jsonschema.validate(instance=sample_report, schema=report_schema)
