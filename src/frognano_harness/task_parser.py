"""SpecKit task discovery and parsing."""

import json
from pathlib import Path
import re
from typing import Optional

from frognano_harness.exceptions import SpecParsingError
from frognano_harness.models import Task, TaskStatus

CHECKLIST_LINE_REGEX = re.compile(
    r"^\s*-\s*\[([ xX])\]\s+([A-Z0-9_-]+)\s*(?:\[P\])?\s*(?:\[(US\d+)\])?\s*(.*)$"
)
DEPENDS_ON_REGEX = re.compile(r"\(depends\s+on\s+([^)]+)\)", re.IGNORECASE)
FILE_PATH_REGEX = re.compile(r"(?:in|at|per)\s+([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)")


class TaskParser:
    """Parses SpecKit task files and project specifications."""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()

    def discover_feature_dir(self) -> Optional[Path]:
        """Discover the active feature directory from .specify/feature.json or specs/."""
        feature_json = self.project_root / ".specify" / "feature.json"
        if feature_json.exists():
            try:
                with open(feature_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    dir_path = data.get("feature_directory")
                    if dir_path:
                        candidate = (self.project_root / dir_path).resolve()
                        if candidate.exists():
                            return candidate
            except Exception:
                pass

        specs_dir = self.project_root / "specs"
        if specs_dir.exists():
            subdirs = sorted([d for d in specs_dir.iterdir() if d.is_dir()], key=lambda d: d.name)
            if subdirs:
                return subdirs[-1]
        return None

    def parse_tasks_file(self, path: Path) -> list[Task]:
        """Parse tasks from a markdown file (either checklist or block format)."""
        if not path.exists():
            raise SpecParsingError(f"Tasks file not found at: {path}")

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Check if structured block format (### Task: ...)
        if "### Task:" in content:
            return self._parse_block_tasks(content)
        return self._parse_checklist_tasks(content)

    @classmethod
    def parse_file(cls, path: Path) -> list[Task]:
        """Convenience class method to parse a tasks file."""
        return cls().parse_tasks_file(path)

    def _parse_checklist_tasks(self, content: str) -> list[Task]:
        tasks: list[Task] = []
        lines = content.splitlines()

        for line in lines:
            match = CHECKLIST_LINE_REGEX.match(line)
            if not match:
                continue

            checked = match.group(1).lower() == "x"
            task_id = match.group(2)
            story = match.group(3) or ""
            desc = match.group(4).strip()

            # Extract dependencies e.g., (depends on T001, T002)
            deps: list[str] = []
            dep_match = DEPENDS_ON_REGEX.search(desc)
            if dep_match:
                raw_deps = dep_match.group(1)
                for d in re.split(r"[,;\s]+", raw_deps):
                    cleaned = d.strip()
                    if cleaned and cleaned != task_id:
                        deps.append(cleaned)

            # Extract referenced allowed files
            allowed_files: list[str] = []
            for file_match in FILE_PATH_REGEX.findall(desc):
                allowed_files.append(file_match.replace("\\", "/"))

            # Derive verification commands
            verification_commands = ["pytest"]
            if "pyproject.toml" in desc or "setup" in desc.lower():
                verification_commands = ["python -m pytest"]

            tasks.append(
                Task(
                    task_id=task_id,
                    title=desc,
                    objective=desc,
                    description=desc,
                    dependencies=tuple(deps),
                    allowed_files=tuple(allowed_files),
                    acceptance_criteria=(f"Implement {task_id} per specification",),
                    verification_commands=tuple(verification_commands),
                    status=TaskStatus.COMPLETED if checked else TaskStatus.PENDING,
                )
            )

        if not tasks:
            raise SpecParsingError("No valid task entries found in tasks file.")
        return tasks

    def _parse_block_tasks(self, content: str) -> list[Task]:
        tasks: list[Task] = []
        blocks = re.split(r"(?=###\s+Task:\s*)", content)

        for block in blocks:
            if not block.strip().startswith("### Task:"):
                continue

            header_match = re.search(r"###\s+Task:\s*([A-Z0-9_-]+)\s*(?:-\s*(.*))?", block)
            if not header_match:
                continue

            task_id = header_match.group(1).strip()
            title = (header_match.group(2) or task_id).strip()

            def get_field(name: str) -> str:
                m = re.search(rf"{name}:\s*(.+)", block, re.IGNORECASE)
                return m.group(1).strip() if m else ""

            objective = get_field("Objective") or title
            allowed_raw = get_field("Allowed Files")
            allowed_files = [f.strip() for f in allowed_raw.split(",") if f.strip()] if allowed_raw else []

            deps_raw = get_field("Dependencies")
            deps = []
            if deps_raw and deps_raw.lower() != "none":
                deps = [d.strip() for d in deps_raw.split(",") if d.strip()]

            criteria_raw = get_field("Acceptance Criteria")
            criteria = [criteria_raw] if criteria_raw else [f"Complete {task_id}"]

            commands_raw = get_field("Verification Commands")
            commands = [commands_raw] if commands_raw else ["pytest"]

            tasks.append(
                Task(
                    task_id=task_id,
                    title=title,
                    objective=objective,
                    description=block.strip(),
                    dependencies=tuple(deps),
                    allowed_files=tuple(allowed_files),
                    acceptance_criteria=tuple(criteria),
                    verification_commands=tuple(commands),
                    status=TaskStatus.PENDING,
                )
            )

        if not tasks:
            raise SpecParsingError("No structured task blocks found in file.")
        return tasks
