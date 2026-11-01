"""Deterministic Policy and Authorization Engine."""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Optional
import uuid

from frognano_harness.models import AuthorizationDecision, DecisionType, RiskLevel, Task

PROTECTED_SECRET_PATTERNS = [
    re.compile(r"^\.env(?:\..+)?$", re.IGNORECASE),
    re.compile(r".*\.(?:pem|key|pkcs12|pfx|id_rsa)$", re.IGNORECASE),
    re.compile(r"^\.git(?:[/\\].*)?$", re.IGNORECASE),
]

SAFE_COMMANDS = {"python", "pytest", "git", "mypy", "ruff"}
WINDOWS_DEVICE_NAMES = {"con", "prn", "aux", "nul", "com1", "com2", "lpt1", "lpt2"}


class PolicyEngine:
    """Enforces zero-trust sandbox rules and deterministic authorization."""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()

    def _normalize_path(self, rel_path: str) -> tuple[Optional[Path], Optional[str]]:
        """Normalize path and ensure it resides strictly within project_root."""
        # Check for invalid Windows device names
        parts = re.split(r"[/\\:]+", rel_path)
        for part in parts:
            if part.lower() in WINDOWS_DEVICE_NAMES:
                return None, f"Path contains illegal device name: '{part}'"

        try:
            target = (self.project_root / rel_path).resolve()
        except Exception as e:
            return None, f"Invalid path syntax: {e}"

        if not target.is_relative_to(self.project_root):
            return None, f"Path traversal boundary violation: '{rel_path}' escapes project root"

        return target, None

    def _is_secret_path(self, target: Path) -> bool:
        """Check if path targets protected secrets or credentials."""
        rel_str = str(target.relative_to(self.project_root)).replace("\\", "/")
        filename = target.name
        for pat in PROTECTED_SECRET_PATTERNS:
            if pat.match(filename) or pat.match(rel_str):
                return True
        return False

    def evaluate(
        self,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
        args: Optional[dict[str, Any]] = None,
        task: Optional[Task] = None,
        allowed_files: Optional[tuple[str, ...]] = None,
    ) -> AuthorizationDecision:
        """Unified entrypoint satisfying PolicyEngineProtocol."""
        effective_args = arguments if arguments is not None else (args or {})
        return self.evaluate_tool_request(
            tool_name=tool_name,
            args=effective_args,
            task=task,
            allowed_files=allowed_files,
        )

    def evaluate_tool_request(
        self,
        tool_name: str,
        args: dict[str, Any],
        task: Optional[Task] = None,
        allowed_files: Optional[tuple[str, ...]] = None,
    ) -> AuthorizationDecision:
        """Evaluate a tool invocation request against security and scope rules."""
        now = datetime.now(timezone.utc).isoformat()
        decision_id = f"AUTH-{uuid.uuid4().hex[:8].upper()}"

        # 0. Constitutional prohibition: Model Git commit
        if tool_name == "git_commit":
            return AuthorizationDecision(
                decision_id=decision_id,
                tool_call_id="",
                decision=DecisionType.DENY,
                risk_level=RiskLevel.HIGH,
                policy_rule="MODEL_GIT_COMMIT_PROHIBITED",
                reason="Model is constitutionally prohibited from executing Git commits directly. Commits are created exclusively by the harness verification engine upon verified success.",
                decided_at=now,
            )

        # 1. Path-based evaluation
        if tool_name in ("read_file", "write_file", "apply_patch"):
            path_arg = args.get("path")
            if not path_arg or not isinstance(path_arg, str):
                return AuthorizationDecision(
                    decision_id=decision_id,
                    tool_call_id="",
                    decision=DecisionType.DENY,
                    risk_level=RiskLevel.HIGH,
                    policy_rule="PATH_REQUIRED",
                    reason="Operation requires a valid 'path' argument",
                    decided_at=now,
                )

            target, err = self._normalize_path(path_arg)
            if err or target is None:
                return AuthorizationDecision(
                    decision_id=decision_id,
                    tool_call_id="",
                    decision=DecisionType.DENY,
                    risk_level=RiskLevel.HIGH,
                    policy_rule="PATH_BOUNDARY",
                    reason=err or "Path escapes project boundary",
                    decided_at=now,
                )

            if self._is_secret_path(target):
                return AuthorizationDecision(
                    decision_id=decision_id,
                    tool_call_id="",
                    decision=DecisionType.DENY,
                    risk_level=RiskLevel.HIGH,
                    policy_rule="SECRET_PROTECTION",
                    reason=f"Access to protected secret or credential file is denied: '{path_arg}'",
                    decided_at=now,
                )

            # Check task allowed_files for write/patch operations
            if tool_name in ("write_file", "apply_patch"):
                effective_allowed = allowed_files if allowed_files is not None else (task.allowed_files if task else ())
                if not effective_allowed:
                    return AuthorizationDecision(
                        decision_id=decision_id,
                        tool_call_id="",
                        decision=DecisionType.DENY,
                        risk_level=RiskLevel.HIGH,
                        policy_rule="TASK_ALLOWED_FILES_EMPTY",
                        reason=f"Write operation denied: no allowed_files declared for this task boundary",
                        decided_at=now,
                    )

                norm_rel = str(target.relative_to(self.project_root)).replace("\\", "/")
                allowed_normalized = [f.replace("\\", "/").lstrip("./") for f in effective_allowed]
                if norm_rel not in allowed_normalized:
                    task_label = f"task {task.task_id}" if task else "current task"
                    return AuthorizationDecision(
                        decision_id=decision_id,
                        tool_call_id="",
                        decision=DecisionType.DENY,
                        risk_level=RiskLevel.MEDIUM,
                        policy_rule="TASK_ALLOWED_FILES",
                        reason=f"File '{norm_rel}' is not in declared allowed_files for {task_label}",
                        decided_at=now,
                    )

                return AuthorizationDecision(
                    decision_id=decision_id,
                    tool_call_id="",
                    decision=DecisionType.ALLOW,
                    risk_level=RiskLevel.MEDIUM,
                    policy_rule="AUTHORIZED_WRITE",
                    reason=f"Write operation permitted within allowed_files",
                    decided_at=now,
                )

            # Read file within project root
            return AuthorizationDecision(
                decision_id=decision_id,
                tool_call_id="",
                decision=DecisionType.ALLOW,
                risk_level=RiskLevel.LOW,
                policy_rule="SAFE_READ",
                reason="Read operation permitted within project root",
                decided_at=now,
            )

        # 2. Command execution evaluation
        elif tool_name == "run_command":
            cmd = args.get("command", "")
            cmd_args = args.get("args", [])
            base_cmd = Path(cmd).name.lower().replace(".exe", "")

            # High risk commands
            if base_cmd not in SAFE_COMMANDS or any(a in ("pip", "install", "rm", "del", "format") for a in cmd_args):
                return AuthorizationDecision(
                    decision_id=decision_id,
                    tool_call_id="",
                    decision=DecisionType.REQUIRE_APPROVAL,
                    risk_level=RiskLevel.HIGH,
                    policy_rule="HIGH_RISK_COMMAND",
                    reason=f"Command '{cmd}' or arguments require operator authorization",
                    decided_at=now,
                )

            return AuthorizationDecision(
                decision_id=decision_id,
                tool_call_id="",
                decision=DecisionType.ALLOW,
                risk_level=RiskLevel.MEDIUM,
                policy_rule="SAFE_COMMAND",
                reason=f"Command '{cmd}' is allowlisted",
                decided_at=now,
            )

        # 3. Read-only navigation
        elif tool_name in ("list_files", "search_code", "git_status", "git_diff"):
            return AuthorizationDecision(
                decision_id=decision_id,
                tool_call_id="",
                decision=DecisionType.ALLOW,
                risk_level=RiskLevel.LOW,
                policy_rule="READ_ONLY_OBSERVATION",
                reason=f"Tool '{tool_name}' is read-only and safe to execute",
                decided_at=now,
            )

        # 4. Testing
        elif tool_name == "run_tests":
            return AuthorizationDecision(
                decision_id=decision_id,
                tool_call_id="",
                decision=DecisionType.ALLOW,
                risk_level=RiskLevel.MEDIUM,
                policy_rule="SAFE_TASK_CYCLE",
                reason=f"Tool '{tool_name}' is authorized as part of nominal task execution",
                decided_at=now,
            )

        # Default fallback
        return AuthorizationDecision(
            decision_id=decision_id,
            tool_call_id="",
            decision=DecisionType.REQUIRE_APPROVAL,
            risk_level=RiskLevel.HIGH,
            policy_rule="UNKNOWN_TOOL_POLICY",
            reason=f"Tool '{tool_name}' requires human authorization",
            decided_at=now,
        )
