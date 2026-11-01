"""Command Line Interface for Frognano Execution Harness."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Optional

from frognano_harness.approval_manager import HumanApprovalManager
from frognano_harness.audit_ledger import AuditLedger
from frognano_harness.config import HarnessConfig, load_config
from frognano_harness.git_manager import GitManager
from frognano_harness.models import ApprovalStatus, TaskStatus
from frognano_harness.orchestrator import ExecutionOrchestrator
from frognano_harness.reporting import ReportGenerator
from frognano_harness.scheduler import TaskScheduler
from frognano_harness.state_manager import StateManager
from frognano_harness.task_parser import TaskParser
from frognano_harness.verification_engine import IndependentVerificationEngine


def build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for the 14 harness CLI commands."""
    parser = argparse.ArgumentParser(
        prog="harness",
        description="Frognano Autonomous Execution Harness CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. init
    p_init = subparsers.add_parser("init", help="Initialize harness configuration and .harness/ directory")
    p_init.add_argument("--endpoint", type=str, default="http://127.0.0.1:8080/v1", help="Inference endpoint URL")
    p_init.add_argument("--model", type=str, default="frognano", help="Model alias")
    p_init.add_argument("--force", action="store_true", help="Force overwrite existing configuration")

    # 2. validate
    p_validate = subparsers.add_parser("validate", help="Discover and validate tasks.md and DAG cycle freedom")
    p_validate.add_argument("--tasks", type=str, default="specs/002-local-execution-harness/tasks.md", help="Path to tasks.md")
    p_validate.add_argument("--json", action="store_true", help="Output results as JSON")

    # 3. plan
    p_plan = subparsers.add_parser("plan", help="Display topological DAG execution order")
    p_plan.add_argument("--tasks", type=str, default="specs/002-local-execution-harness/tasks.md", help="Path to tasks.md")
    p_plan.add_argument("--ascii", action="store_true", help="Render ASCII execution tree")
    p_plan.add_argument("--json", action="store_true", help="Output topological order as JSON")

    # 4. run
    p_run = subparsers.add_parser("run", help="Execute ready tasks in sequential topological order")
    p_run.add_argument("--tasks", type=str, default="specs/002-local-execution-harness/tasks.md", help="Path to tasks.md")
    p_run.add_argument("--task", type=str, default=None, help="Execute specific task only")
    p_run.add_argument("--max-retries", type=int, default=2, help="Maximum retry attempts per task")
    p_run.add_argument("--unattended", action="store_true", help="Run unattended without interactive prompts")
    p_run.add_argument("--timeout", type=int, default=180, help="Timeout in seconds")

    # 5. resume
    p_resume = subparsers.add_parser("resume", help="Reconcile state against Git and resume execution")
    p_resume.add_argument("--run-id", type=str, default=None, help="Specific run ID to resume")
    p_resume.add_argument("--unattended", action="store_true", help="Run unattended")

    # 6. status
    p_status = subparsers.add_parser("status", help="Display overall run progress and task queues")
    p_status.add_argument("--json", action="store_true", help="Output status as JSON")
    p_status.add_argument("--watch", action="store_true", help="Continuously poll status")

    # 7. task
    p_task = subparsers.add_parser("task", help="Display detailed inspection of a specific task")
    p_task.add_argument("task_id", type=str, help="Task ID to inspect")
    p_task.add_argument("--json", action="store_true", help="Output as JSON")

    # 8. retry
    p_retry = subparsers.add_parser("retry", help="Reset retry count and re-queue a BLOCKED or FAILED task")
    p_retry.add_argument("task_id", type=str, help="Task ID to retry")
    p_retry.add_argument("--force", action="store_true", help="Force reset regardless of status")

    # 9. approve
    p_approve = subparsers.add_parser("approve", help="Authorize a pending high-risk tool operation")
    p_approve.add_argument("approval_id", type=str, help="Approval ID to authorize")

    # 10. reject
    p_reject = subparsers.add_parser("reject", help="Reject a pending high-risk tool operation")
    p_reject.add_argument("approval_id", type=str, help="Approval ID to reject")
    p_reject.add_argument("--reason", type=str, default="Rejected by operator", help="Rejection rationale")

    # 11. report
    p_report = subparsers.add_parser("report", help="Generate structured JSON and Markdown execution reports")
    p_report.add_argument("--output", type=str, default=None, help="Output directory")
    p_report.add_argument("--format", type=str, choices=["json", "md", "both"], default="both", help="Report format")

    # 12. logs
    p_logs = subparsers.add_parser("logs", help="View structured execution traces and tool outputs")
    p_logs.add_argument("task_id", type=str, help="Task ID")
    p_logs.add_argument("--tail", type=int, default=50, help="Number of lines to tail")
    p_logs.add_argument("--tool", type=str, default=None, help="Filter by tool name")

    # 13. verify
    p_verify = subparsers.add_parser("verify", help="Independently re-run verification commands without model")
    p_verify.add_argument("task_id", type=str, nargs="?", default=None, help="Task ID to verify")
    p_verify.add_argument("--all", action="store_true", help="Verify all tasks")

    # 14. audit
    p_audit = subparsers.add_parser("audit", help="Verify hash-chain cryptographic integrity")
    p_audit.add_argument("--verify-chain", action="store_true", help="Verify cryptographic hash chain")
    p_audit.add_argument("--tool-call", type=str, default=None, help="Inspect specific tool call audit entry")
    p_audit.add_argument("--json", action="store_true", help="Output audit events as JSON")

    return parser


def get_state_manager(repo_root: Optional[Path] = None) -> StateManager:
    """Resolve StateManager dynamically using workspace configuration."""
    config = load_config(repo_root or Path.cwd())
    return StateManager(config.db_path)


def handle_init(args: argparse.Namespace) -> int:
    harness_dir = Path(".harness")
    harness_dir.mkdir(parents=True, exist_ok=True)
    config_file = harness_dir / "config.json"

    if config_file.exists() and not args.force:
        print(f"Error: {config_file} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    config = {
        "model_endpoint": args.endpoint,
        "model_alias": args.model,
        "context_token_budget": 65536,
        "max_retries": 2,
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    db_path = harness_dir / "state.db"
    StateManager(db_path)
    print(f"Initialized Frognano Execution Harness in {harness_dir}")
    return 0


def handle_validate(args: argparse.Namespace) -> int:
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"Error: Tasks file {tasks_path} not found.", file=sys.stderr)
        return 1

    tasks = TaskParser.parse_file(tasks_path)
    if not tasks:
        print(f"Error: No tasks found in {tasks_path}.", file=sys.stderr)
        return 1

    scheduler = TaskScheduler(tasks)
    is_valid, msg = scheduler.validate_dag()

    if args.json:
        print(json.dumps({"valid": is_valid, "task_count": len(tasks), "message": msg}))
    else:
        status_str = "VALID" if is_valid else "INVALID"
        print(f"SpecKit Validation: [{status_str}] - {len(tasks)} tasks parsed. {msg}")

    return 0 if is_valid else 1


def handle_plan(args: argparse.Namespace) -> int:
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"Error: Tasks file {tasks_path} not found.", file=sys.stderr)
        return 1

    tasks = TaskParser.parse_file(tasks_path)
    scheduler = TaskScheduler(tasks)
    is_valid, msg = scheduler.validate_dag()
    if not is_valid:
        print(f"DAG Error: {msg}", file=sys.stderr)
        return 1

    topological_order = scheduler.get_topological_order()

    if args.json:
        data = [
            {
                "task_id": t.task_id,
                "title": t.title,
                "dependencies": list(t.dependencies),
                "allowed_files": list(t.allowed_files),
            }
            for t in topological_order
        ]
        print(json.dumps(data, indent=2))
    else:
        print(f"Topological Task Execution Plan ({len(topological_order)} tasks):")
        for i, t in enumerate(topological_order, 1):
            deps = f" (prerequisites: {', '.join(t.dependencies)})" if t.dependencies else ""
            print(f"  {i:02d}. [{t.task_id}] {t.title}{deps}")

    return 0


