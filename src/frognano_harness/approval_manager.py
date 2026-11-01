"""Human Approval Manager: manages operator authorization holds on high-risk operations."""

from datetime import datetime, timezone
import hashlib
import json
import sys
from typing import Any, Optional
import uuid

from frognano_harness.exceptions import HarnessError
from frognano_harness.models import ApprovalRequest, ApprovalStatus, RiskLevel
from frognano_harness.state_manager import StateManager


class HumanApprovalManager:
    """Handles authorization requests, interactive CLI prompting, and approval records."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    def create_approval_request(
        self,
        tool_call_id: str,
        task_id: str,
        operation: str,
        exact_arguments: dict[str, Any],
        risk_level: RiskLevel,
    ) -> ApprovalRequest:
        """Create and persist a pending human approval request."""
        now = datetime.now(timezone.utc).isoformat()
        approval_id = f"APP-{uuid.uuid4().hex[:8].upper()}"

        serialized_args = json.dumps(exact_arguments, sort_keys=True, separators=(",", ":"))
        args_hash = hashlib.sha256(serialized_args.encode("utf-8")).hexdigest()

        req = ApprovalRequest(
            approval_id=approval_id,
            tool_call_id=tool_call_id,
            task_id=task_id,
            operation=operation,
            exact_arguments=exact_arguments,
            arguments_hash=args_hash,
            risk_level=risk_level,
            status=ApprovalStatus.PENDING,
            created_at=now,
        )

        with self.state_manager.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO approvals (
                    approval_id, tool_call_id, task_id, operation, exact_arguments_json,
                    arguments_hash, risk_level, status, created_at, resolved_at, resolved_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req.approval_id, req.tool_call_id, req.task_id, req.operation,
                    serialized_args, req.arguments_hash, req.risk_level.value,
                    req.status.value, req.created_at, req.resolved_at, req.resolved_by
                )
            )

        return req

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        """List all requests in PENDING status."""
        with self.state_manager.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at ASC",
                (ApprovalStatus.PENDING.value,)
            ).fetchall()

            return [
                ApprovalRequest(
                    approval_id=row["approval_id"],
                    tool_call_id=row["tool_call_id"],
                    task_id=row["task_id"],
                    operation=row["operation"],
                    exact_arguments=json.loads(row["exact_arguments_json"]),
                    arguments_hash=row["arguments_hash"],
                    risk_level=RiskLevel(row["risk_level"]),
                    status=ApprovalStatus(row["status"]),
                    created_at=row["created_at"],
                    resolved_at=row["resolved_at"],
                    resolved_by=row["resolved_by"],
                )
                for row in rows
            ]

    def approve_request(self, approval_id: str, resolved_by: str = "operator") -> ApprovalRequest:
        """Approve a pending authorization request."""
        now = datetime.now(timezone.utc).isoformat()
        with self.state_manager.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            if not row:
                raise HarnessError(f"Approval request not found: {approval_id}")

            conn.execute(
                """
                UPDATE approvals
                SET status = ?, resolved_at = ?, resolved_by = ?
                WHERE approval_id = ?
                """,
                (ApprovalStatus.APPROVED.value, now, resolved_by, approval_id)
            )

        return ApprovalRequest(
            approval_id=row["approval_id"],
            tool_call_id=row["tool_call_id"],
            task_id=row["task_id"],
            operation=row["operation"],
            exact_arguments=json.loads(row["exact_arguments_json"]),
            arguments_hash=row["arguments_hash"],
            risk_level=RiskLevel(row["risk_level"]),
            status=ApprovalStatus.APPROVED,
            created_at=row["created_at"],
            resolved_at=now,
            resolved_by=resolved_by,
        )

    def reject_request(
        self, approval_id: str, reason: str = "", resolved_by: str = "operator"
    ) -> ApprovalRequest:
        """Reject a pending authorization request."""
        now = datetime.now(timezone.utc).isoformat()
        with self.state_manager.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            if not row:
                raise HarnessError(f"Approval request not found: {approval_id}")

            conn.execute(
                """
                UPDATE approvals
                SET status = ?, resolved_at = ?, resolved_by = ?
                WHERE approval_id = ?
                """,
                (ApprovalStatus.REJECTED.value, now, resolved_by, approval_id)
            )

        return ApprovalRequest(
            approval_id=row["approval_id"],
            tool_call_id=row["tool_call_id"],
            task_id=row["task_id"],
            operation=row["operation"],
            exact_arguments=json.loads(row["exact_arguments_json"]),
            arguments_hash=row["arguments_hash"],
            risk_level=RiskLevel(row["risk_level"]),
            status=ApprovalStatus.REJECTED,
            created_at=row["created_at"],
            resolved_at=now,
            resolved_by=resolved_by,
        )

    def prompt_inline_approval(self, request: ApprovalRequest, timeout_sec: int = 60) -> bool:
        """Prompt operator interactively in the terminal if interactive, else leave pending."""
        if not sys.stdin.isatty():
            return False

        print("\n" + "=" * 60)
        print(f"[SECURITY HOLD] High-risk operation requires human authorization: {request.approval_id}")
        print(f"Task: {request.task_id} | Operation: {request.operation} | Risk: {request.risk_level.value}")
        print(f"Arguments: {json.dumps(request.exact_arguments, indent=2)}")
        print("=" * 60)

        try:
            choice = input(f"Authorize execution of {request.approval_id}? [y/N]: ").strip().lower()
            if choice in ("y", "yes"):
                self.approve_request(request.approval_id, resolved_by="interactive-user")
                return True
            else:
                self.reject_request(request.approval_id, reason="Operator denied inline", resolved_by="interactive-user")
                return False
        except (KeyboardInterrupt, EOFError):
            return False

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Fetch approval by ID."""
        with self.state_manager.get_connection() as conn:
            row = conn.execute("SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)).fetchone()
            if not row:
                return None
            return ApprovalRequest(
                approval_id=row["approval_id"],
                tool_call_id=row["tool_call_id"],
                task_id=row["task_id"],
                operation=row["operation"],
                exact_arguments=json.loads(row["exact_arguments_json"]),
                arguments_hash=row["arguments_hash"],
                risk_level=RiskLevel(row["risk_level"]),
                status=ApprovalStatus(row["status"]),
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
                resolved_by=row["resolved_by"],
            )

    def resolve_approval(
        self,
        approval_id: str,
        status: ApprovalStatus,
        reason: Optional[str] = None,
        resolved_by: str = "operator",
    ) -> Optional[ApprovalRequest]:
        """Resolve an approval to either APPROVED or REJECTED."""
        if status == ApprovalStatus.APPROVED:
            try:
                return self.approve_request(approval_id, resolved_by=resolved_by)
            except HarnessError:
                return None
        elif status == ApprovalStatus.REJECTED:
            try:
                return self.reject_request(approval_id, reason=reason or "Rejected", resolved_by=resolved_by)
            except HarnessError:
                return None
        return None

    def request_approval(
        self,
        tool_call_id: str,
        task_id: str,
        operation: str,
        arguments: dict[str, Any],
        risk_level: RiskLevel,
        auto_prompt: bool = True,
    ) -> ApprovalRequest:
        """Create and optionally prompt interactively for an approval."""
        req = self.create_approval_request(
            tool_call_id=tool_call_id,
            task_id=task_id,
            operation=operation,
            exact_arguments=arguments,
            risk_level=risk_level,
        )
        if auto_prompt and sys.stdin.isatty():
            self.prompt_inline_approval(req)
            return self.get_approval(req.approval_id) or req
        return req
