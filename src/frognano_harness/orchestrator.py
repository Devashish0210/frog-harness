"""Central execution orchestrator for Frognano Execution Harness."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional
import uuid

from frognano_harness.approval_manager import HumanApprovalManager
from frognano_harness.audit_ledger import AuditLedger
from frognano_harness.config import HarnessConfig
from frognano_harness.context_manager import ContextManager
from frognano_harness.git_manager import GitManager
from frognano_harness.inference_client import InferenceClient
from frognano_harness.models import (
    ExecutionRun,
    RiskLevel,
    StateCheckpoint,
    Task,
    TaskAttempt,
    TaskStatus,
)
from frognano_harness.policy_engine import PolicyEngine
from frognano_harness.protocols import InferenceBackendProtocol, ToolGatewayProtocol
from frognano_harness.reporting import ReportGenerator
from frognano_harness.runtime import RuntimeAdapters
from frognano_harness.scheduler import TaskScheduler
from frognano_harness.state_manager import StateManager
from frognano_harness.tool_gateway import ToolGateway
from frognano_harness.verification_engine import IndependentVerificationEngine


class ExecutionOrchestrator:
    """Coordinates scheduling, model dispatch, policy gating, tool execution, and verification."""

    def __init__(
        self,
        config: Optional[HarnessConfig] = None,
        repo_root: Optional[Path] = None,
        inference_client: Optional[InferenceBackendProtocol] = None,
        tool_gateway: Optional[ToolGatewayProtocol] = None,
    ) -> None:
        self.config = config or HarnessConfig()
        self.repo_root = (repo_root or Path.cwd()).resolve()

        self.state_manager = StateManager(self.config.db_path)
        self.git_manager = GitManager(self.repo_root)
        self.audit_ledger = AuditLedger(self.state_manager)
        self.inference_client = inference_client or InferenceClient(self.config.model_endpoint, self.config.model_alias)
        self.context_manager = ContextManager(self.config.context_token_budget)
        self.policy_engine = PolicyEngine(project_root=self.repo_root)
        self.approval_manager = HumanApprovalManager(self.state_manager)
        self.runtime = RuntimeAdapters(project_root=self.repo_root)
        self.tool_gateway = tool_gateway or ToolGateway(
            project_root=self.repo_root,
            policy_engine=self.policy_engine,
            approval_manager=self.approval_manager,
            audit_ledger=self.audit_ledger,
            runtime=self.runtime,
        )
        self.verification_engine = IndependentVerificationEngine(project_root=self.repo_root)
        self.reporting = ReportGenerator(self.state_manager, self.git_manager)

    def initialize_run(self, tasks: list[Task]) -> str:
        """Create a new execution run in SQLite and persist initial task states."""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        branch = self.git_manager.get_current_branch() if self.git_manager.is_git_repo() else "main"

        run = ExecutionRun(
            run_id=run_id,
            project_root=str(self.repo_root),
            git_branch=branch,
            model_endpoint=self.config.model_endpoint,
            model_alias=self.config.model_alias,
            started_at=datetime.now(timezone.utc).isoformat(),
            status="RUNNING",
            total_tasks=len(tasks),
        )
        self.state_manager.create_run(run)

        for task in tasks:
            self.state_manager.save_task(run_id, task)

        self.audit_ledger.record_event(
            "RUN_EVENT",
            {"action": "START_RUN", "run_id": run_id, "total_tasks": len(tasks)},
        )
        return run_id

    def execute_task(
        self,
        task: Task,
        run_id: str,
        unattended: bool = False,
        max_retries: int = 2,
    ) -> bool:
        """
        Execute a single task with bounded retries, policy enforcement, and verification.
        Returns True if task succeeded and verified, False if blocked or failed.
        """
        self.state_manager.update_task_status(task.task_id, TaskStatus.RUNNING)
        self.audit_ledger.record_event(
            "TASK_STATE",
            {"task_id": task.task_id, "status": "RUNNING"},
        )

        prior_diagnostics: Optional[dict[str, Any]] = None
        attempt_number = task.retry_count

        while attempt_number <= max_retries:
            attempt_number += 1
            attempt_id = f"att_{uuid.uuid4().hex[:8]}"
            started_at = datetime.now(timezone.utc).isoformat()

            attempt = TaskAttempt(
                attempt_id=attempt_id,
                run_id=run_id,
                task_id=task.task_id,
                attempt_number=attempt_number,
                started_at=started_at,
            )
            self.state_manager.record_attempt(attempt)

            # Build messages
            if attempt_number == 1 or not prior_diagnostics:
                messages = [
                    {
                        "role": "system",
                        "content": "You are FrogNano, an autonomous coding agent. Use available tools to complete the task.",
                    },
                    {
                        "role": "user",
                        "content": self.context_manager.build_task_envelope(task),
                    },
                ]
            else:
                messages = self.context_manager.package_retry_context(task, prior_diagnostics)

            # Dialogue turn loop
            turn_limit = 10
            total_prompt_tokens = 0
            total_completion_tokens = 0
            final_response = ""

            for _ in range(turn_limit):
                try:
                    resp = self.inference_client.generate_completion(
                        messages=messages,
                        tools=self.tool_gateway.get_tool_definitions(),
                        temperature=0.2,
                    )
                except Exception as e:
                    # Model connection error
                    final_response = f"Inference failure: {e}"
                    break

                usage = resp.get("usage", {})
                total_prompt_tokens += usage.get("prompt_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0)

                choice = resp["choices"][0]
                message = choice["message"]
                final_response = message.get("content", "") or ""
                messages.append(message)

                tool_calls = message.get("tool_calls", [])
                if not tool_calls:
                    # Model concluded its turn
                    break

                # Process tool calls strictly through unbypassable ToolGateway facade
                for tc in tool_calls:
                    tc_id = tc["id"]
                    tool_name = tc["function"]["name"]
                    try:
                        raw_args = json.loads(tc["function"]["arguments"])
                    except Exception:
                        raw_args = {}

                    result, auth = self.tool_gateway.dispatch(
                        tool_name=tool_name,
                        arguments=raw_args,
                        allowed_files=task.allowed_files,
                        task_id=task.task_id,
                        attempt_id=attempt_id,
                        unattended=unattended,
                    )
                    content = result.stdout if result.exit_code == 0 else f"EXIT {result.exit_code}: {result.stderr or result.stdout}"
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tool_name,
                            "content": content,
                        }
                    )

            # Verification phase
            diff = self.git_manager.get_diff()
            verif_records, verif_passed = self.verification_engine.verify_task(task)

            completed_at = datetime.now(timezone.utc).isoformat()
            if verif_passed:
                # Stage only allowed files and commit checkpoint
                commit_hash = self.git_manager.commit_task_changes(
                    task_id=task.task_id,
                    title=task.title,
                    files=list(task.allowed_files) if task.allowed_files else None,
                )

                # Record checkpoint in SQLite
                chk_id = f"chk_{uuid.uuid4().hex[:8]}"
                branch = self.git_manager.get_current_branch() if self.git_manager.is_git_repo() else "main"
                self.state_manager.record_checkpoint(
                    StateCheckpoint(
                        checkpoint_id=chk_id,
                        run_id=run_id,
                        task_id=task.task_id,
                        git_commit_hash=commit_hash,
                        git_branch=branch,
                        committed_at=completed_at,
                    )
                )

                self.state_manager.update_attempt_outcome(
                    attempt_id=attempt_id,
                    outcome="SUCCESS",
                    completed_at=completed_at,
                    model_response=final_response,
                    git_diff=diff,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                )

                self.state_manager.update_task_status(
                    task.task_id,
                    TaskStatus.COMPLETED,
                    retry_count=attempt_number - 1,
                    commit_hash=commit_hash,
                )

                self.audit_ledger.record_event(
                    "GIT_CHECKPOINT",
                    {"task_id": task.task_id, "commit_hash": commit_hash, "branch": branch},
                )
                self.audit_ledger.record_event(
                    "TASK_STATE",
                    {"task_id": task.task_id, "status": "COMPLETED"},
                )
                return True
            else:
                # Verification failed
                self.state_manager.update_attempt_outcome(
                    attempt_id=attempt_id,
                    outcome="FAILED",
                    completed_at=completed_at,
                    model_response=final_response,
                    git_diff=diff,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                )
                self.state_manager.update_task_status(
                    task.task_id,
                    TaskStatus.RUNNING,
                    retry_count=attempt_number,
                )

                # Collect error diagnostics for retry
                first_failed = next((r for r in verif_records if r.outcome.value == "FAILED"), None)
                prior_diagnostics = {
                    "exit_code": first_failed.exit_code if first_failed else 1,
                    "stdout": first_failed.stdout if first_failed else "",
                    "stderr": first_failed.stderr if first_failed else "Verification failed",
                    "git_diff": diff,
                }

        # Exhausted retries -> BLOCKED
        self.state_manager.update_task_status(task.task_id, TaskStatus.BLOCKED, retry_count=max_retries)
        self.audit_ledger.record_event(
            "TASK_STATE",
            {"task_id": task.task_id, "status": "BLOCKED", "reason": "Exceeded maximum retry limit"},
        )
        return False

    def run_all(self, run_id: str, unattended: bool = False, max_retries: int = 2) -> bool:
        """Run all ready tasks sequentially through topological DAG order."""
        all_tasks = self.state_manager.list_tasks(run_id)
        scheduler = TaskScheduler(all_tasks)

        while True:
            ready_tasks = scheduler.get_ready_tasks()
            if not ready_tasks:
                break

            task = ready_tasks[0]
            success = self.execute_task(task, run_id, unattended=unattended, max_retries=max_retries)

            if success:
                scheduler.mark_task_completed(task.task_id)
            else:
                # Cascade blocked status to dependents
                blocked_ids = scheduler.mark_task_blocked(task.task_id)
                for bid in blocked_ids:
                    if bid != task.task_id:
                        self.state_manager.update_task_status(bid, TaskStatus.BLOCKED)
                        self.audit_ledger.record_event(
                            "TASK_STATE",
                            {"task_id": bid, "status": "BLOCKED", "reason": f"Prerequisite {task.task_id} failed"},
                        )

            self.state_manager.update_run_counters(run_id)

        # Export final reports
        self.reporting.export_reports(run_id)

        # Update run status
        tasks = self.state_manager.list_tasks(run_id)
        if all(t.status == TaskStatus.COMPLETED for t in tasks):
            self.state_manager.update_run_status(run_id, "COMPLETED", completed_at=datetime.now(timezone.utc).isoformat())
            return True
        else:
            self.state_manager.update_run_status(run_id, "FAILED", completed_at=datetime.now(timezone.utc).isoformat())
            return False
