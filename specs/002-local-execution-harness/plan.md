# Implementation Plan: Local Agentic Coding Execution Harness

**Branch**: `002-local-execution-harness` | **Date**: 2026-11-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-local-execution-harness/spec.md` and requirements from `specify-pr.txt`.

---

## Summary

Build a deterministic, locally operated, crash-resilient software engineering execution harness on Windows 11 connecting GitHub SpecKit with local coding models (`FrogNano-4B` via `llama.cpp` OpenAI-compatible endpoint). The architecture enforces strict separation between planning (Gemini), specification structuring (SpecKit), orchestration (Python engine), implementation (FrogNano), authorization (Policy Engine), tool sandboxing (Tool Gateway), independent verification (Verification Engine), and audit logging (SQLite Audit Ledger). All operations are executed locally with zero external paid API dependencies.

---

## Technical Context

**Language/Version**: Python 3.11+ (modern typing, dataclasses, pattern matching, exception groups).

**Primary Dependencies**: Python Standard Library (`sqlite3`, `subprocess`, `pathlib`, `json`, `argparse`, `dataclasses`, `urllib.request`, `hashlib`, `logging`, `typing`, `enum`). Development tools: `pytest` (test execution), `mypy` (static type checking in strict mode), `ruff` (formatting and linting).

**Storage**: Local SQLite database (`.harness/state.db`) configured with Write-Ahead Logging (`WAL` mode) and foreign keys enabled.

**Testing**: `pytest` covering unit, contract, and integration tests across all 15 logical components.

**Target Platform**: Windows 11 (PowerShell 7+ / `pwsh`), NVIDIA RTX 4060 Laptop GPU (8 GB VRAM), 16 GB system RAM.

**Project Type**: Local Command-Line Application / Developer Execution Harness.

**Performance Goals**:
- Harness startup / discovery: <1.5s
- DAG dependency resolution: <500ms for 100+ tasks
- Tool Gateway dispatch and policy validation overhead: <10ms per tool call
- Recovery and restart reconciliation: <3s
- Supervisory report generation: <2s

**Constraints**:
- Single-process Python application footprint (<50 MB RSS memory).
- Context window ceiling: 65,536 tokens per slot on local `llama.cpp` endpoint (`http://127.0.0.1:8080/v1`).
- Bounded retries: Maximum 2 retries per task before transitioning to `BLOCKED`.
- 100% local operation: 0 paid external API calls.

**Scale/Scope**: 15 cohesive logical components, 9 core tools in Tool Gateway, 14 CLI commands, supporting projects up to hundreds of atomic tasks.

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Article / Invariant | Status | Compliance Verification |
|---------------------|--------|-------------------------|
| **Core Engineering Principle** | PASSED | Clear separation: Gemini plans, SpecKit structures, Python orchestrates, FrogNano implements, Policy authorizes, Gateway executes, Engine verifies, Ledger remembers. |
| **Article I — Separation of Intelligence & Execution** | PASSED | FrogNano cannot bypass Tool Gateway; Gemini cannot override deterministic security policy; verification is strictly independent. |
| **Article II — Deterministic Orchestration** | PASSED | Orchestrator uses an explicit finite state machine with monotonic transitions; DAG dependency enforcement via Kahn's algorithm; state persisted in SQLite. |
| **Article III — Security by Default** | PASSED | All tool calls pass through Tool Gateway; Policy Engine enforces project-root sandboxing, pre-declared `allowed_files`, command allowlists, and `.env` secret scrubbing. |
| **Article IV — Independent Authorization & Verification** | PASSED | No model self-authorization or self-attestation; completion requires independent test runner exit code 0 and Git diff validation. |
| **Article V — Tool Execution Contracts** | PASSED | Strict JSON Schemas for all 9 tools defined in [contracts/tools.json](./contracts/tools.json); inputs validated before execution; unique IDs assigned. |
| **Article VI — Immutable Task Scope** | PASSED | File operations restricted to `allowed_files`; scope creep or out-of-boundary access immediately returns `DENY` / `BLOCKED`. |
| **Article VII — Test-Driven & Evidence-Based Development** | PASSED | Prescribed verification commands executed in isolated subprocesses; tests cannot be skipped; exit code 0 and diffs captured. |
| **Article VIII — Auditability & Traceability** | PASSED | Append-only SQLite table with SHA-256 hash chaining; complete tool lifecycle tracked; secrets scrubbed. |
| **Article IX — Recoverability & State Persistence** | PASSED | SQLite WAL database survives crashes; `resume` reconciles database state against Git commit history before restarting. |
| **Article X — Resource Efficiency** | PASSED | Designed for Windows 11 + RTX 4060 8GB VRAM; stdlib-first, lean memory (<50MB); clean context envelopes avoid token exhaustion. |
| **Article XI — Simplicity & Maintainability** | PASSED | Single local Python package; stdlib-first; SQLite; zero unnecessary microservices or external message queues. |
| **Article XII — Git Integrity** | PASSED | Verified tasks receive individual Git commits referencing task ID; no automatic remote pushes; pre-execution working tree checks. |
| **Article XIII — Controlled Evolution** | PASSED | Modular architecture supports future worktrees and multi-model adapters without altering security invariants. |

