"""Task scheduling, DAG construction, and dependency resolution."""

from collections import defaultdict, deque
from typing import Optional

from frognano_harness.exceptions import CyclicDependencyError
from frognano_harness.models import Task, TaskStatus


class TaskScheduler:
    """Constructs execution DAG, validates cycles, and determines task execution order."""

    def __init__(self, tasks: list[Task]) -> None:
        self.tasks: dict[str, Task] = {t.task_id: t for t in tasks}
        self.in_degree: dict[str, int] = {t.task_id: 0 for t in tasks}
        self.adjacency: dict[str, list[str]] = defaultdict(list)
        self._build_graph()

    def _build_graph(self) -> None:
        for task in self.tasks.values():
            for dep in task.dependencies:
                if dep in self.tasks:
                    self.adjacency[dep].append(task.task_id)
                    self.in_degree[task.task_id] += 1

    def get_execution_order(self) -> list[Task]:
        """Compute topological sort using Kahn's algorithm."""
        in_deg = dict(self.in_degree)
        queue: deque[str] = deque([t_id for t_id, deg in in_deg.items() if deg == 0])
        ordered: list[Task] = []

        while queue:
            curr_id = queue.popleft()
            ordered.append(self.tasks[curr_id])

            for neighbor in self.adjacency[curr_id]:
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(self.tasks):
            # Cycle detected
            remaining = [t_id for t_id, deg in in_deg.items() if deg > 0]
            raise CyclicDependencyError(f"Cyclic dependency detected among tasks: {', '.join(remaining)}")

        return ordered

    def validate_dag(self) -> tuple[bool, str]:
        """Validate DAG cycle freedom. Returns (is_valid, message)."""
        try:
            order = self.get_execution_order()
            return True, f"DAG is acyclic with {len(order)} tasks in topological sequence."
        except CyclicDependencyError as e:
            return False, str(e)

    def get_topological_order(self) -> list[Task]:
        """Alias for get_execution_order()."""
        return self.get_execution_order()

    def is_task_blocked_by_dependency(self, task_id: str) -> bool:
        """Check if any prerequisite task is BLOCKED."""
        visited: set[str] = set()

        def has_blocked_ancestor(t_id: str) -> bool:
            if t_id in visited:
                return False
            visited.add(t_id)

            task = self.tasks.get(t_id)
            if not task:
                return False

            for dep in task.dependencies:
                dep_task = self.tasks.get(dep)
                if dep_task:
                    if dep_task.status == TaskStatus.BLOCKED:
                        return True
                    if has_blocked_ancestor(dep):
                        return True
            return False

        return has_blocked_ancestor(task_id)

    def get_ready_tasks(self) -> list[Task]:
        """
        Return tasks that are ready for execution:
        - Status is PENDING or READY
        - Not blocked by any ancestor dependency
        - All direct dependencies are COMPLETED
        """
        ready: list[Task] = []
        for task in self.tasks.values():
            if task.status not in (TaskStatus.PENDING, TaskStatus.READY):
                continue

            if self.is_task_blocked_by_dependency(task.task_id):
                continue

            # Check if all dependencies are COMPLETED
            deps_completed = True
            for dep in task.dependencies:
                dep_task = self.tasks.get(dep)
                if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                    deps_completed = False
                    break

            if deps_completed:
                ready.append(task)

        return sorted(ready, key=lambda t: t.task_id)

    def cascade_blocked_dependents(self, blocked_task_id: str) -> list[str]:
        """Find all downstream transitive dependents of a blocked task."""
        cascaded: list[str] = []
        queue: deque[str] = deque([blocked_task_id])
        visited: set[str] = {blocked_task_id}

        while queue:
            curr = queue.popleft()
            for neighbor in self.adjacency[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    cascaded.append(neighbor)
                    queue.append(neighbor)

        return cascaded

    def mark_task_completed(self, task_id: str) -> None:
        """Update in-memory task status to COMPLETED."""
        if task_id in self.tasks:
            t = self.tasks[task_id]
            self.tasks[task_id] = Task(
                task_id=t.task_id,
                title=t.title,
                objective=t.objective,
                description=t.description,
                dependencies=t.dependencies,
                allowed_files=t.allowed_files,
                acceptance_criteria=t.acceptance_criteria,
                verification_commands=t.verification_commands,
                status=TaskStatus.COMPLETED,
                retry_count=t.retry_count,
                current_commit_hash=t.current_commit_hash,
            )

    def mark_task_blocked(self, task_id: str) -> list[str]:
        """Update in-memory task status to BLOCKED and cascade to dependents."""
        blocked_ids = [task_id]
        if task_id in self.tasks:
            t = self.tasks[task_id]
            self.tasks[task_id] = Task(
                task_id=t.task_id,
                title=t.title,
                objective=t.objective,
                description=t.description,
                dependencies=t.dependencies,
                allowed_files=t.allowed_files,
                acceptance_criteria=t.acceptance_criteria,
                verification_commands=t.verification_commands,
                status=TaskStatus.BLOCKED,
                retry_count=t.retry_count,
                current_commit_hash=t.current_commit_hash,
            )

        dependents = self.cascade_blocked_dependents(task_id)
        for dep_id in dependents:
            blocked_ids.append(dep_id)
            if dep_id in self.tasks:
                dt = self.tasks[dep_id]
                self.tasks[dep_id] = Task(
                    task_id=dt.task_id,
                    title=dt.title,
                    objective=dt.objective,
                    description=dt.description,
                    dependencies=dt.dependencies,
                    allowed_files=dt.allowed_files,
                    acceptance_criteria=dt.acceptance_criteria,
                    verification_commands=dt.verification_commands,
                    status=TaskStatus.BLOCKED,
                    retry_count=dt.retry_count,
                    current_commit_hash=dt.current_commit_hash,
                )
        return blocked_ids
