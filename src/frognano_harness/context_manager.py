"""Task-specific context assembly and observation management."""

from typing import Any, Optional
from frognano_harness.models import Task

SYSTEM_PROMPT = """You are FrogNano-4B, an autonomous implementation agent executing inside a controlled local execution harness on Windows 11.
Core Engineering Principle:
Gemini plans. SpecKit structures. Python orchestrates. FrogNano implements. The Policy Engine authorizes. The Runtime executes. The Verification Engine verifies. The Audit Ledger remembers.

Operating Rules:
1. You MUST NOT attempt direct shell or filesystem calls. All actions MUST pass through tool calls.
2. You MUST operate strictly within the declared allowed_files boundaries. Creating or modifying files outside allowed_files will be rejected by the Policy Engine.
3. Every implementation MUST be accompanied by passing tests specified in verification_commands.
4. When finished, emit your final response explaining the completed implementation.
"""


class ContextManager:
    """Manages context assembly, token ceiling enforcement, and clean retry packaging."""

    def __init__(self, context_limit: int = 65536) -> None:
        self.context_limit = context_limit

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation heuristic (1 token ~= 4 characters)."""
        return max(1, len(text) // 4)

    def build_initial_messages(
        self,
        task: Task,
        file_contents: Optional[dict[str, str]] = None,
        spec_extract: Optional[str] = None,
    ) -> list[dict[str, str]]:
        """Assemble the initial structured task envelope."""
        allowed_files_str = "\n".join(f"  - {f}" for f in task.allowed_files) or "  (None declared)"
        criteria_str = "\n".join(f"  - {c}" for c in task.acceptance_criteria) or "  (None declared)"
        commands_str = "\n".join(f"  - {v}" for v in task.verification_commands) or "  (None declared)"

        user_content_parts = [
            f"# TASK ENVELOPE: {task.task_id} - {task.title}\n",
            f"**Objective**: {task.objective}\n",
            f"**Description**:\n{task.description}\n",
            f"**Allowed Files (Strict Boundaries)**:\n{allowed_files_str}\n",
            f"**Acceptance Criteria**:\n{criteria_str}\n",
            f"**Prescribed Verification Commands**:\n{commands_str}\n",
        ]

        if spec_extract:
            user_content_parts.append(f"\n## Relevant Specification\n{spec_extract}\n")

        if file_contents:
            user_content_parts.append("\n## Permitted File Context\n")
            for path, content in file_contents.items():
                truncated = self.truncate_text(content, max_tokens=8000)
                user_content_parts.append(f"### File: {path}\n```\n{truncated}\n```\n")

        user_msg = "".join(user_content_parts)
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

    def build_task_envelope(self, task: Task) -> str:
        """Return the user message text for a task envelope."""
        messages = self.build_initial_messages(task)
        return messages[1]["content"]

    def package_retry_context(self, task: Task, diagnostics: dict[str, Any]) -> list[dict[str, str]]:
        """Convenience adapter packaging retry diagnostics dictionary into retry messages."""
        return self.build_retry_messages(
            task=task,
            failed_command=diagnostics.get("command", "pytest"),
            exit_code=diagnostics.get("exit_code", 1),
            stdout=diagnostics.get("stdout", ""),
            stderr=diagnostics.get("stderr", ""),
            git_diff=diagnostics.get("git_diff", ""),
        )

    def build_retry_messages(
        self,
        task: Task,
        failed_command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        git_diff: str,
        file_contents: Optional[dict[str, str]] = None,
    ) -> list[dict[str, str]]:
        """
        Assemble clean-context retry envelope:
        Resets intermediate tool dialogue and provides pristine task envelope plus
        only the immediate preceding failure diagnostics.
        """
        messages = self.build_initial_messages(task, file_contents)

        diff_snippet = self.truncate_text(git_diff, max_tokens=4000)
        err_snippet = self.truncate_text(stderr or stdout, max_tokens=4000)

        correction_content = (
            f"# VERIFICATION FAILED (Attempt {task.retry_count + 1})\n"
            f"Your previous implementation attempt failed independent verification.\n\n"
            f"**Command Executed**: `{failed_command}`\n"
            f"**Exit Code**: {exit_code}\n\n"
            f"**Test Output / Error Diagnostics**:\n```\n{err_snippet}\n```\n\n"
            f"**Current Git Diff**:\n```diff\n{diff_snippet}\n```\n\n"
            f"Please correct the implementation to fix the failing tests and satisfy all acceptance criteria."
        )

        messages.append({"role": "user", "content": correction_content})
        return messages

    def truncate_text(self, text: str, max_tokens: int = 4000) -> str:
        """Truncate text to avoid overflowing token budgets."""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n\n... [TRUNCATED DUE TO CONTEXT LIMIT] ...\n\n" + text[-half:]