*Gate Result*: **ALL GATES PASSED** with 0 violations.

---

## Project Structure

### Documentation (this feature)

```text
specs/002-local-execution-harness/
├── plan.md              # This implementation plan
├── research.md          # Phase 0 architectural & technical decisions
├── data-model.md        # Phase 1 domain entities, state machines & SQLite mapping
├── quickstart.md        # Phase 1 runnable validation guide
├── checklists/
│   └── requirements.md  # Specification quality checklist
├── contracts/
│   ├── tools.json       # JSON schemas for Tool Gateway registry
│   ├── cli.md           # Specification of 14 CLI commands
│   ├── sqlite-schema.sql# SQLite DDL schema
│   └── report-schema.json # JSON schema for Gemini supervisory reports
└── tasks.md             # Phase 2 task breakdown (created by /speckit-tasks)
```

### Source Code (repository root)

```text
src/
└── frognano_harness/
    ├── __init__.py
    ├── config.py             # Externalized runtime & environment configuration
    ├── exceptions.py         # Domain error hierarchy
    ├── models.py             # Typed immutable domain entities & Enums
    ├── task_parser.py        # SpecKit tasks.md & constitution parser
    ├── scheduler.py          # DAG builder, topological sort, cycle detection
    ├── context_manager.py    # Task context assembly & retry error packaging
    ├── inference_client.py   # llama.cpp OpenAI-compatible HTTP client
    ├── tool_gateway.py       # Tool registry, JSON schema validation, dispatch
    ├── policy_engine.py      # Authorization engine, path normalizer, sandboxing
    ├── approval_manager.py   # Human approval manager (inline & SQLite hold)
    ├── runtime.py            # Execution adapters (fs, terminal, tests, git)
    ├── verification_engine.py# Subprocess test runner, exit codes & diff checker
    ├── git_manager.py        # Checkpoint commits & working tree status
    ├── audit_ledger.py       # Append-only hash-linked SQLite audit ledger
    ├── state_manager.py      # Persistent task state & crash reconciliation
    ├── reporting.py          # Structured JSON & Markdown reports for Gemini
    ├── orchestrator.py       # Main state machine execution coordinator
    └── cli.py                # Windows PowerShell CLI entry point (14 commands)

tests/
├── conftest.py               # Shared pytest fixtures & mock environments
├── unit/
│   ├── test_models.py
│   ├── test_task_parser.py
│   ├── test_scheduler.py
│   ├── test_context_manager.py
│   ├── test_policy_engine.py
│   ├── test_approval_manager.py
│   ├── test_tool_gateway.py
│   ├── test_runtime_adapters.py
│   ├── test_verification_engine.py
│   ├── test_audit_ledger.py
│   └── test_state_manager.py
├── contract/
│   ├── test_tool_schemas.py
│   ├── test_cli_contract.py
│   ├── test_sqlite_schema.py
│   └── test_report_schema.py
└── integration/
    ├── test_e2e_mock_run.py
    ├── test_recovery_flow.py
    └── test_policy_rejection_flow.py
```

**Structure Decision**: Single Python package layout (`src/frognano_harness/`) with dedicated `tests/` tree divided into `unit/`, `contract/`, and `integration/`. Strictly complies with Article XI (Simplicity and Maintainability).

---

## Complexity Tracking

> *No constitutional violations or unjustified complexity introduced. All gates passed.*

| Area | Decision | Justification |
|------|----------|---------------|
| Architecture | Monolithic single-process Python package | Adheres to Article XI; avoids distributed complexity, latency, and memory bloat on laptop hardware. |
| Model Client | Standard library `urllib.request` | Adheres to stdlib-first rule; eliminates third-party HTTP client dependencies. |
| Persistence | Local SQLite with WAL mode | Compact, zero-configuration local durability with foreign key guarantees. |
| Audit Integrity | In-database SHA-256 hash chaining | Delivers cryptographic tamper-evidence without external blockchain or centralized logging infrastructure. |
