"""Unit tests for task scheduler and DAG resolver."""

import pytest
from frognano_harness.exceptions import CyclicDependencyError
from frognano_harness.models import Task, TaskStatus
from frognano_harness.scheduler import TaskScheduler


def make_task(task_id: str, deps: tuple[str, ...], status: TaskStatus = TaskStatus.PENDING) -> Task:
    return Task(
        task_id=task_id,
        title=f"Task {task_id}",
        objective=f"Objective {task_id}",
        description="Desc",
        dependencies=deps,
        status=status,
    )


def test_topological_sort_linear() -> None:
    t1 = make_task("T-1", ())
    t2 = make_task("T-2", ("T-1",))
    t3 = make_task("T-3", ("T-2",))

    scheduler = TaskScheduler([t3, t1, t2])
    ordered = scheduler.get_execution_order()
    assert [t.task_id for t in ordered] == ["T-1", "T-2", "T-3"]


def test_topological_sort_branching() -> None:
    t1 = make_task("T-1", ())
    t2a = make_task("T-2A", ("T-1",))
    t2b = make_task("T-2B", ("T-1",))
    t3 = make_task("T-3", ("T-2A", "T-2B"))

    scheduler = TaskScheduler([t3, t2b, t1, t2a])
    ordered = scheduler.get_execution_order()
    order_ids = [t.task_id for t in ordered]
    assert order_ids[0] == "T-1"
    assert order_ids[-1] == "T-3"
    assert set(order_ids[1:3]) == {"T-2A", "T-2B"}


def test_cycle_detection() -> None:
    t1 = make_task("T-1", ("T-2",))
    t2 = make_task("T-2", ("T-1",))

    scheduler = TaskScheduler([t1, t2])
    with pytest.raises(CyclicDependencyError, match="Cyclic dependency"):
        scheduler.get_execution_order()


def test_get_ready_tasks() -> None:
    t1 = make_task("T-1", (), status=TaskStatus.COMPLETED)
    t2 = make_task("T-2", ("T-1",), status=TaskStatus.PENDING)
    t3 = make_task("T-3", ("T-2",), status=TaskStatus.PENDING)

    scheduler = TaskScheduler([t1, t2, t3])
    ready = scheduler.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].task_id == "T-2"


def test_blocked_task_cascades_only_dependents() -> None:
    t1 = make_task("T-1", (), status=TaskStatus.BLOCKED)
    t2 = make_task("T-2", ("T-1",), status=TaskStatus.PENDING)  # Dependent on blocked
    t3 = make_task("T-3", (), status=TaskStatus.PENDING)        # Independent

    scheduler = TaskScheduler([t1, t2, t3])
    ready = scheduler.get_ready_tasks()
    # T-3 is ready; T-2 is blocked by T-1
    assert len(ready) == 1
    assert ready[0].task_id == "T-3"
    assert scheduler.is_task_blocked_by_dependency("T-2") is True
