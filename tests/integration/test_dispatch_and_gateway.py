"""Integration test for task dispatch and ToolGateway execution loop."""

import tempfile
from pathlib import Path
from frognano_harness.context_manager import ContextManager
from frognano_harness.models import Task, TaskStatus
from frognano_harness.tool_gateway import ToolGateway


def test_context_assembly_and_gateway_execution() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "src").mkdir()

        task = Task(
            task_id="T-001",
            title="Create component",
            objective="Write hello.py",
            description="Create hello.py in src/",
            allowed_files=("src/hello.py",),
            acceptance_criteria=("File src/hello.py exists",),
            verification_commands=("pytest",),
        )

        cm = ContextManager(context_limit=65536)
        messages = cm.build_initial_messages(task, {"src/sample.txt": "hello"})
        assert len(messages) == 2
        assert "TASK ENVELOPE: T-001" in messages[1]["content"]

        gateway = ToolGateway(workspace)
        tool_call_id = gateway.generate_tool_call_id()
        assert tool_call_id.startswith("TC-")

        # Execute write_file tool
        res_w = gateway.execute_tool("write_file", {"path": "src/hello.py", "content": "print('hello world')"})
        assert res_w.exit_code == 0
        assert (workspace / "src" / "hello.py").exists()

        # Execute read_file tool
        res_r = gateway.execute_tool("read_file", {"path": "src/hello.py"})
        assert res_r.exit_code == 0
        assert "hello world" in res_r.stdout
