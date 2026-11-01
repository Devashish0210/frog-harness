"""Unit tests for ToolGateway and sandboxed execution adapters."""

import tempfile
from pathlib import Path
import pytest
from frognano_harness.runtime import RuntimeAdapters
from frognano_harness.tool_gateway import ToolGateway, ToolRegistry


@pytest.fixture
def workspace() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "src").mkdir()
        (root / "src" / "sample.py").write_text("print('hello')", encoding="utf-8")
        yield root


def test_tool_gateway_schema_validation(workspace: Path) -> None:
    gateway = ToolGateway(workspace)
    # Valid call
    is_valid, err = gateway.validate_tool_args("read_file", {"path": "src/sample.py"})
    assert is_valid is True
    assert err is None

    # Invalid tool name
    is_valid, err = gateway.validate_tool_args("unknown_tool", {})
    assert is_valid is False
    assert "Unrecognized tool" in (err or "")

    # Missing required parameter
    is_valid, err = gateway.validate_tool_args("read_file", {})
    assert is_valid is False
    assert "Missing required argument" in (err or "")


def test_runtime_adapters_filesystem(workspace: Path) -> None:
    adapters = RuntimeAdapters(workspace)

    # Read
    res = adapters.read_file("src/sample.py")
    assert res.exit_code == 0
    assert "print('hello')" in res.stdout

    # Write
    res_w = adapters.write_file("src/new.py", "x = 42")
    assert res_w.exit_code == 0
    assert (workspace / "src" / "new.py").read_text(encoding="utf-8") == "x = 42"

    # Search
    res_s = adapters.search_code("hello", "src")
    assert res_s.exit_code == 0
    assert "src/sample.py" in res_s.stdout


def test_tool_gateway_dispatch_enforces_policy_and_blocks_bypass(workspace: Path) -> None:
    """Verify that dispatch() strictly enforces PolicyEngine and cannot be bypassed."""
    gateway = ToolGateway(workspace)

    # 1. Deny path traversal
    res, auth = gateway.dispatch(
        tool_name="read_file",
        arguments={"path": "../../escaped.txt"},
        allowed_files=("src/sample.py",),
        task_id="T001",
        attempt_id="att1",
    )
    assert res.exit_code == 1
    assert "POLICY ERROR" in res.stderr
    assert auth.decision.value == "DENY"

    # 2. Deny file outside allowed_files
    res2, auth2 = gateway.dispatch(
        tool_name="write_file",
        arguments={"path": "src/unauthorized.py", "content": "bad"},
        allowed_files=("src/sample.py",),
        task_id="T001",
        attempt_id="att1",
    )
    assert res2.exit_code == 1
    assert "POLICY ERROR" in res2.stderr
    assert auth2.decision.value == "DENY"

    # 3. Allow file within allowed_files
    res3, auth3 = gateway.dispatch(
        tool_name="write_file",
        arguments={"path": "src/sample.py", "content": "updated content"},
        allowed_files=("src/sample.py",),
        task_id="T001",
        attempt_id="att1",
    )
    assert res3.exit_code == 0
    assert auth3.decision.value == "ALLOW"
    assert (workspace / "src" / "sample.py").read_text(encoding="utf-8") == "updated content"
