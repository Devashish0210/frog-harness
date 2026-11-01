"""Tool Gateway and Registry: exclusive, unbypassable entry point for tool execution."""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional
import uuid

from frognano_harness.approval_manager import HumanApprovalManager
from frognano_harness.audit_ledger import AuditLedger
from frognano_harness.exceptions import HarnessError
from frognano_harness.models import AuthorizationDecision, DecisionType, RiskLevel
from frognano_harness.policy_engine import PolicyEngine
from frognano_harness.runtime import RuntimeAdapters, ToolResult

CONTRACTS_TOOLS_JSON = (
    Path(__file__).resolve().parent.parent.parent
    / "specs"
    / "002-local-execution-harness"
    / "contracts"
    / "tools.json"
)

CORE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read contents of a file within the permitted workspace boundaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file within the project root."},
                "offset": {"type": "integer", "description": "Line offset from which to start reading (0-indexed).", "default": 0, "minimum": 0},
                "limit": {"type": "integer", "description": "Maximum number of lines to read.", "default": 2000, "minimum": 1, "maximum": 5000}
            },
            "required": ["path"],
            "additionalProperties": False
        }
    },
    {
        "name": "list_files",
        "description": "List files and directories in a given path within the project root.",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Relative directory path to inspect.", "default": "."},
                "recursive": {"type": "boolean", "description": "Whether to list recursively.", "default": False}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "search_code",
        "description": "Search workspace text files for regex query matching.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Regular expression pattern to find."},
                "path": {"type": "string", "description": "Directory or file to search within.", "default": "."},
                "file_pattern": {"type": "string", "description": "Glob file pattern filter.", "default": "*"}
            },
            "required": ["query"],
            "additionalProperties": False
        }
    },
    {
        "name": "write_file",
        "description": "Write or overwrite file contents strictly within allowed_files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to destination file."},
                "content": {"type": "string", "description": "Complete file content to write."},
                "overwrite": {"type": "boolean", "description": "Whether to overwrite existing file.", "default": True}
            },
            "required": ["path", "content"],
            "additionalProperties": False
        }
    },
    {
        "name": "apply_patch",
        "description": "Apply standard unified diff patch to a file strictly within allowed_files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Target file relative path to patch."},
                "patch": {"type": "string", "description": "Unified diff patch string to apply."}
            },
            "required": ["path", "patch"],
            "additionalProperties": False
        }
    },
    {
        "name": "run_command",
        "description": "Execute an allowlisted shell/build command within project boundaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Base command executable."},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments.", "default": []},
                "timeout": {"type": "integer", "description": "Timeout in seconds.", "default": 120}
            },
            "required": ["command"],
            "additionalProperties": False
        }
    },
    {
        "name": "run_tests",
        "description": "Execute the project automated test suite in a sandboxed subprocess.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_command": {"type": "string", "description": "Test runner command.", "default": "pytest"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Test runner arguments.", "default": []}
            },
            "additionalProperties": False
        }
    },
    {
        "name": "git_status",
        "description": "Check current Git working tree status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "name": "git_diff",
        "description": "Inspect uncommitted Git diffs in the working tree.",
        "parameters": {
            "type": "object",
            "properties": {
                "cached": {"type": "boolean", "description": "Whether to view staged diffs.", "default": False},
                "path": {"type": "string", "description": "Optional specific file path to diff."}
            },
            "additionalProperties": False
        }
    }
]