def handle_run(args: argparse.Namespace) -> int:
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"Error: Tasks file {tasks_path} not found.", file=sys.stderr)
        return 1

    tasks = TaskParser.parse_file(tasks_path)
    orchestrator = ExecutionOrchestrator()
    run_id = orchestrator.initialize_run(tasks)
    print(f"Started execution run: {run_id}")

    if args.task:
        target = next((t for t in tasks if t.task_id == args.task), None)
        if not target:
            print(f"Error: Task {args.task} not found.", file=sys.stderr)
            return 1
        success = orchestrator.execute_task(target, run_id, unattended=args.unattended, max_retries=args.max_retries)
        return 0 if success else 1

    success = orchestrator.run_all(run_id, unattended=args.unattended, max_retries=args.max_retries)
    return 0 if success else 1


def handle_resume(args: argparse.Namespace) -> int:
    orchestrator = ExecutionOrchestrator()
    run_id = args.run_id
    if not run_id:
        with orchestrator.state_manager.get_connection() as conn:
            row = conn.execute("SELECT run_id FROM execution_runs ORDER BY started_at DESC LIMIT 1").fetchone()
            if not row:
                print("Error: No execution run found to resume.", file=sys.stderr)
                return 1
            run_id = row["run_id"]

    reconciliation = orchestrator.state_manager.reconcile_and_resume(run_id, orchestrator.git_manager)
    print(f"Resuming run {run_id}:")
    print(f"  - Verified completed: {len(reconciliation.verified_completed)}")
    print(f"  - Reset to ready: {len(reconciliation.reset_to_ready)}")
    if reconciliation.invalid_checkpoints:
        print(f"  - Invalid checkpoints reset: {len(reconciliation.invalid_checkpoints)}")

    success = orchestrator.run_all(run_id, unattended=args.unattended)
    return 0 if success else 1


