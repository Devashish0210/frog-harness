"""Unit tests for SpecKit task parser."""

import tempfile
from pathlib import Path
import pytest
from frognano_harness.exceptions import SpecParsingError
from frognano_harness.task_parser import TaskParser

SAMPLE_VALID_TASKS_MD = """# Tasks: Test Feature

- [ ] T001 Setup project structure in src/
- [ ] T002 [P] Implement models in src/models.py
- [ ] T003 [US1] Implement service in src/service.py (depends on T001, T002)
"""

SAMPLE_CONTRACT_TASKS_MD = """# Tasks: Complex Feature

### Task: T-001 - Initialize Database
Objective: Setup sqlite database
Allowed Files: src/db.py, tests/test_db.py
Dependencies: none
Acceptance Criteria: Database tables created
Verification Commands: pytest tests/test_db.py

### Task: T-002 - Build Auth
Objective: Implement token authentication
Allowed Files: src/auth.py
Dependencies: T-001
Acceptance Criteria: Auth returns token
Verification Commands: pytest tests/test_auth.py
"""


def test_parse_checklist_tasks() -> None:
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md", encoding="utf-8") as f:
        f.write(SAMPLE_VALID_TASKS_MD)
        path = Path(f.name)

    parser = TaskParser()
    tasks = parser.parse_tasks_file(path)
    assert len(tasks) == 3
    assert tasks[0].task_id == "T001"
    assert "Setup project structure" in tasks[0].title
    assert tasks[1].task_id == "T002"
    assert tasks[2].task_id == "T003"
    assert "T001" in tasks[2].dependencies
    assert "T002" in tasks[2].dependencies


def test_parse_structured_contract_tasks() -> None:
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md", encoding="utf-8") as f:
        f.write(SAMPLE_CONTRACT_TASKS_MD)
        path = Path(f.name)

    parser = TaskParser()
    tasks = parser.parse_tasks_file(path)
    assert len(tasks) == 2
    assert tasks[0].task_id == "T-001"
    assert tasks[0].objective == "Setup sqlite database"
    assert "src/db.py" in tasks[0].allowed_files
    assert "pytest tests/test_db.py" in tasks[0].verification_commands

    assert tasks[1].task_id == "T-002"
    assert "T-001" in tasks[1].dependencies