class ToolRegistry:
    """Registry maintaining schemas for all available tools."""

    def __init__(self) -> None:
        self.schemas: dict[str, dict[str, Any]] = {}
        # Load from contract if present
        if CONTRACTS_TOOLS_JSON.exists():
            try:
                with open(CONTRACTS_TOOLS_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for t in data.get("tools", []):
                        self.schemas[t["name"]] = t
            except Exception:
                pass

        if not self.schemas:
            for s in CORE_TOOL_SCHEMAS:
                self.schemas[s["name"]] = s

    def get_tool_schema(self, name: str) -> Optional[dict[str, Any]]:
        return self.schemas.get(name)

    def get_all_tool_schemas(self) -> list[dict[str, Any]]:
        return list(self.schemas.values())


class ToolGateway:
    """
    Exclusive, unbypassable entry point for all model-generated tool calls.
    Encapsulates PolicyEngine, HumanApprovalManager, AuditLedger, and RuntimeAdapters.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        policy_engine: Optional[PolicyEngine] = None,
        approval_manager: Optional[HumanApprovalManager] = None,
        audit_ledger: Optional[AuditLedger] = None,
        runtime: Optional[RuntimeAdapters] = None,
    ) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.registry = ToolRegistry()
        self.policy_engine = policy_engine or PolicyEngine(project_root=self.project_root)
        self.approval_manager = approval_manager
        self.audit_ledger = audit_ledger
        self.adapters = runtime or RuntimeAdapters(self.project_root)

    def generate_tool_call_id(self) -> str:
        """Generate unique tool-call identifier."""
        return f"TC-{uuid.uuid4().hex[:8].upper()}"

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions wrapped in OpenAI function calling schema."""
        return [
            {"type": "function", "function": schema}
            for schema in self.registry.get_all_tool_schemas()
        ]

    def validate_tool_args(self, tool_name: str, args: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate tool name and arguments against schema."""
        schema = self.registry.get_tool_schema(tool_name)
        if not schema:
            return False, f"Unrecognized tool: '{tool_name}'"

        params = schema.get("parameters", {})
        required = params.get("required", [])
        for req in required:
            if req not in args:
                return False, f"Missing required argument: '{req}' for tool '{tool_name}'"

        properties = params.get("properties", {})
        for key, val in args.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type == "string" and not isinstance(val, str):
                    return False, f"Argument '{key}' must be a string"
                elif expected_type == "integer" and not isinstance(val, int):
                    return False, f"Argument '{key}' must be an integer"
                elif expected_type == "boolean" and not isinstance(val, bool):
                    return False, f"Argument '{key}' must be a boolean"
                elif expected_type == "array" and not isinstance(val, list):
                    return False, f"Argument '{key}' must be an array"

        return True, None

    def dispatch(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        allowed_files: tuple[str, ...],
        task_id: str,
        attempt_id: str,
        unattended: bool = False,
    ) -> tuple[ToolResult, AuthorizationDecision]:
        """
        Unified, unbypassable execution pipeline:
        1. Validates argument schemas.
        2. Evaluates security and boundary policy.
        3. Intercepts high-risk operations for approval.
        4. Executes via sandboxed runtime adapters.
        5. Logs events to audit ledger.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Step 1: Schema validation
        is_valid, err = self.validate_tool_args(tool_name, arguments)
        if not is_valid:
            decision = AuthorizationDecision(
                decision_id=f"AUTH-{uuid.uuid4().hex[:8].upper()}",
                tool_call_id="",
                decision=DecisionType.DENY,
                risk_level=RiskLevel.HIGH,
                policy_rule="INVALID_TOOL_ARGUMENTS",
                reason=err or "Schema validation error",
                decided_at=now,
            )
            return (
                ToolResult(exit_code=1, stdout="", stderr=f"SCHEMA ERROR: {err}", duration_ms=0),
                decision,
            )

        # Step 2: Policy authorization
        auth = self.policy_engine.evaluate(
            tool_name=tool_name,
            arguments=arguments,
            allowed_files=allowed_files,
        )

        # Record policy decision in audit ledger if available
        if self.audit_ledger:
            self.audit_ledger.record_event(
                "POLICY_DECISION",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "tool_name": tool_name,
                    "decision": auth.decision.value,
                    "policy_rule": auth.policy_rule,
                    "reason": auth.reason,
                },
            )

        # Step 3: Handle DENY
        if auth.decision == DecisionType.DENY:
            return (
                ToolResult(
                    exit_code=1,
                    stdout="",
                    stderr=f"POLICY ERROR: Operation denied by rule '{auth.policy_rule}': {auth.reason}",
                    duration_ms=0,
                ),
                auth,
            )

        # Step 4: Handle REQUIRE_APPROVAL
        if auth.decision == DecisionType.REQUIRE_APPROVAL:
            if not self.approval_manager:
                return (
                    ToolResult(
                        exit_code=1,
                        stdout="",
                        stderr="APPROVAL ERROR: High-risk operation requires human approval, but no approval manager configured",
                        duration_ms=0,
                    ),
                    auth,
                )
            tc_id = self.generate_tool_call_id()
            approval = self.approval_manager.request_approval(
                tool_call_id=tc_id,
                task_id=task_id,
                operation=tool_name,
                arguments=arguments,
                risk_level=auth.risk_level,
                auto_prompt=not unattended,
            )
            if approval.status.value != "APPROVED":
                return (
                    ToolResult(
                        exit_code=1,
                        stdout="",
                        stderr=f"APPROVAL ERROR: Operation was {approval.status.value}. Execution aborted.",
                        duration_ms=0,
                    ),
                    auth,
                )

        # Step 5: Execute via sandboxed runtime
        result = self.execute_tool(tool_name, arguments)

        # Record execution in audit ledger
        if self.audit_ledger:
            self.audit_ledger.record_event(
                "TOOL_EXECUTION",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "tool_name": tool_name,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                    "affected_files": list(result.affected_files),
                },
            )

        return result, auth

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        """Execute a tool directly through its sandboxed runtime adapter."""
        is_valid, err = self.validate_tool_args(tool_name, args)
        if not is_valid:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"Tool argument validation failed: {err}",
                duration_ms=0,
            )

        if tool_name == "read_file":
            return self.adapters.read_file(
                path=args["path"],
                offset=args.get("offset", 0),
                limit=args.get("limit", 2000),
            )
        elif tool_name == "list_files":
            return self.adapters.list_files(
                directory=args.get("directory", "."),
                recursive=args.get("recursive", False),
            )
        elif tool_name == "search_code":
            return self.adapters.search_code(
                query=args["query"],
                path=args.get("path", "."),
                file_pattern=args.get("file_pattern", "*"),
            )
        elif tool_name == "write_file":
            return self.adapters.write_file(
                path=args["path"],
                content=args["content"],
                overwrite=args.get("overwrite", True),
            )
        elif tool_name == "apply_patch":
            return self.adapters.apply_patch(
                path=args["path"],
                patch=args["patch"],
            )
        elif tool_name == "run_command":
            return self.adapters.run_command(
                command=args["command"],
                args=args.get("args", []),
                timeout=args.get("timeout", 120),
            )
        elif tool_name == "run_tests":
            return self.adapters.run_tests(
                test_command=args.get("test_command", "pytest"),
                args=args.get("args", []),
            )
        elif tool_name == "git_status":
            return self.adapters.git_status()
        elif tool_name == "git_diff":
            return self.adapters.git_diff(
                cached=args.get("cached", False),
                path=args.get("path"),
            )
        elif tool_name == "git_commit":
            # Constitution Article IX: Model direct commits prohibited
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr="Tool 'git_commit' is disabled: model direct commits are constitutionally prohibited",
                duration_ms=0,
            )
        else:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"No execution adapter for tool: '{tool_name}'",
                duration_ms=0,
            )