def handle_status(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    with sm.get_connection() as conn:
        row = conn.execute("SELECT run_id, status, total_tasks, completed_tasks, failed_tasks, blocked_tasks FROM execution_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            print("No active or historical execution run found.")
            return 0

        run_id = row["run_id"]
        tasks = sm.list_tasks(run_id)

    if args.json:
        data = {
            "run_id": run_id,
            "status": row["status"],
            "total_tasks": row["total_tasks"],
            "completed_tasks": row["completed_tasks"],
            "failed_tasks": row["failed_tasks"],
            "blocked_tasks": row["blocked_tasks"],
            "tasks": [{"task_id": t.task_id, "title": t.title, "status": t.status.value} for t in tasks],
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Run {run_id} [{row['status']}]: {row['completed_tasks']}/{row['total_tasks']} completed, {row['blocked_tasks']} blocked, {row['failed_tasks']} failed")
        for t in tasks:
            print(f"  [{t.status.value:10s}] {t.task_id}: {t.title}")

    return 0


def handle_task(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    task = sm.get_task(args.task_id)
    if not task:
        print(f"Error: Task {args.task_id} not found.", file=sys.stderr)
        return 1

    attempts = sm.get_attempts(args.task_id)

    if args.json:
        data = {
            "task_id": task.task_id,
            "title": task.title,
            "objective": task.objective,
            "status": task.status.value,
            "retry_count": task.retry_count,
            "commit_hash": task.current_commit_hash,
            "attempts": [
                {
                    "attempt_number": a.attempt_number,
                    "outcome": a.outcome,
                    "prompt_tokens": a.prompt_tokens,
                    "completion_tokens": a.completion_tokens,
                }
                for a in attempts
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Task: {task.task_id} - {task.title}")
        print(f"Status: {task.status.value} | Retries: {task.retry_count} | Commit: {task.current_commit_hash or 'None'}")
        print(f"Objective: {task.objective}")
        print(f"Allowed files: {', '.join(task.allowed_files)}")
        print(f"Attempts recorded: {len(attempts)}")

    return 0


def handle_retry(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    task = sm.get_task(args.task_id)
    if not task:
        print(f"Error: Task {args.task_id} not found.", file=sys.stderr)
        return 1

    if task.status not in (TaskStatus.BLOCKED, TaskStatus.FAILED) and not args.force:
        print(f"Error: Task {args.task_id} is in status {task.status.value}. Use --force to reset.", file=sys.stderr)
        return 1

    sm.update_task_status(args.task_id, TaskStatus.READY, retry_count=0)
    print(f"Task {args.task_id} reset to READY (retries reset to 0).")
    return 0


def handle_approve(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    mgr = HumanApprovalManager(sm)
    approval = mgr.resolve_approval(args.approval_id, ApprovalStatus.APPROVED, resolved_by="operator")
    if not approval:
        print(f"Error: Approval {args.approval_id} not found.", file=sys.stderr)
        return 1

    print(f"Approval {args.approval_id} APPROVED.")
    return 0


def handle_reject(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    mgr = HumanApprovalManager(sm)
    approval = mgr.resolve_approval(args.approval_id, ApprovalStatus.REJECTED, resolved_by="operator")
    if not approval:
        print(f"Error: Approval {args.approval_id} not found.", file=sys.stderr)
        return 1

    print(f"Approval {args.approval_id} REJECTED: {args.reason}")
    return 0


def handle_report(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    git = GitManager()
    output_dir = Path(args.output) if args.output else None
    rep = ReportGenerator(sm, git, reports_dir=output_dir)

    with sm.get_connection() as conn:
        row = conn.execute("SELECT run_id FROM execution_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            print("Error: No execution run found to report.", file=sys.stderr)
            return 1
        run_id = row["run_id"]

    json_path, md_path = rep.export_reports(run_id)
    print(f"Reports generated successfully:")
    if args.format in ("json", "both"):
        print(f"  JSON: {json_path}")
    if args.format in ("md", "both"):
        print(f"  Markdown: {md_path}")

    return 0


def handle_logs(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    attempts = sm.get_attempts(args.task_id)
    if not attempts:
        print(f"No execution attempts recorded for {args.task_id}.")
        return 0

    for a in attempts:
        print(f"--- Attempt {a.attempt_number} [{a.outcome}] ---")
        if a.model_response:
            print("Model Response:\n" + a.model_response[:500])
        if a.git_diff:
            print("Git Diff:\n" + a.git_diff[:500])

    return 0


def handle_verify(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    verif = IndependentVerificationEngine()

    if args.all:
        tasks = sm.list_tasks()
        all_passed = True
        for t in tasks:
            records, passed = verif.verify_task(t)
            print(f"[{'PASS' if passed else 'FAIL'}] {t.task_id}: {t.title}")
            if not passed:
                all_passed = False
        return 0 if all_passed else 1

    if not args.task_id:
        print("Error: Specify a task_id or --all.", file=sys.stderr)
        return 1

    task = sm.get_task(args.task_id)
    if not task:
        print(f"Error: Task {args.task_id} not found.", file=sys.stderr)
        return 1

    records, passed = verif.verify_task(task)
    for r in records:
        print(f"  [{r.outcome.value}] {r.command} (exit {r.exit_code})")
    print(f"Verification for {args.task_id}: {'PASSED' if passed else 'FAILED'}")
    return 0 if passed else 1


def handle_audit(args: argparse.Namespace) -> int:
    sm = get_state_manager()
    ledger = AuditLedger(sm)

    if args.verify_chain:
        is_valid, count, err = ledger.verify_chain()
        if is_valid:
            print(f"Audit Chain Integrity: VERIFIED ({count} entries checked, 0 errors)")
            return 0
        else:
            print(f"Audit Chain Integrity: TAMPERED ({count} entries checked) - {err}", file=sys.stderr)
            return 1

    events = ledger.get_events()
    if args.json:
        data = [
            {
                "id": e.id,
                "entry_id": e.entry_id,
                "event_type": e.event_type,
                "prev_hash": e.prev_entry_hash,
                "hash": e.entry_hash,
                "timestamp": e.created_at,
            }
            for e in events
        ]
        print(json.dumps(data, indent=2))
    else:
        print(f"Audit Ledger ({len(events)} events):")
        for e in events[-20:]:
            print(f"  [{e.id:03d}] {e.event_type:20s} hash={e.entry_hash[:12]}...")

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point dispatching to command handlers."""
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "init": handle_init,
        "validate": handle_validate,
        "plan": handle_plan,
        "run": handle_run,
        "resume": handle_resume,
        "status": handle_status,
        "task": handle_task,
        "retry": handle_retry,
        "approve": handle_approve,
        "reject": handle_reject,
        "report": handle_report,
        "logs": handle_logs,
        "verify": handle_verify,
        "audit": handle_audit,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
