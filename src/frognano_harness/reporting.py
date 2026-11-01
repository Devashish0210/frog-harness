"""Supervisory execution reporting for Gemini and human operators."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional

from frognano_harness.git_manager import GitManager
from frognano_harness.models import TaskStatus
from frognano_harness.state_manager import StateManager


class ReportGenerator:
    """Generates supervisory reports conforming to contracts/report-schema.json."""

    def __init__(
        self,
        state_manager: StateManager,
        git_manager: GitManager,
        project_name: str = "Frognano-harness",
        reports_dir: Optional[Path] = None,
    ) -> None:
        self.state_manager = state_manager
        self.git_manager = git_manager
        self.project_name = project_name
        self.reports_dir = (reports_dir or (git_manager.repo_root / ".harness" / "reports")).resolve()

    def generate_report(self, run_id: str) -> dict[str, Any]:
        """Construct a structured report dictionary from database and Git state."""
        run = self.state_manager.get_run(run_id)
        tasks = self.state_manager.list_tasks(run_id)

        # 1. Calculate task metrics
        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        blocked = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
        pending = sum(
            1
            for t in tasks
            if t.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.VERIFYING, TaskStatus.PENDING_APPROVAL)
        )
        progress = round((completed / total * 100.0), 1) if total > 0 else 0.0

        if completed == total and total > 0:
            summary_status = "COMPLETED"
        elif blocked > 0:
            summary_status = "BLOCKED"
        elif failed > 0:
            summary_status = "FAILED"
        else:
            summary_status = "PARTIAL"

        summary = {
            "status": summary_status,
            "total_tasks": total,
            "completed_tasks": completed,
            "blocked_tasks": blocked,
            "failed_tasks": failed,
            "pending_tasks": pending,
            "progress_percentage": progress,
        }

        # 2. Checkpoints of completed tasks
        checkpoints_data: list[dict[str, Any]] = []
        for t in tasks:
            if t.status == TaskStatus.COMPLETED:
                chk = self.state_manager.get_checkpoint(t.task_id)
                attempts = self.state_manager.get_attempts(t.task_id)
                checkpoints_data.append(
                    {
                        "task_id": t.task_id,
                        "title": t.title,
                        "git_commit_hash": chk.git_commit_hash if chk else (t.current_commit_hash or "unknown"),
                        "completed_at": chk.committed_at if chk else datetime.now(timezone.utc).isoformat(),
                        "attempts": max(len(attempts), 1),
                    }
                )

        # 3. Blocked tasks details
        task_map = {t.task_id: t for t in tasks}
        blocked_data: list[dict[str, Any]] = []
        for t in tasks:
            if t.status == TaskStatus.BLOCKED:
                attempts = self.state_manager.get_attempts(t.task_id)
                failed_attempts = max(t.retry_count, len(attempts))
                
                # Find direct/transitive cascaded dependents
                dependents: list[str] = [
                    other.task_id for other in tasks if t.task_id in other.dependencies
                ]

                # Fetch verification failures from verifications table if any
                verification_errors: list[dict[str, Any]] = []
                with self.state_manager.get_connection() as conn:
                    rows = conn.execute(
                        """
                        SELECT command, exit_code, stderr
                        FROM verifications v
                        JOIN task_attempts a ON v.attempt_id = a.attempt_id
                        WHERE a.task_id = ? AND v.outcome = 'FAILED'
                        ORDER BY v.verified_at DESC
                        LIMIT 5
                        """,
                        (t.task_id,),
                    ).fetchall()
                    for r in rows:
                        verification_errors.append(
                            {
                                "command": r["command"],
                                "exit_code": r["exit_code"],
                                "stderr_snippet": (r["stderr"] or "")[:200],
                            }
                        )

                blocked_data.append(
                    {
                        "task_id": t.task_id,
                        "title": t.title,
                        "reason": f"Exceeded maximum retries ({failed_attempts}/2) or verification failure",
                        "failed_attempts": failed_attempts,
                        "verification_errors": verification_errors,
                        "cascaded_blocked_dependents": dependents,
                    }
                )

        # 4. Policy violations
        policy_violations: list[dict[str, Any]] = []
        with self.state_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT tc.task_id, tc.tool_name, tc.normalized_arguments_json, auth.policy_rule, auth.decided_at
                FROM authorizations auth
                JOIN tool_calls tc ON auth.tool_call_id = tc.tool_call_id
                WHERE auth.decision = 'DENY'
                ORDER BY auth.decided_at DESC
                LIMIT 50
                """
            ).fetchall()
            for r in rows:
                policy_violations.append(
                    {
                        "task_id": r["task_id"],
                        "tool_name": r["tool_name"],
                        "denied_path_or_command": r["normalized_arguments_json"],
                        "policy_rule": r["policy_rule"],
                        "timestamp": r["decided_at"],
                    }
                )

        # 5. Recommended actions for Gemini supervisor
        recommendations: list[str] = []
        if summary_status == "COMPLETED":
            recommendations.append("All tasks successfully executed and verified against Git checkpoints. Ready for review/merge.")
        elif blocked_data:
            for b in blocked_data:
                recommendations.append(
                    f"Task {b['task_id']} is BLOCKED after {b['failed_attempts']} attempts. Review verification errors and consider adjusting instructions or test preconditions."
                )
            recommendations.append("Use 'harness retry <task_id>' after addressing issues to unblock downstream tasks.")
        elif failed > 0:
            recommendations.append("Failed tasks encountered. Review attempt logs and trigger 'harness retry <task_id>'.")
        elif pending > 0:
            recommendations.append(f"{pending} tasks pending execution. Run 'harness resume' to continue the execution loop.")

        branch = self.git_manager.get_current_branch() if self.git_manager.is_git_repo() else "main"
        head = self.git_manager.get_head_commit() if self.git_manager.is_git_repo() else "0" * 40

        return {
            "report_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "project_name": self.project_name,
            "git_branch": branch,
            "head_commit": head,
            "summary": summary,
            "completed_task_checkpoints": checkpoints_data,
            "blocked_tasks": blocked_data,
            "policy_violations": policy_violations,
            "recommended_actions": recommendations,
        }

    def render_markdown(self, report: dict[str, Any]) -> str:
        """Render a clean, human and LLM-readable Markdown summary."""
        summary = report["summary"]
        md_lines = [
            f"# Execution Report: {report['project_name']}",
            "",
            f"- **Run ID**: `{report['run_id']}`",
            f"- **Generated At**: `{report['generated_at']}`",
            f"- **Branch**: `{report['git_branch']}`",
            f"- **Head Commit**: `{report['head_commit'][:7]}`",
            f"- **Status**: `{summary['status']}` ({summary['progress_percentage']}% complete)",
            "",
            "## Summary",
            "",
            f"| Total | Completed | Blocked | Failed | Pending | Progress |",
            f"| :---: | :-------: | :-----: | :----: | :-----: | :------: |",
            f"| {summary['total_tasks']} | {summary['completed_tasks']} | {summary['blocked_tasks']} | {summary['failed_tasks']} | {summary['pending_tasks']} | {summary['progress_percentage']}% |",
            "",
        ]

        # Blocked tasks section
        if report["blocked_tasks"]:
            md_lines.append("## Blocked Tasks")
            md_lines.append("")
            for b in report["blocked_tasks"]:
                md_lines.append(f"### Task `{b['task_id']}`: {b['title']}")
                md_lines.append(f"- **Reason**: {b['reason']}")
                md_lines.append(f"- **Failed Attempts**: {b['failed_attempts']}")
                if b["cascaded_blocked_dependents"]:
                    md_lines.append(f"- **Cascaded Blocked Dependents**: {', '.join(b['cascaded_blocked_dependents'])}")
                if b["verification_errors"]:
                    md_lines.append("- **Verification Errors**:")
                    for err in b["verification_errors"]:
                        md_lines.append(f"  - Command: `{err['command']}` (exit {err['exit_code']})")
                        if err.get("stderr_snippet"):
                            md_lines.append(f"    ```\n    {err['stderr_snippet']}\n    ```")
                md_lines.append("")

        # Completed tasks section
        if report["completed_task_checkpoints"]:
            md_lines.append("## Completed Checkpoints")
            md_lines.append("")
            md_lines.append("| Task ID | Title | Commit | Completed At | Attempts |")
            md_lines.append("| :--- | :--- | :--- | :--- | :---: |")
            for c in report["completed_task_checkpoints"]:
                commit_short = c["git_commit_hash"][:7] if c["git_commit_hash"] else "none"
                md_lines.append(
                    f"| `{c['task_id']}` | {c['title']} | `{commit_short}` | {c['completed_at']} | {c['attempts']} |"
                )
            md_lines.append("")

        # Recommended actions
        md_lines.append("## Recommended Actions")
        md_lines.append("")
        for action in report["recommended_actions"]:
            md_lines.append(f"- {action}")
        md_lines.append("")

        return "\n".join(md_lines)

    def export_reports(self, run_id: str) -> tuple[Path, Path]:
        """Generate and save both JSON and Markdown reports to disk."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        report = self.generate_report(run_id)

        json_path = self.reports_dir / f"report_{run_id}.json"
        md_path = self.reports_dir / f"report_{run_id}.md"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        md_content = self.render_markdown(report)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return json_path, md_path
