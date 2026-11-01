# CLI Interface Contract: Frognano Execution Harness

**Feature Branch**: `002-local-execution-harness`
**Date**: 2026-11-01
**Spec**: [spec.md](../spec.md)

This contract defines the 14 commands exposed by the `frognano-harness` CLI for Windows PowerShell (`pwsh`).

---

## Command Overview

The CLI entry point is `harness` (or `python -m frognano_harness.cli`).

| Command | Summary | Key Options | Exit Codes |
|---------|---------|-------------|------------|
| `init` | Initialize harness configuration and `.harness/` directory in the current workspace | `--endpoint <url>`, `--model <alias>`, `--force` | 0: success, 1: error |
| `validate` | Discover and validate `tasks.md`, `constitution.md`, task schemas, and detect dependency cycles | `--tasks <path>`, `--json` | 0: valid, 1: invalid / cycle |
| `plan` | Display the topological task execution DAG and dependency sequence | `--tasks <path>`, `--ascii`, `--json` | 0: success, 1: error |
| `run` | Execute ready tasks in sequential topological order | `--task <id>`, `--max-retries <n>`, `--unattended` | 0: completed, 1: failed/blocked |
| `resume` | Reconcile state against Git and resume an interrupted execution session | `--run-id <id>`, `--unattended` | 0: completed, 1: error |
| `status` | Display overall run progress, task queues, model health, and pending approvals | `--json`, `--watch` | 0: success |
| `task` | Display detailed inspection of a specific task execution envelope and history | `<task_id>`, `--json` | 0: found, 1: not found |
| `retry` | Reset retry count and re-queue a `BLOCKED` or `FAILED` task | `<task_id>`, `--force` | 0: queued, 1: error |
| `approve` | Authorize a pending high-risk tool operation | `<approval_id>` | 0: approved, 1: invalid ID |
| `reject` | Reject a pending high-risk tool operation | `<approval_id>`, `--reason <text>` | 0: rejected, 1: invalid ID |
| `report` | Generate structured JSON and Markdown execution reports for Gemini supervisory review | `--output <dir>`, `--format [json\|md\|both]` | 0: generated, 1: error |
| `logs` | View structured execution traces and tool outputs for a task or run | `<task_id>`, `--tail <n>`, `--tool <name>` | 0: success, 1: error |
| `verify` | Independently re-run verification commands for a task without model invocation | `<task_id>`, `--all` | 0: passed, 1: failed |
| `audit` | Verify hash-chain cryptographic integrity and inspect tool-call lifecycles | `--verify-chain`, `--tool-call <id>`, `--json` | 0: valid, 1: tampered/error |

---

## Detailed Command Specifications

### 1. `harness init`
- **Purpose**: Creates `.harness/` directory structure, initializes `.harness/state.db` SQLite database, and creates `.harness/config.json`.
- **Usage**:
  ```powershell
  harness init [--endpoint http://127.0.0.1:8080/v1] [--model frognano] [--force]
  ```

### 2. `harness validate`
- **Purpose**: Scans project root for SpecKit files, parses `tasks.md`, checks contract requirements (objective, acceptance criteria, verification commands, `allowed_files`), and runs Kahn's algorithm to detect dependency cycles.
- **Usage**:
  ```powershell
  harness validate [--tasks specs/002-feature/tasks.md] [--json]
  ```

### 3. `harness plan`
- **Purpose**: Generates and prints the directed acyclic graph (DAG) of tasks showing topological ordering and parallelizable branches.
- **Usage**:
  ```powershell
  harness plan [--ascii] [--json]
  ```

### 4. `harness run`
- **Purpose**: Starts execution of tasks. Connects to `llama.cpp`, dispatches task envelopes to FrogNano, enforces Policy Engine rules, executes tools via Tool Gateway, runs independent verification, and creates Git checkpoints.
- **Usage**:
  ```powershell
  harness run [--unattended] [--max-retries 2] [--timeout 180]
  ```

### 5. `harness resume`
- **Purpose**: Reconciles SQLite state with the current Git working tree. Skips already committed tasks and resumes execution from the first incomplete task.
- **Usage**:
  ```powershell
  harness resume [--unattended]
  ```

### 6. `harness status`
- **Purpose**: Prints terminal summary of execution progress: completed, running, pending, blocked, and approvals awaiting action.
- **Usage**:
  ```powershell
  harness status [--json]
  ```

### 7. `harness approve` / `harness reject`
- **Purpose**: Manually approve or deny high-risk operations held by the Human Approval Manager.
- **Usage**:
  ```powershell
  harness approve APP-9042
  harness reject APP-9042 --reason "Package installation not allowed"
  ```

### 8. `harness audit`
- **Purpose**: Traverses the SQLite `audit_events` table, verifies SHA-256 hash chaining, and detects unauthorized state tampering.
- **Usage**:
  ```powershell
  harness audit --verify-chain
  harness audit --tool-call TC-1049
  ```
