# Research: Local Agentic Coding Execution Harness

**Feature Branch**: `002-local-execution-harness`
**Date**: 2026-11-01
**Spec**: [spec.md](./spec.md)

This document consolidates research findings, architectural decisions, and technology selections for implementing the Local Agentic Coding Execution Harness.

---

## 1. Local Python Architecture & Dependency Strategy

### Context & Problem
The system coordinates complex agentic workflows (task parsing, DAG scheduling, model inference, tool execution, policy enforcement, verification, and audit logging) on Windows 11 hardware (NVIDIA RTX 4060 Laptop GPU 8GB VRAM, 16GB RAM) without paid external APIs. Article XI and Article X of the project constitution mandate simplicity, maintainability, resource efficiency, and a standard-library-first approach.

### Decision
Implement the entire execution harness as a single, modular Python 3.11+ application organized under `src/frognano_harness/`.
- Prioritize Python's standard library modules: `sqlite3`, `subprocess`, `pathlib`, `json`, `argparse`, `dataclasses`, `urllib.request`, `hashlib`, `logging`, `typing`, `enum`.
- Minimal external development dependencies: `pytest` (test execution), `mypy` (static type checking in strict mode), and `ruff` (formatting and linting).
- No web servers (FastAPI/Flask), no external databases (PostgreSQL/Redis), and no microservices in the initial release.

### Rationale
- **Zero Supply-Chain Bloat**: Minimizes security attack surface and avoids version conflicts on the developer's laptop.
- **Resource Footprint**: Consumes minimal memory (<50MB RSS), reserving RAM and VRAM for the local `llama.cpp` inference server.
- **Low Latency**: In-process component calls have near-zero overhead compared to network microservices.

### Alternatives Considered
- *Microservices Architecture (FastAPI + Redis + Celery)*: Rejected due to violation of Article XI and excessive memory/complexity overhead on laptop hardware.
- *Node.js / TypeScript Harness*: Rejected because the project ecosystem, tooling, and target local data models align with Python.

---

## 2. Local llama.cpp Inference Client & Interaction Protocol

### Context & Problem
The harness must communicate with a locally hosted `llama.cpp` server serving `FrogNano-4B` via an OpenAI-compatible endpoint (`http://127.0.0.1:8080/v1/chat/completions`) with a 65,536 token context window. Smaller 4B parameter models can struggle with complex tool-calling formatting or occasionally output unescaped JSON.

### Decision
Implement a custom `InferenceClient` using Python's built-in `urllib.request` that supports a **hybrid protocol**:
1. **Primary Protocol**: Native OpenAI function/tool calling (`tools` array parameter, receiving `tool_calls` in response).
2. **Fallback Protocol**: If the model omits `tool_calls` and outputs action blocks in Markdown code fences (e.g., ````action\n{"tool": "write_file", "arguments": {...}}\n````), the parser extracts and validates the payload.
3. **External Configuration**: Server endpoint (`http://127.0.0.1:8080/v1`), model alias (`frognano`), context limits, temperature, and request timeouts (default 180s) are configurable via `.harness/config.json` or environment variables without source modification.

### Rationale
- Standard library `urllib.request` avoids dragging in heavy HTTP client libraries or the full `openai` SDK while maintaining exact compatibility with `llama.cpp` endpoints.
- Hybrid parsing provides robust resilience against small model formatting inconsistencies without failing the entire task.

### Alternatives Considered
- *Official `openai` Python SDK*: Evaluated, but introduces 15+ transitive dependencies (pydantic, httpx, anyio, distro, etc.) and potential version drift.
- *Pure Markdown Action Parsing Only*: Rejected because OpenAI function calling is standard and more cleanly structured when the model follows it.

---

## 3. Tool Gateway & Sandboxed Adapters

### Context & Problem
Article III, IV, and V mandate that no LLM may directly invoke shell or filesystem commands. All model-initiated actions must pass through an independent Tool Gateway that assigns IDs, validates schemas, consults policy, and records audit traces.

### Decision
Build an independent `ToolGateway` with an extensible `ToolRegistry` exposing 9 core tools:
- Filesystem: `read_file`, `list_files`, `search_code`, `write_file`, `apply_patch`
- Terminal: `run_command`
- Testing: `run_tests`
- Git: `git_status`, `git_diff`, `git_commit`

Each tool defines:
- A strict JSON Schema defining parameter types, required fields, and boundary constraints.
- A dedicated execution adapter executing strictly within `project_root`.
- Execution output capture: `exit_code`, `stdout`, `stderr`, `duration_ms`, `affected_files`.

### Rationale
- Completely isolates FrogNano from host system internals.
- Provides predictable, structured outputs for model consumption and audit recording.

### Alternatives Considered
- *Direct Model Shell Access (`bash` tool)*: Strictly prohibited by Article III.
- *Dynamic Tool Loading via Reflection*: Rejected for initial release to ensure rigid security verification of every exposed tool.

---

## 4. Policy Engine & Windows 11 Path Security

### Context & Problem
On Windows 11, path traversal attacks, symbolic link manipulation, case-insensitivity quirks, and Alternate Data Streams (ADS) can allow malicious or hallucinated paths to escape project boundaries or expose secret credentials (`.env`, SSH keys).

