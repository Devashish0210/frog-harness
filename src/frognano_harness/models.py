"""Domain entities, enums, and data models for Frognano Execution Harness."""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Any, Optional


class TaskStatus(str, Enum):
    """Lifecycle states of a task in the execution graph."""
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    VERIFYING = "VERIFYING"
    SUCCESS = "SUCCESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class DecisionType(str, Enum):
    """Policy evaluation outcomes."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class RiskLevel(str, Enum):
    """Risk classification for tool execution requests."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ApprovalStatus(str, Enum):
    """State of an interactive or pending human approval request."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class AttemptOutcome(str, Enum):
    """Outcome of an individual model task attempt."""
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    TIMED_OUT = "TIMED_OUT"


class VerificationOutcome(str, Enum):
    """Result of independent verification command execution."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


TASK_ID_REGEX = re.compile(r"^[A-Z0-9_-]+$")


@dataclass(frozen=True)
class Task:
    """The structured unit of work parsed from SpecKit tasks.md."""
    task_id: str
    title: str
    objective: str
    description: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    allowed_files: tuple[str, ...] = field(default_factory=tuple)
    acceptance_criteria: tuple[str, ...] = field(default_factory=tuple)
    verification_commands: tuple[str, ...] = field(default_factory=tuple)
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    current_commit_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if not TASK_ID_REGEX.match(self.task_id):
            raise ValueError(f"Invalid task_id '{self.task_id}'. Must match ^[A-Z0-9_-]+$")
        if not self.objective.strip():
            raise ValueError("Task objective must not be empty.")
        if self.retry_count < 0:
            raise ValueError("retry_count cannot be negative.")

    def with_status(self, new_status: TaskStatus, commit_hash: Optional[str] = None) -> "Task":
        return Task(
            task_id=self.task_id,
            title=self.title,
            objective=self.objective,
            description=self.description,
            dependencies=self.dependencies,
            allowed_files=self.allowed_files,
            acceptance_criteria=self.acceptance_criteria,
            verification_commands=self.verification_commands,
            status=new_status,
            retry_count=self.retry_count,
            current_commit_hash=commit_hash or self.current_commit_hash,
        )

    def with_incremented_retry(self) -> "Task":
        return Task(
            task_id=self.task_id,
            title=self.title,
            objective=self.objective,
            description=self.description,
            dependencies=self.dependencies,
            allowed_files=self.allowed_files,
            acceptance_criteria=self.acceptance_criteria,
            verification_commands=self.verification_commands,
            status=self.status,
            retry_count=self.retry_count + 1,
            current_commit_hash=self.current_commit_hash,
        )


@dataclass(frozen=True)
class ExecutionRun:
    """A single invocation session of the execution harness."""
    run_id: str
    project_root: str
    git_branch: str
    model_endpoint: str
    model_alias: str
    started_at: str
    status: str = "INITIALIZING"
    completed_at: Optional[str] = None
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    blocked_tasks: int = 0


@dataclass(frozen=True)
class TaskAttempt:
    """An individual execution cycle for a task."""
    attempt_id: str
    run_id: str
    task_id: str
    attempt_number: int
    started_at: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_response: Optional[str] = None
    git_diff: Optional[str] = None
    outcome: AttemptOutcome = AttemptOutcome.IN_PROGRESS
    completed_at: Optional[str] = None


@dataclass(frozen=True)
class ToolCallRequest:
    """A model-generated request to execute an operational tool."""
    tool_call_id: str
    attempt_id: str
    task_id: str
    tool_name: str
    raw_arguments: dict[str, Any]
    normalized_arguments: dict[str, Any]
    arguments_hash: str
    requested_at: str

    @staticmethod
    def compute_args_hash(normalized_args: dict[str, Any]) -> str:
        serialized = json.dumps(normalized_args, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthorizationDecision:
    """Deterministic policy ruling for a tool request."""
    decision_id: str
    tool_call_id: str
    decision: DecisionType
    risk_level: RiskLevel
    policy_rule: str
    reason: str
    decided_at: str


@dataclass(frozen=True)
class ApprovalRequest:
    """An interactive hold on a high-risk operation."""
    approval_id: str
    tool_call_id: str
    task_id: str
    operation: str
    exact_arguments: dict[str, Any]
    arguments_hash: str
    risk_level: RiskLevel
    status: ApprovalStatus
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None


@dataclass(frozen=True)
class ToolExecutionEvent:
    """The recorded execution of an authorized tool."""
    execution_id: str
    tool_call_id: str
    exit_code: int
    stdout: str
    stderr: str
    affected_files: tuple[str, ...]
    duration_ms: int
    result_hash: str
    executed_at: str


@dataclass(frozen=True)
class VerificationRecord:
    """The recorded outcome of verification checks for an attempt."""
    verification_id: str
    attempt_id: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    outcome: VerificationOutcome
    verified_at: str


@dataclass(frozen=True)
class AuditEntry:
    """An immutable, hash-linked log entry in SQLite."""
    entry_id: str
    prev_entry_hash: str
    entry_hash: str
    event_type: str
    payload_json: str
    created_at: str
    id: Optional[int] = None

    @staticmethod
    def compute_hash(prev_hash: str, event_type: str, payload_json: str, created_at: str) -> str:
        content = f"{prev_hash}|{event_type}|{payload_json}|{created_at}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StateCheckpoint:
    """Durable tracking mapping tasks to their Git commit hashes."""
    checkpoint_id: str
    run_id: str
    task_id: str
    git_commit_hash: str
    git_branch: str
    committed_at: str


@dataclass(frozen=True)
class ReconciliationResult:
    """Outcome of reconciling database state with Git commit history upon resumption."""
    run_id: str
    verified_completed: tuple[str, ...]
    reset_to_ready: tuple[str, ...]
    invalid_checkpoints: tuple[str, ...]
