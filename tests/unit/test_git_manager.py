"""Unit tests for GitManager."""

import subprocess
import tempfile
from pathlib import Path
import pytest
from frognano_harness.git_manager import GitManager


@pytest.fixture
def temp_git_repo() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)
        # Initialize test repo
        subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
        )
        # Initial commit
        test_file = repo_dir / "init.txt"
        test_file.write_text("initial", encoding="utf-8")
        subprocess.run(["git", "add", "init.txt"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(repo_dir),
            check=True,
            capture_output=True,
        )
        yield repo_dir


def test_git_manager_basic_queries(temp_git_repo: Path) -> None:
    gm = GitManager(temp_git_repo)
    assert gm.is_git_repo() is True
    assert len(gm.get_head_commit()) == 40
    assert gm.has_uncommitted_changes() is False


def test_git_manager_uncommitted_changes(temp_git_repo: Path) -> None:
    gm = GitManager(temp_git_repo)
    new_file = temp_git_repo / "dirty.txt"
    new_file.write_text("changes", encoding="utf-8")
    assert gm.has_uncommitted_changes() is True

    # Commit task changes
    commit_hash = gm.commit_task_changes("T-100", "Add dirty file", ["dirty.txt"])
    assert len(commit_hash) == 40
    assert gm.has_uncommitted_changes() is False

    # Check commit message in git log
    res = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=str(temp_git_repo),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[T-100] Add dirty file" in res.stdout