### Decision
Implement a deterministic `PolicyEngine` applying strict path normalization:
1. **Path Resolution**: Resolve all target paths via `pathlib.Path(p).resolve()`.
2. **Root Boundary Check**: Ensure `target_path` is strictly within `project_root.resolve()` via `target_path.is_relative_to(project_root)`. Reject paths containing relative traversal (`..`) or device names (`CON`, `PRN`, `AUX`, `NUL`).
3. **Task Scope Enforcement**: Check `target_path` against the task envelope's `allowed_files`. Any attempt to touch or create an undeclared file immediately yields `DENY`.
4. **Secret Scrubbing**: Permanently deny access to `.env`, `.git/`, private keys, and credential stores.
5. **Command Whitelist for `run_command`**: Executable must be in an explicit allowlist (`python`, `pytest`, `git`, `mypy`, `ruff`). Shell evaluation (`shell=True`) is strictly prohibited; all commands use `subprocess.run(args, shell=False)`.

### Rationale
- Enforces zero-trust boundary validation as required by Article III and FR-009 through FR-012.

### Alternatives Considered
- *Relying on relative path strings*: Flawed on Windows due to drive letter changes and mixed forward/backward slashes.
- *Permissive Coder Sandbox*: Violates Article III (Security by Default).

---

## 5. Human Approval Workflow & Operational Lifecycle

### Context & Problem
High-risk operations (e.g., file deletion, package installations, unlisted commands) cannot be autonomously executed under the principle of least privilege. The harness must support both active interactive supervision and unattended background runs.

### Decision
Implement a `HumanApprovalManager` supporting hybrid resolution:
- **Interactive Mode**: If attached to an interactive terminal, prompt the operator inline (`[y/N]`) with operation details, exact arguments, and risk classification.
- **Unattended / Timeout Mode**: If running non-interactively or if an interactive prompt exceeds 60 seconds, create a `PENDING_APPROVAL` record in SQLite and suspend the task.
- **CLI Resolution**: The operator can inspect pending requests via `harness status` and resolve them via `harness approve <id>` or `harness reject <id>`.
- **Argument Binding**: Approval is cryptographically bound to the SHA-256 hash of the exact normalized arguments. If arguments change, approval is immediately invalidated.

### Rationale
- Guarantees safety without deadlocking background or scripted test runs.

---

## 6. SQLite State Management & Tamper-Evident Audit Ledger

### Context & Problem
Article VIII and IX require that execution state survive process termination, system reboots, and inference failures, while maintaining an immutable, traceable history of every tool invocation.

### Decision
Use a local SQLite database at `.harness/state.db` configured with Write-Ahead Logging (`PRAGMA journal_mode = WAL`) and foreign key enforcement (`PRAGMA foreign_keys = ON`).
- **State Tables**: `runs`, `tasks`, `task_attempts`, `approvals`, `checkpoints`.
- **Audit Table**: `audit_events` with SHA-256 hash chaining:
  $$\text{entry\_hash} = \text{SHA256}(\text{prev\_entry\_hash} + \text{event\_type} + \text{payload\_json} + \text{timestamp})$$
- **Crash Recovery**: On `harness resume` or system startup, reconcile SQLite task states against Git commit history. If SQLite marks a task completed but Git has no matching commit, flag a reconciliation error before proceeding.

### Rationale
- SQLite WAL mode ensures transactional durability and fast concurrent reads.
- Hash chaining provides cryptographic tamper-evidence, satisfying Article VIII.

---

## 7. Independent Verification & Clean-Context Retry Loop

### Context & Problem
FrogNano-4B cannot declare its own implementation complete. Prescribed verification commands must be executed independently, and failed tasks must be retried with targeted error diagnostics without exceeding context limits.

### Decision
Implement an `IndependentVerificationEngine`:
1. **Subprocess Isolation**: Runs test commands via `subprocess.run(..., timeout=120, capture_output=True)`.
2. **Deterministic Checks**: Validates exit code 0, verifies that Git diffs contain zero changes outside `allowed_files`, and checks acceptance criteria.
3. **Retry Strategy**: Configurable retry ceiling (default 2). On retry, reset the intermediate tool conversation dialogue and send a clean prompt containing the original task envelope plus only the test failure diagnostics (stderr/stdout, exit code, diff) from the immediately preceding attempt.
4. **Blockage Handling**: After 2 failed retries, mark the task as `BLOCKED`.

### Rationale
- Small coding models suffer severe performance degradation when burdened with multi-turn transcripts of their own prior mistakes. Resetting conversation context with targeted error feedback maximizes correction success.

---

## 8. DAG Task Scheduling & Partial Execution

### Context & Problem
`tasks.md` defines tasks with interdependencies. When an isolated task becomes `BLOCKED`, halting the entire run starves independent parallel branches.

### Decision
Implement a topological sort using Kahn's algorithm in `TaskScheduler`:
- Detect cycles during `harness validate` and `harness plan`.
- Identify ready tasks whose dependencies are strictly `COMPLETED`.
- If a task becomes `BLOCKED`, mark all transitive downstream dependents as `BLOCKED` (cascade), but continue executing unblocked independent branches until all runnable tasks are finished.

### Rationale
- Maximizes autonomous development progress before requiring supervisory human or Gemini intervention.
