"""Integration test for SpecKit discovery, parsing, and DAG ordering."""

from pathlib import Path
from frognano_harness.scheduler import TaskScheduler
from frognano_harness.task_parser import TaskParser


def test_discover_and_parse_real_spec() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    parser = TaskParser(root)
    feature_dir = parser.discover_feature_dir()
    assert feature_dir is not None
    assert feature_dir.name == "002-local-execution-harness"

    tasks_file = feature_dir / "tasks.md"
    assert tasks_file.exists()

    tasks = parser.parse_tasks_file(tasks_file)
    assert len(tasks) == 58
    assert tasks[0].task_id == "T001"
    assert tasks[-1].task_id == "T058"

    scheduler = TaskScheduler(tasks)
    ordered = scheduler.get_execution_order()
    assert len(ordered) == 58

    # Check dependencies: T006 cannot run before T001
    ids = [t.task_id for t in ordered]
    assert ids.index("T001") < ids.index("T006")
