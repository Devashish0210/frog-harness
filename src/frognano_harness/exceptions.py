"""Domain exceptions for Frognano Local Execution Harness."""

from typing import Any, Optional


class HarnessError(Exception):
    """Base exception for all harness operations."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PolicyViolationError(HarnessError):
    """Raised when an operation is denied by the Policy Engine."""

    def __init__(self, message: str, policy_rule: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, details)
        self.policy_rule = policy_rule


class ApprovalRequiredError(HarnessError):
    """Raised when an operation requires explicit human approval before execution."""

    def __init__(self, message: str, approval_id: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, details)
        self.approval_id = approval_id


class VerificationFailedError(HarnessError):
    """Raised when an independent verification check fails."""

    def __init__(self, message: str, command: str, exit_code: int, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, details)
        self.command = command
        self.exit_code = exit_code


class BlockedTaskError(HarnessError):
    """Raised when a task cannot proceed and must be escalated for replanning."""

    def __init__(self, message: str, task_id: str, reason: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, details)
        self.task_id = task_id
        self.reason = reason


class SpecParsingError(HarnessError):
    """Raised when a SpecKit tasks.md or spec file is invalid or missing required fields."""
    pass


class CyclicDependencyError(HarnessError):
    """Raised when a dependency cycle is detected in the task graph."""
    pass
