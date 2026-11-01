"""Git operations and repository integrity management."""

from pathlib import Path
import subprocess
from typing import Optional

from frognano_harness.exceptions import HarnessError


class GitManager:
    """Manages Git operations, task-level atomic commits, and repository checks."""

    def __init__(self, repo_root: Optional[Path] = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()

    def _run_git(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        """Execute a git command within the repository root."""
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=check,
                encoding="utf-8",
                errors="replace",
            )
            return result
        except subprocess.CalledProcessError as e:
            raise HarnessError(f"Git command failed: {' '.join(cmd)}\nStderr: {e.stderr}") from e

    def is_git_repo(self) -> bool:
        """Check if current directory is inside a Git repository."""
        result = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
        return result.returncode == 0 and result.stdout.strip() == "true"

    def get_current_branch(self) -> str:
        """Get the current Git branch name."""
        result = self._run_git(["branch", "--show-current"])
        branch = result.stdout.strip()
        if not branch:
            # Handle detached HEAD
            result = self._run_git(["rev-parse", "--short", "HEAD"])
            branch = f"detached-{result.stdout.strip()}"
        return branch

    def get_head_commit(self) -> str:
        """Get the current HEAD commit hash."""
        result = self._run_git(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def verify_commit_exists(self, commit_hash: str) -> bool:
        """Check if a commit hash exists in the local Git repository history."""
        result = self._run_git(["cat-file", "-e", f"{commit_hash}^{{commit}}"], check=False)
        return result.returncode == 0

    def has_uncommitted_changes(self) -> bool:
        """Check if the repository working tree has unstaged or staged changes."""
        result = self._run_git(["status", "--porcelain"])
        return len(result.stdout.strip()) > 0

    def get_status(self) -> str:
        """Get standard git status output."""
        result = self._run_git(["status", "--short"])
        return result.stdout.strip()

    def get_diff(self, cached: bool = False, path: Optional[str] = None) -> str:
        """Get git diff output."""
        args = ["diff"]
        if cached:
            args.append("--cached")
        if path:
            args.extend(["--", path])
        result = self._run_git(args)
        return result.stdout

    def commit_task_changes(self, task_id: str, title: str, files: Optional[list[str]] = None) -> str:
        """
        Stage specified task files (or all changes if files is None) and commit.
        Never pushes to remotes. Returns new commit hash.
        """
        if files:
            # Stage only specific files
            for f in files:
                target = (self.repo_root / f).resolve()
                if target.exists():
                    self._run_git(["add", str(f)])
                else:
                    self._run_git(["add", "-u", "--", str(f)], check=False)
        else:
            self._run_git(["add", "-A"])

        commit_message = f"[{task_id}] {title}"
        self._run_git(["commit", "-m", commit_message])
        return self.get_head_commit()
