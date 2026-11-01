"""SQLite state persistence and database manager for Frognano Execution Harness."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Generator, Optional

from frognano_harness.models import (
    ApprovalRequest,
    ApprovalStatus,
    ExecutionRun,
    ReconciliationResult,
    RiskLevel,
    StateCheckpoint,
    Task,
    TaskAttempt,
    TaskStatus,
)
from frognano_harness.protocols import GitManagerProtocol

SCHEMA_SQL_PATH = Path(__file__).resolve().parent.parent.parent / "specs" / "002-local-execution-harness" / "contracts" / "sqlite-schema.sql"

FALLBACK_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_runs (
    run_id TEXT PRIMARY KEY,
    project_root TEXT NOT NULL,
    git_branch TEXT NOT NULL,
    model_endpoint TEXT NOT NULL,
    model_alias TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('INITIALIZING', 'RUNNING', 'COMPLETED', 'FAILED', 'INTERRUPTED')),
    total_tasks INTEGER NOT NULL DEFAULT 0,
    completed_tasks INTEGER NOT NULL DEFAULT 0,
    failed_tasks INTEGER NOT NULL DEFAULT 0,
    blocked_tasks INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    description TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,
    allowed_files_json TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL,
    verification_commands_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'READY', 'RUNNING', 'PENDING_APPROVAL', 'VERIFYING', 'SUCCESS', 'COMPLETED', 'FAILED', 'BLOCKED')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    current_commit_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_run_id ON tasks(run_id);

CREATE TABLE IF NOT EXISTS task_attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    model_response TEXT,
    git_diff TEXT,
    outcome TEXT NOT NULL CHECK(outcome IN ('IN_PROGRESS', 'SUCCESS', 'FAILED', 'BLOCKED', 'TIMED_OUT')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attempts_task_id ON task_attempts(task_id);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    raw_arguments_json TEXT NOT NULL,
    normalized_arguments_json TEXT NOT NULL,
    arguments_hash TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    FOREIGN KEY (attempt_id) REFERENCES task_attempts(attempt_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS authorizations (
    decision_id TEXT PRIMARY KEY,
    tool_call_id TEXT NOT NULL UNIQUE,
    decision TEXT NOT NULL CHECK(decision IN ('ALLOW', 'DENY', 'REQUIRE_APPROVAL')),
    risk_level TEXT NOT NULL CHECK(risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    policy_rule TEXT NOT NULL,
    reason TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (tool_call_id) REFERENCES tool_calls(tool_call_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    tool_call_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    exact_arguments_json TEXT NOT NULL,
    arguments_hash TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('MEDIUM', 'HIGH')),
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);

CREATE TABLE IF NOT EXISTS tool_executions (
    execution_id TEXT PRIMARY KEY,
    tool_call_id TEXT NOT NULL UNIQUE,
    exit_code INTEGER NOT NULL,
    stdout TEXT,
    stderr TEXT,
    affected_files_json TEXT NOT NULL DEFAULT '[]',
    duration_ms INTEGER NOT NULL,
    result_hash TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    FOREIGN KEY (tool_call_id) REFERENCES tool_calls(tool_call_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verifications (
    verification_id TEXT PRIMARY KEY,
    attempt_id TEXT NOT NULL,
    command TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    stdout TEXT,
    stderr TEXT,
    duration_ms INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK(outcome IN ('PASSED', 'FAILED', 'INCOMPLETE', 'NEEDS_HUMAN_REVIEW')),
    verified_at TEXT NOT NULL,
    FOREIGN KEY (attempt_id) REFERENCES task_attempts(attempt_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verifications_attempt_id ON verifications(attempt_id);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL UNIQUE,
    git_commit_hash TEXT NOT NULL,
    git_branch TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL UNIQUE,
    prev_entry_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('RUN_EVENT', 'TASK_STATE', 'TOOL_REQUEST', 'POLICY_DECISION', 'APPROVAL_ACTION', 'TOOL_EXECUTION', 'VERIFICATION_OUTCOME', 'GIT_CHECKPOINT')),
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_entry_hash ON audit_events(entry_hash);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);

CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only: updates are prohibited');
END;

CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only: deletes are prohibited');
END;
"""


