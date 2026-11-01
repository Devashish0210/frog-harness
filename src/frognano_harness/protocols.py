"""Typed protocol interfaces for decoupling and testing."""

from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from frognano_harness.models import (
    AuthorizationDecision,
    Task,
    VerificationRecord,
)
from frognano_harness.runtime import ToolResult


@runtime_checkable
class GitManagerProtocol(Protocol):
    """Interface for Git version control and repository operations."""

    def is_git_repo(self) -> bool:
        ...

    def get_current_branch(self) -> str:
        ...

    def get_head_commit(self) -> str:
        ...

    def has_uncommitted_changes(self) -> bool:
        ...

    def get_status(self) -> str:
        ...

    def get_diff(self, cached: bool = False, path: Optional[str] = None) -> str:
        ...

    def commit_task_changes(self, task_id: str, title: str, files: Optional[list[str]] = None) -> str:
        ...

    def verify_commit_exists(self, commit_hash: str) -> bool:
        ...


@runtime_checkable
class InferenceBackendProtocol(Protocol):
    """Interface for OpenAI-compatible model inference endpoints."""

    def generate_completion(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        ...


@runtime_checkable
class PolicyEngineProtocol(Protocol):
    """Interface for policy authorization and sandbox evaluation."""

    def evaluate(
        self,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
        args: Optional[dict[str, Any]] = None,
        task: Optional[Task] = None,
        allowed_files: Optional[tuple[str, ...]] = None,
    ) -> AuthorizationDecision:
        ...


@runtime_checkable
class ToolGatewayProtocol(Protocol):
    """Interface for sandboxed tool dispatch and execution."""

    def dispatch(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        allowed_files: tuple[str, ...],
        task_id: str,
        attempt_id: str,
        unattended: bool = False,
    ) -> tuple[ToolResult, AuthorizationDecision]:
        ...

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        ...


@runtime_checkable
class VerificationEngineProtocol(Protocol):
    """Interface for independent test runner execution."""

    def verify_task(
        self,
        task: Task,
        attempt_id: Optional[str] = None,
    ) -> tuple[list[VerificationRecord], bool]:
        ...
