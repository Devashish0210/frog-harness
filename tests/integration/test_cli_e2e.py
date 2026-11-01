"""Integration tests for CLI command execution end-to-end."""

import os
from pathlib import Path
import subprocess
import tempfile
import pytest

from frognano_harness.cli import main


@pytest.fixture
def temp_project() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create minimal git repo
        subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "tester@frognano.local"], cwd=str(root), check=True, capture_output=True)
        (root / "README.md").write_text("# Test\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=str(root), check=True, capture_output=True)

        # Create valid tasks.md
        tasks_dir = root / "specs" / "001-demo"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        tasks_file = tasks_dir / "tasks.md"
        tasks_file.write_text(
            """# Tasks: Demo Feature

- [ ] T001 [Setup] Initialize package layout
  - Objective: Create basic src/ structure
  - Files: src/__init__.py
  - Criteria:
    - Package directory exists
  - Verification:
    - python -c "print('ok')"

- [ ] T002 [Core] Add core module
  - Prereqs: T001
  - Objective: Create core logic
  - Files: src/core.py
  - Criteria:
    - core module imports
  - Verification:
    - python -c "print('core ok')"
""",
            encoding="utf-8",
        )
        yield root


def test_cli_lifecycle_end_to_end(temp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(temp_project)

    # 1. init
    rc_init = main(["init", "--endpoint", "http://127.0.0.1:8080/v1", "--force"])
    assert rc_init == 0
    assert (temp_project / ".harness" / "config.json").exists()
    assert (temp_project / ".harness" / "state.db").exists()

    # 2. validate
    tasks_path = str(temp_project / "specs" / "001-demo" / "tasks.md")
    rc_validate = main(["validate", "--tasks", tasks_path])
    assert rc_validate == 0

    rc_validate_json = main(["validate", "--tasks", tasks_path, "--json"])
    assert rc_validate_json == 0

    # 3. plan
    rc_plan = main(["plan", "--tasks", tasks_path])
    assert rc_plan == 0

    rc_plan_json = main(["plan", "--tasks", tasks_path, "--json"])
    assert rc_plan_json == 0

    # 4. status
    rc_status = main(["status"])
    assert rc_status == 0

    # 5. audit verify-chain (initially empty chain is valid)
    rc_audit = main(["audit", "--verify-chain"])
    assert rc_audit == 0
