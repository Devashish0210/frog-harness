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
