-- SQLite Database Schema for Frognano Local Execution Harness
-- Location: .harness/state.db
-- Version: 1.0.0

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- Schema Version Migration Tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Execution Runs (a single invocation session)
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

-- Tasks parsed from tasks.md
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    description TEXT NOT NULL,
    dependencies_json TEXT NOT NULL,         -- JSON array of prerequisite task_ids
    allowed_files_json TEXT NOT NULL,        -- JSON array of relative file paths
    acceptance_criteria_json TEXT NOT NULL,  -- JSON array of acceptance strings
    verification_commands_json TEXT NOT NULL,-- JSON array of verification command strings
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'READY', 'RUNNING', 'PENDING_APPROVAL', 'VERIFYING', 'SUCCESS', 'COMPLETED', 'FAILED', 'BLOCKED')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    current_commit_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES execution_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_run_id ON tasks(run_id);

-- Individual Task Execution Attempts
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

-- Tool Calls Requested by the Model
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

-- Policy and Authorization Decisions
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

-- Human Approval Requests (holds on high-risk operations)
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

-- Tool Execution Results (actual executed actions)
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

-- Independent Verification Records
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

-- State Checkpoints (Git commits linked to successfully completed tasks)
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

-- Immutable Append-Only Hash-Chained Audit Ledger
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

-- Triggers enforcing physical append-only immutability
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
