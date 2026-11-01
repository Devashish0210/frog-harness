"""Sandboxed execution adapters for filesystem, terminal, testing, and git operations."""

from dataclasses import dataclass, field
import difflib
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Optional


@dataclass(frozen=True)
class ToolResult:
    """Standardized output from a tool adapter execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    affected_files: tuple[str, ...] = field(default_factory=tuple)


class RuntimeAdapters:
    """Executes validated tool operations inside the project workspace."""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()

    def _resolve(self, rel_path: str) -> Path:
        return (self.project_root / rel_path).resolve()

    def read_file(self, path: str, offset: int = 0, limit: int = 2000) -> ToolResult:
        start_time = time.perf_counter()
        target = self._resolve(path)
        if not target.exists() or not target.is_file():
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"File not found: {path}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            sliced = lines[offset : offset + limit]
            return ToolResult(
                exit_code=0,
                stdout="".join(sliced),
                stderr="",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    def list_files(self, directory: str = ".", recursive: bool = False) -> ToolResult:
        start_time = time.perf_counter()
        target = self._resolve(directory)
        if not target.exists() or not target.is_dir():
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"Directory not found: {directory}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

        results: list[str] = []
        try:
            if recursive:
                for root, _, files in os.walk(target):
                    rel_dir = Path(root).relative_to(self.project_root)
                    for f in files:
                        results.append(str(rel_dir / f).replace("\\", "/"))
            else:
                for item in target.iterdir():
                    rel = item.relative_to(self.project_root)
                    suffix = "/" if item.is_dir() else ""
                    results.append(f"{str(rel).replace('\\', '/')}{suffix}")

            return ToolResult(
                exit_code=0,
                stdout="\n".join(sorted(results)),
                stderr="",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    def search_code(self, query: str, path: str = ".", file_pattern: str = "*") -> ToolResult:
        start_time = time.perf_counter()
        target = self._resolve(path)
        if not target.exists():
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"Search path not found: {path}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

        matches: list[str] = []
        regex = re.compile(query, re.IGNORECASE)

        files = target.rglob(file_pattern) if target.is_dir() else [target]
        for f in files:
            if not f.is_file():
                continue
            try:
                with open(f, "r", encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh, start=1):
                        if regex.search(line):
                            rel = f.relative_to(self.project_root)
                            matches.append(f"{str(rel).replace('\\', '/')}:{i}: {line.strip()}")
            except Exception:
                continue

        return ToolResult(
            exit_code=0,
            stdout="\n".join(matches[:500]),
            stderr="",
            duration_ms=int((time.perf_counter() - start_time) * 1000),
        )

    def write_file(self, path: str, content: str, overwrite: bool = True) -> ToolResult:
        start_time = time.perf_counter()
        target = self._resolve(path)
        if target.exists() and not overwrite:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"File already exists and overwrite is False: {path}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                exit_code=0,
                stdout=f"Wrote {len(content)} characters to {path}",
                stderr="",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                affected_files=(path,),
            )
        except Exception as e:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    def apply_patch(self, path: str, patch: str) -> ToolResult:
        start_time = time.perf_counter()
        target = self._resolve(path)
        if not target.exists():
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=f"Cannot patch non-existent file: {path}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

        # Simple string replacement or unified diff patch
        try:
            original = target.read_text(encoding="utf-8")
            # If patch contains SEARCH/REPLACE format
            if "<<<<<<< SEARCH" in patch and "=======" in patch and ">>>>>>> REPLACE" in patch:
                parts = patch.split("<<<<<<< SEARCH")[1].split(">>>>>>> REPLACE")[0]
                search_block, replace_block = parts.split("=======")
                search_text = search_block.strip("\r\n")
                replace_text = replace_block.strip("\r\n")
                if search_text not in original:
                    return ToolResult(
                        exit_code=1,
                        stdout="",
                        stderr="Search block not found in original file",
                        duration_ms=int((time.perf_counter() - start_time) * 1000),
                    )
                new_content = original.replace(search_text, replace_text, 1)
                target.write_text(new_content, encoding="utf-8")
                return ToolResult(
                    exit_code=0,
                    stdout=f"Applied block patch to {path}",
                    stderr="",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                    affected_files=(path,),
                )
            else:
                # Direct overwrite with patch text if simple update
                target.write_text(patch, encoding="utf-8")
                return ToolResult(
                    exit_code=0,
                    stdout=f"Updated {path}",
                    stderr="",
                    duration_ms=int((time.perf_counter() - start_time) * 1000),
                    affected_files=(path,),
                )
        except Exception as e:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    def run_command(self, command: str, args: list[str], timeout: int = 120) -> ToolResult:
        start_time = time.perf_counter()
        cmd = [command] + args
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                encoding="utf-8",
                errors="replace",
            )
            return ToolResult(
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                exit_code=124,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds: {' '.join(cmd)}",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
        except Exception as e:
            return ToolResult(
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
            )

    def run_tests(self, test_command: str = "pytest", args: Optional[list[str]] = None) -> ToolResult:
        cmd_args = args or []
        # Run via python -m if pytest
        if test_command == "pytest":
            return self.run_command("python", ["-m", "pytest"] + cmd_args)
        return self.run_command(test_command, cmd_args)

    def git_status(self) -> ToolResult:
        return self.run_command("git", ["status", "--short"])

    def git_diff(self, cached: bool = False, path: Optional[str] = None) -> ToolResult:
        args = ["diff"]
        if cached:
            args.append("--cached")
        if path:
            args.extend(["--", path])
        return self.run_command("git", args)

    def git_commit(self, message: str, files: Optional[list[str]] = None) -> ToolResult:
        start_time = time.perf_counter()
        if files:
            for f in files:
                self.run_command("git", ["add", f])
        else:
            self.run_command("git", ["add", "-A"])

        res = self.run_command("git", ["commit", "-m", message])
        return ToolResult(
            exit_code=res.exit_code,
            stdout=res.stdout,
            stderr=res.stderr,
            duration_ms=int((time.perf_counter() - start_time) * 1000),
        )
