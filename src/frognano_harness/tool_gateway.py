"""Tool Gateway and Registry: exclusive entry point for model tool execution."""

import json
from pathlib import Path
from typing import Any, Optional
import uuid

from frognano_harness.exceptions import HarnessError
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
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "name": "search_code",
        "description": "Search for text or regex patterns across files in the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search string or regular expression."},
                "path": {"type": "string", "description": "Relative directory path to restrict search.", "default": "."},
                "file_pattern": {"type": "string", "description": "Glob pattern to filter filenames (e.g., '*.py').", "default": "*"}
            },
            "required": ["query"],
            "additionalProperties": False
        }
    },
    {
        "name": "write_file",
        "description": "Write or overwrite content to a pre-declared allowed file path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file to create or overwrite."},
                "content": {"type": "string", "description": "The exact full text content to write."},
                "overwrite": {"type": "boolean", "description": "Whether to overwrite existing file.", "default": True}
            },
            "required": ["path", "content"],
            "additionalProperties": False
        }
    },
    {
        "name": "apply_patch",
        "description": "Apply a unified diff or targeted block replacement to a file in allowed_files.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to the file to modify."},
                "patch": {"type": "string", "description": "Unified diff or search/replace block patch."}
            },
            "required": ["path", "patch"],
            "additionalProperties": False
        }
    },
    {
        "name": "run_command",
        "description": "Execute a safe allowlisted command using structured process arguments.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The allowlisted executable binary name (e.g., 'python', 'git')."},
                "args": {"type": "array", "items": {"type": "string"}, "description": "List of command-line arguments."},
                "timeout": {"type": "integer", "description": "Execution timeout in seconds.", "default": 120, "maximum": 300}
            },
            "required": ["command", "args"],
            "additionalProperties": False
        }
    },
    {
        "name": "run_tests",
        "description": "Execute the project automated test suite in a sandboxed subprocess.",
        "parameters": {
            "type": "object",
            "properties": {
                "test_command": {"type": "string", "description": "Test runner command (e.g., 'pytest').", "default": "pytest"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Optional arguments passed to the test runner.", "default": []}
            },
            "required": [],
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
    },
    {
        "name": "git_commit",
        "description": "Commit staged task changes to Git with task ID association.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message referencing task ID."},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Specific files to stage and commit."}
            },
            "required": ["message"],
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
    """Exclusive entry point for all model-generated tool calls."""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.registry = ToolRegistry()
        self.adapters = RuntimeAdapters(self.project_root)

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

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        """Execute a tool through its sandboxed runtime adapter."""
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
            return self.adapters.git_commit(
                message=args["message"],
                files=args.get("files"),
            )
        else:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"No execution adapter for tool: '{tool_name}'",
                duration_ms=0,
            )