class StateManager:
    """Manages SQLite persistent state for execution runs and tasks."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Initialize database tables according to sqlite-schema.sql."""
        ddl = FALLBACK_SCHEMA_SQL
        if SCHEMA_SQL_PATH.exists():
            try:
                with open(SCHEMA_SQL_PATH, "r", encoding="utf-8") as f:
                    ddl = f.read()
            except Exception:
                pass

        with self.get_connection() as conn:
            conn.executescript(ddl)

    def create_run(self, run: ExecutionRun) -> None:
        """Persist a new execution run."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_runs (
                    run_id, project_root, git_branch, model_endpoint, model_alias,
                    started_at, completed_at, status, total_tasks, completed_tasks,
                    failed_tasks, blocked_tasks
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id, run.project_root, run.git_branch, run.model_endpoint,
                    run.model_alias, run.started_at, run.completed_at, run.status,
                    run.total_tasks, run.completed_tasks, run.failed_tasks, run.blocked_tasks
                )
            )

    def get_run(self, run_id: str) -> Optional[ExecutionRun]:
        """Fetch an execution run by ID."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM execution_runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return None
            return ExecutionRun(
                run_id=row["run_id"],
                project_root=row["project_root"],
                git_branch=row["git_branch"],
                model_endpoint=row["model_endpoint"],
                model_alias=row["model_alias"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                status=row["status"],
                total_tasks=row["total_tasks"],
                completed_tasks=row["completed_tasks"],
                failed_tasks=row["failed_tasks"],
                blocked_tasks=row["blocked_tasks"],
            )

    def save_task(self, run_id: str, task: Task) -> None:
        """Insert or update a task record."""
        now = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, run_id, title, objective, description,
                    dependencies_json, allowed_files_json, acceptance_criteria_json,
                    verification_commands_json, status, retry_count, current_commit_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    retry_count = excluded.retry_count,
                    current_commit_hash = excluded.current_commit_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    task.task_id,
                    run_id,
                    task.title,
                    task.objective,
                    task.description,
                    json.dumps(list(task.dependencies)),
                    json.dumps(list(task.allowed_files)),
                    json.dumps(list(task.acceptance_criteria)),
                    json.dumps(list(task.verification_commands)),
                    task.status.value,
                    task.retry_count,
                    task.current_commit_hash,
                    now,
                    now,
                )
            )

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return Task(
                task_id=row["task_id"],
                title=row["title"],
                objective=row["objective"],
                description=row["description"],
                dependencies=tuple(json.loads(row["dependencies_json"])),
                allowed_files=tuple(json.loads(row["allowed_files_json"])),
                acceptance_criteria=tuple(json.loads(row["acceptance_criteria_json"])),
                verification_commands=tuple(json.loads(row["verification_commands_json"])),
                status=TaskStatus(row["status"]),
                retry_count=row["retry_count"],
                current_commit_hash=row["current_commit_hash"],
            )

    def list_tasks(self, run_id: Optional[str] = None) -> list[Task]:
        """List all tasks, optionally filtered by run ID."""
        with self.get_connection() as conn:
            if run_id:
                rows = conn.execute("SELECT * FROM tasks WHERE run_id = ?", (run_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tasks").fetchall()

            return [
                Task(
                    task_id=row["task_id"],
                    title=row["title"],
                    objective=row["objective"],
                    description=row["description"],
                    dependencies=tuple(json.loads(row["dependencies_json"])),
                    allowed_files=tuple(json.loads(row["allowed_files_json"])),
                    acceptance_criteria=tuple(json.loads(row["acceptance_criteria_json"])),
                    verification_commands=tuple(json.loads(row["verification_commands_json"])),
                    status=TaskStatus(row["status"]),
                    retry_count=row["retry_count"],
                    current_commit_hash=row["current_commit_hash"],
                )
                for row in rows
            ]

    def record_checkpoint(self, checkpoint: StateCheckpoint) -> None:
        """Record an atomic Git checkpoint commit for a task."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints (
                    checkpoint_id, run_id, task_id, git_commit_hash, git_branch, committed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id, checkpoint.run_id, checkpoint.task_id,
                    checkpoint.git_commit_hash, checkpoint.git_branch, checkpoint.committed_at
                )
            )

    def get_checkpoint(self, task_id: str) -> Optional[StateCheckpoint]:
        """Retrieve the checkpoint for a task."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM checkpoints WHERE task_id = ?", (task_id,)).fetchone()
            if not row:
                return None
            return StateCheckpoint(
                checkpoint_id=row["checkpoint_id"],
                run_id=row["run_id"],
                task_id=row["task_id"],
                git_commit_hash=row["git_commit_hash"],
                git_branch=row["git_branch"],
                committed_at=row["committed_at"],
            )

    def update_run_status(self, run_id: str, status: str, completed_at: Optional[str] = None) -> None:
        """Update the status and optional completion timestamp of an execution run."""
        with self.get_connection() as conn:
            if completed_at:
                conn.execute(
                    "UPDATE execution_runs SET status = ?, completed_at = ? WHERE run_id = ?",
                    (status, completed_at, run_id),
                )
            else:
                conn.execute(
                    "UPDATE execution_runs SET status = ? WHERE run_id = ?",
                    (status, run_id),
                )

    def update_run_counters(self, run_id: str) -> None:
        """Recalculate task counters for an execution run."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'BLOCKED' THEN 1 ELSE 0 END) as blocked
                FROM tasks WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE execution_runs SET
                        total_tasks = ?,
                        completed_tasks = ?,
                        failed_tasks = ?,
                        blocked_tasks = ?
                    WHERE run_id = ?
                    """,
                    (
                        row["total"] or 0,
                        row["completed"] or 0,
                        row["failed"] or 0,
                        row["blocked"] or 0,
                        run_id,
                    ),
                )

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        retry_count: Optional[int] = None,
        commit_hash: Optional[str] = None,
    ) -> None:
        """Update a task's status, retry count, and commit hash."""
        now = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            query = "UPDATE tasks SET status = ?, updated_at = ?"
            params: list[Any] = [status.value, now]
            if retry_count is not None:
                query += ", retry_count = ?"
                params.append(retry_count)
            if commit_hash is not None:
                query += ", current_commit_hash = ?"
                params.append(commit_hash)
            query += " WHERE task_id = ?"
            params.append(task_id)
            conn.execute(query, params)

    def record_attempt(self, attempt: TaskAttempt) -> None:
        """Record a new task execution attempt."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_attempts (
                    attempt_id, run_id, task_id, attempt_number,
                    prompt_tokens, completion_tokens, model_response, git_diff,
                    outcome, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.attempt_id,
                    attempt.run_id,
                    attempt.task_id,
                    attempt.attempt_number,
                    attempt.prompt_tokens,
                    attempt.completion_tokens,
                    attempt.model_response,
                    attempt.git_diff,
                    attempt.outcome,
                    attempt.started_at,
                    attempt.completed_at,
                ),
            )

    def update_attempt_outcome(
        self,
        attempt_id: str,
        outcome: str,
        completed_at: str,
        model_response: Optional[str] = None,
        git_diff: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Update the final outcome, metrics, and diagnostics of an attempt."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE task_attempts SET
                    outcome = ?,
                    completed_at = ?,
                    model_response = COALESCE(?, model_response),
                    git_diff = COALESCE(?, git_diff),
                    prompt_tokens = CASE WHEN ? > 0 THEN ? ELSE prompt_tokens END,
                    completion_tokens = CASE WHEN ? > 0 THEN ? ELSE completion_tokens END
                WHERE attempt_id = ?
                """,
                (
                    outcome,
                    completed_at,
                    model_response,
                    git_diff,
                    prompt_tokens,
                    prompt_tokens,
                    completion_tokens,
                    completion_tokens,
                    attempt_id,
                ),
            )

    def get_attempts(self, task_id: str) -> list[TaskAttempt]:
        """Fetch all attempts for a given task ordered by attempt number."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM task_attempts WHERE task_id = ? ORDER BY attempt_number ASC",
                (task_id,),
            ).fetchall()
            return [
                TaskAttempt(
                    attempt_id=row["attempt_id"],
                    run_id=row["run_id"],
                    task_id=row["task_id"],
                    attempt_number=row["attempt_number"],
                    prompt_tokens=row["prompt_tokens"],
                    completion_tokens=row["completion_tokens"],
                    model_response=row["model_response"],
                    git_diff=row["git_diff"],
                    outcome=row["outcome"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                )
                for row in rows
            ]

    def get_latest_attempt(self, task_id: str) -> Optional[TaskAttempt]:
        """Fetch the most recent attempt for a task."""
        attempts = self.get_attempts(task_id)
        return attempts[-1] if attempts else None

    def reconcile_and_resume(self, run_id: str, git_manager: GitManagerProtocol) -> ReconciliationResult:
        """
        Reconcile database state with Git commit history upon resumption.
        - Verifies that tasks marked COMPLETED actually have their recorded commit in Git.
        - Resets interrupted tasks (RUNNING / VERIFYING) back to READY.
        - Flags any invalid checkpoints where commits are missing from Git and resets task to READY.
        """
        verified_completed: list[str] = []
        reset_to_ready: list[str] = []
        invalid_checkpoints: list[str] = []

        tasks = self.list_tasks(run_id)
        now = datetime.now(timezone.utc).isoformat()

        with self.get_connection() as conn:
            for task in tasks:
                if task.status == TaskStatus.COMPLETED:
                    row_chk = conn.execute(
                        "SELECT git_commit_hash FROM checkpoints WHERE task_id = ?",
                        (task.task_id,),
                    ).fetchone()
                    commit_hash = row_chk["git_commit_hash"] if row_chk else task.current_commit_hash
                    if commit_hash and git_manager.verify_commit_exists(commit_hash):
                        verified_completed.append(task.task_id)
                    else:
                        # Checkpoint invalid or missing in Git
                        invalid_checkpoints.append(task.task_id)
                        conn.execute(
                            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                            (TaskStatus.READY.value, now, task.task_id),
                        )
                        conn.execute("DELETE FROM checkpoints WHERE task_id = ?", (task.task_id,))
                elif task.status in (TaskStatus.RUNNING, TaskStatus.VERIFYING):
                    # Interrupted during execution
                    reset_to_ready.append(task.task_id)
                    conn.execute(
                        "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                        (TaskStatus.READY.value, now, task.task_id),
                    )

            # Update run status to RUNNING and refresh counters
            conn.execute("UPDATE execution_runs SET status = 'RUNNING' WHERE run_id = ?", (run_id,))
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'BLOCKED' THEN 1 ELSE 0 END) as blocked
                FROM tasks WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE execution_runs SET
                        total_tasks = ?,
                        completed_tasks = ?,
                        failed_tasks = ?,
                        blocked_tasks = ?
                    WHERE run_id = ?
                    """,
                    (
                        row["total"] or 0,
                        row["completed"] or 0,
                        row["failed"] or 0,
                        row["blocked"] or 0,
                        run_id,
                    ),
                )

        return ReconciliationResult(
            run_id=run_id,
            verified_completed=tuple(verified_completed),
            reset_to_ready=tuple(reset_to_ready),
            invalid_checkpoints=tuple(invalid_checkpoints),
        )
