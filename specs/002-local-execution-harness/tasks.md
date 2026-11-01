# Tasks: Local Agentic Coding Execution Harness

**Input**: Design documents from `/specs/002-local-execution-harness/` ([plan.md](./plan.md), [spec.md](./spec.md), [data-model.md](./data-model.md), [research.md](./research.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md))
**Constitution**: Governed by [constitution.md](../../.specify/memory/constitution.md) (v2.0.0, 13 Articles)

**Organization**: Tasks are grouped by user story to enable independent implementation, testing, and progressive delivery of each story.

## Format: `- [ ] [TaskID] [P?] [Story?] Description with file path`

- **[P]**: Can run in parallel (different files, no blocking dependencies)
- **[Story]**: User story identifier (`[US1]` through `[US8]`)
- Every task includes explicit target file paths and verifiable constraints.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, directory structure, package configuration, and typing/linting tooling.

- [X] T001 Create project directory structure for `src/frognano_harness/` and `tests/` (`unit/`, `contract/`, `integration/`) per implementation plan
- [X] T002 [P] Create Python package configuration in `pyproject.toml` targeting Python 3.11+ with dev dependencies (`pytest`, `mypy`, `ruff`) and zero required third-party production dependencies
- [X] T003 [P] Configure strict static typing and linting rules in `pyproject.toml` (`mypy` strict mode without unchecked Any escapes, `ruff` PEP 8 rules)
- [X] T004 [P] Define domain exception hierarchy in `src/frognano_harness/exceptions.py` including `HarnessError`, `PolicyViolationError`, `VerificationFailedError`, `BlockedTaskError`, and `ApprovalRequiredError`
- [X] T005 [P] Define runtime configuration dataclass in `src/frognano_harness/config.py` externalizing inference endpoint (default `http://127.0.0.1:8080/v1`), model alias (`frognano`), context limit (65,536 tokens), retry limit (2), and timeouts (120s test, 60s approval)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core domain entities, SQLite database engine, and Git manager that MUST be completed before ANY user story can begin.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 [P] Implement domain entity dataclasses and Enums in `src/frognano_harness/models.py` with immutable dataclasses (`@dataclass(frozen=True)`) covering `TaskStatus` (`PENDING`, `READY`, `RUNNING`, `PENDING_APPROVAL`, `VERIFYING`, `SUCCESS`, `COMPLETED`, `FAILED`, `BLOCKED`), `DecisionType` (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`), `RiskLevel` (`LOW`, `MEDIUM`, `HIGH`), `ApprovalStatus` (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`), `AttemptOutcome`, and `VerificationOutcome`
- [X] T007 [P] Unit tests for domain models and state transitions in `tests/unit/test_models.py` validating entity immutability and enum invariants
- [X] T008 Implement SQLite database connection manager and schema initializer in `src/frognano_harness/state_manager.py` implementing `specs/002-local-execution-harness/contracts/sqlite-schema.sql` at `.harness/state.db` with `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`
- [X] T009 [P] Contract tests for SQLite schema in `tests/contract/test_sqlite_schema.py` verifying all 11 tables, constraints, foreign keys, and indexes
- [X] T010 [P] Implement Git manager in `src/frognano_harness/git_manager.py` to inspect repository status, verify clean working tree, record pre-execution HEAD commit hash, and create task-scoped commits without pushing
- [X] T011 [P] Unit tests for Git manager in `tests/unit/test_git_manager.py` validating dirty tree detection, commit hash retrieval, and commit creation

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - SpecKit Discovery, Task Contract Parsing, and Dependency Graph Generation (Priority: P1) 🎯 MVP Component

**Goal**: Discover SpecKit project, parse `tasks.md`, extract structured task contracts, validate fields, and build dependency DAG with cycle detection.

**Independent Test**: Can be validated by executing `validate` and `plan` against SpecKit projects containing linear, branching, and cyclic task dependencies without requiring an active inference server.

### Tests for User Story 1

- [X] T012 [P] [US1] Unit tests for SpecKit task parser in `tests/unit/test_task_parser.py` validating task ID format (`^[A-Z0-9_-]+$`), extraction of objectives, dependencies, `allowed_files`, criteria, and detection of missing mandatory fields
- [X] T013 [P] [US1] Unit tests for task scheduler in `tests/unit/test_scheduler.py` validating DAG construction, topological sort (Kahn's algorithm), and circular dependency detection

### Implementation for User Story 1

- [X] T014 [US1] Implement SpecKit parser in `src/frognano_harness/task_parser.py` to discover project root, read `constitution.md`, parse `tasks.md`, and return structured `Task` envelopes
- [X] T015 [US1] Implement task scheduler and DAG resolver in `src/frognano_harness/scheduler.py` building dependency graphs, enforcing prerequisite execution, and detecting cycles
- [X] T016 [US1] Integration test for discovery, parsing, and DAG rendering in `tests/integration/test_spec_discovery_and_dag.py`

**Checkpoint**: At this point, User Story 1 is fully functional and can parse and plan any SpecKit project independently.

---

## Phase 4: User Story 2 - Controlled Task Dispatch and Bounded Tool Gateway Execution (Priority: P1)

**Goal**: Connect to local `llama.cpp` endpoint, assemble task-specific context envelopes (<65,536 tokens), and execute tool calls strictly through Tool Gateway schema-validated adapters.

**Independent Test**: Dispatch mock tasks to inference endpoint, verify context envelope assembly, validate tool request schemas, and execute controlled filesystem operations in the project root.

### Tests for User Story 2

- [X] T017 [P] [US2] Contract tests for Tool Gateway in `tests/contract/test_tool_schemas.py` validating all 9 tools against `specs/002-local-execution-harness/contracts/tools.json`
- [X] T018 [P] [US2] Unit tests for inference client in `tests/unit/test_inference_client.py` testing hybrid OpenAI `tools`/`tool_calls` format and markdown action code fence fallback
- [X] T019 [P] [US2] Unit tests for Tool Gateway and adapters in `tests/unit/test_tool_gateway.py` testing tool execution, stdout/stderr capture, and schema failure rejection

### Implementation for User Story 2

- [X] T020 [US2] Implement `InferenceClient` in `src/frognano_harness/inference_client.py` using Python standard library `urllib.request` to communicate with `/v1/chat/completions` supporting hybrid tool-calling protocol
- [X] T021 [US2] Implement `ContextManager` in `src/frognano_harness/context_manager.py` for task envelope assembly, token estimation, and observation history truncation within the 65,536 token ceiling
- [X] T022 [US2] Implement `ToolGateway` and `ToolRegistry` in `src/frognano_harness/tool_gateway.py` enforcing unique tool-call IDs, JSON schema validation, and dispatch to adapters
- [X] T023 [US2] Implement sandboxed runtime adapters in `src/frognano_harness/runtime.py` for filesystem (`read_file`, `list_files`, `search_code`, `write_file`, `apply_patch`), terminal (`run_command`), testing (`run_tests`), and git (`git_status`, `git_diff`, `git_commit`)
- [X] T024 [US2] Integration test for task dispatch and tool execution loop in `tests/integration/test_dispatch_and_gateway.py`

**Checkpoint**: At this point, User Stories 1 and 2 deliver an end-to-end model execution pipeline through the Tool Gateway.

---

## Phase 5: User Story 3 - Policy-Driven Authorization and Interactive Human Approval (Priority: P1)

**Goal**: Evaluate every tool request against risk classification policies before execution, strictly confining operations to project root and `allowed_files`, and holding high-risk actions for human approval.

**Independent Test**: Request tool actions across low, medium, and high-risk operations; verify low/medium in-boundary actions evaluate to `ALLOW`, out-of-boundary actions evaluate to `DENY`, and high-risk actions suspend to `PENDING_APPROVAL` with inline prompt or CLI approval.

### Tests for User Story 3

- [X] T025 [P] [US3] Unit tests for Policy Engine in `tests/unit/test_policy_engine.py` verifying path normalization, project-root sandboxing, `allowed_files` bounds, command allowlist, `.env` secret scrubbing, and risk classification
- [X] T026 [P] [US3] Unit tests for Human Approval Manager in `tests/unit/test_approval_manager.py` verifying inline prompt (`[y/N]`), 60s unattended timeout, SQLite hold, CLI approval, and argument hash binding

### Implementation for User Story 3

- [X] T027 [US3] Implement `PolicyEngine` in `src/frognano_harness/policy_engine.py` applying Windows path normalization, project-root confinement, task-level `allowed_files` enforcement, command allowlisting, and risk classification (`LOW`, `MEDIUM`, `HIGH`)
- [X] T028 [US3] Implement `HumanApprovalManager` in `src/frognano_harness/approval_manager.py` managing `ApprovalRequest` records, interactive terminal prompt (`[y/N]`), 60s unattended timeout, and argument hash binding (`SHA256(normalized_args)`)
- [X] T029 [US3] Integration test for policy authorization and approval workflow in `tests/integration/test_policy_and_approval.py`

**Checkpoint**: User Stories 1, 2, and 3 enforce complete security boundaries and human-in-the-loop governance.

---

## Phase 6: User Story 4 - Independent Verification and Bounded Remediation (Priority: P1)

**Goal**: Independently execute prescribed verification commands, check process exit codes and Git diffs, enforce 2-retry limit, and cascade `BLOCKED` status only to dependent tasks.

**Independent Test**: Execute tasks with passing and failing tests; verify passing tests transition to `SUCCESS`, failing tests trigger clean-context retry (up to 2 attempts), and exhausted retries mark the task `BLOCKED` while independent branches continue.

### Tests for User Story 4

- [X] T030 [P] [US4] Unit tests for Independent Verification Engine in `tests/unit/test_verification_engine.py` testing subprocess test execution, exit code 0 checking, timeout enforcement (120s), and Git diff checking against `allowed_files`

### Implementation for User Story 4

- [X] T031 [US4] Implement `IndependentVerificationEngine` in `src/frognano_harness/verification_engine.py` executing verification commands in isolated subprocesses, capturing exit codes, stdout, stderr, and validating Git diffs
- [X] T032 [US4] Implement clean-context retry packaging in `src/frognano_harness/context_manager.py` resetting intermediate tool conversation dialogue and supplying only original task envelope + immediate prior test failure diagnostics (exit code, test stdout/stderr, git diff)
- [X] T033 [US4] Implement partial graph continuation logic in `src/frognano_harness/scheduler.py` cascading `BLOCKED` status only to direct/transitive dependents while allowing independent DAG branches to continue
- [X] T034 [US4] Integration test for independent verification and bounded retry loop in `tests/integration/test_verification_and_retry.py`

**Checkpoint**: User Stories 1 through 4 deliver evidence-based verification and bounded remediation.

---

## Phase 7: User Story 5 - Immutable Audit Ledger and Task-Level Git Checkpoints (Priority: P1)

**Goal**: Record every tool request, policy decision, approval, and verification outcome in an append-only, SHA-256 hash-chained SQLite ledger, and commit verified tasks individually to Git.

**Independent Test**: Query the SQLite `audit_events` table, verify cryptographic hash chain integrity, verify sensitive credentials are scrubbed, and check individual Git commits referencing task IDs.

### Tests for User Story 5

- [X] T035 [P] [US5] Unit tests for Audit Ledger in `tests/unit/test_audit_ledger.py` verifying append-only logging, SHA-256 hash chaining (`SHA256(prev_hash + event_type + payload + timestamp)`), secret scrubbing, and hash integrity verification

### Implementation for User Story 5

- [X] T036 [US5] Implement `AuditLedger` in `src/frognano_harness/audit_ledger.py` writing append-only events to SQLite with SHA-256 hash chaining, distinguishing requested vs executed arguments, and providing `verify_chain()` integrity method
- [X] T037 [US5] Implement atomic task checkpoint commits in `src/frognano_harness/git_manager.py` staging only authorized files and committing with standardized message `[<task_id>] <title>`
- [X] T038 [US5] Integration test for audit ledger hash chain and Git checkpoint commits in `tests/integration/test_audit_and_checkpoints.py`

**Checkpoint**: User Stories 1 through 5 complete the core P1 execution engine with full auditability and Git checkpoints.

---

## Phase 8: User Story 6 - State Persistence and Crash-Resilient Session Recovery (Priority: P2)

**Goal**: Persist execution runs, task states, attempt counts, and checkpoints in SQLite, and reconcile database state with Git commit history upon `harness resume`.

**Independent Test**: Terminate execution run mid-process, invoke `harness resume`, and verify that completed tasks are skipped and execution resumes from the exact pending task.

### Tests for User Story 6

- [X] T039 [P] [US6] Unit tests for state persistence and reconciliation in `tests/unit/test_state_manager.py` verifying state saves and recovery from interrupted states

### Implementation for User Story 6

- [X] T040 [US6] Implement state persistence methods in `src/frognano_harness/state_manager.py` for task state transitions, attempt logging, and checkpoint tracking
- [X] T041 [US6] Implement crash recovery and Git reconciliation logic in `src/frognano_harness/state_manager.py` verifying SQLite completed tasks against Git commit hashes
- [X] T042 [US6] Integration test for process interruption and session resumption in `tests/integration/test_crash_recovery.py`

**Checkpoint**: Execution progress is now durable across crashes, terminal closures, and reboots.

---

## Phase 9: User Story 7 - Real-Time Telemetry and Supervisory Reporting for Gemini (Priority: P2)

**Goal**: Display real-time CLI execution progress and export structured JSON and Markdown reports to `.harness/reports/` conforming to `contracts/report-schema.json`.

**Independent Test**: Run tasks, trigger `harness report`, and validate exported JSON against `contracts/report-schema.json` and Markdown report for human readability.

### Tests for User Story 7

- [X] T043 [P] [US7] Contract test for supervisory report schema in `tests/contract/test_report_schema.py` validating report output against `specs/002-local-execution-harness/contracts/report-schema.json`

### Implementation for User Story 7

- [X] T044 [US7] Implement supervisory report generator in `src/frognano_harness/reporting.py` exporting JSON and Markdown summaries to `.harness/reports/` with task counts, commit hashes, failure errors, and recommended next actions
- [X] T045 [US7] Integration test for report generation in `tests/integration/test_reporting.py`

**Checkpoint**: Gemini can now asynchronously inspect machine-readable execution results and replan.

---

## Phase 10: User Story 8 - Operator Command Line Interface (Priority: P3)

**Goal**: Implement the 14 Windows PowerShell CLI commands (`init`, `validate`, `plan`, `run`, `resume`, `status`, `task`, `retry`, `approve`, `reject`, `report`, `logs`, `verify`, `audit`) in `src/frognano_harness/cli.py`.

**Independent Test**: Execute all 14 CLI commands with `--help` and sample fixtures in PowerShell; confirm standard exit codes (0 for success, non-zero for failure).

### Tests for User Story 8

- [X] T046 [P] [US8] Contract tests for CLI commands in `tests/contract/test_cli_contract.py` verifying argument parsing, help text, and exit codes for all 14 commands

### Implementation for User Story 8

- [X] T047 [US8] Implement orchestrator coordination loop in `src/frognano_harness/orchestrator.py` tying together scheduler, dispatch, gateway, policy, verification, and audit
- [X] T048 [US8] Implement CLI entry point and all 14 commands in `src/frognano_harness/cli.py` using `argparse`
- [X] T049 [US8] Integration test for CLI execution in `tests/integration/test_cli_e2e.py`

**Checkpoint**: The entire harness can now be driven from Windows PowerShell via all 14 CLI commands.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end quickstart validation, strict static typing verification, code formatting, and documentation.

- [X] T050 [P] Implement end-to-end quickstart validation test in `tests/integration/test_quickstart_validation.py` executing all 6 scenarios from `specs/002-local-execution-harness/quickstart.md`
- [X] T051 [P] Ensure 100% strict type-checking passes with `mypy --strict src/ tests/` with zero unchecked Any escapes
- [X] T052 [P] Run code formatting and linting verification with `ruff check src/ tests/` and `ruff format --check src/ tests/`
- [X] T053 Update project `README.md` at repository root with architecture summary, quickstart guide, CLI reference, and constitutional principles

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (Phase 1) — BLOCKS all user stories.
- **User Story 1 (Phase 3, P1)**: Depends on Foundational (Phase 2).
- **User Story 2 (Phase 4, P1)**: Depends on User Story 1 (needs `Task` envelopes).
- **User Story 3 (Phase 5, P1)**: Depends on User Story 2 (intercepts tool requests from Tool Gateway).
- **User Story 4 (Phase 6, P1)**: Depends on User Story 2 (verifies executed code).
- **User Story 5 (Phase 7, P1)**: Depends on User Story 3 & 4 (audits tool calls and commits verified tasks).
- **User Story 6 (Phase 8, P2)**: Depends on User Story 5 (persists run state and reconciles checkpoints).
- **User Story 7 (Phase 9, P2)**: Depends on User Story 5 (reports on completed and blocked tasks).
- **User Story 8 (Phase 10, P3)**: Depends on all prior User Stories (exposes complete CLI control surface).
- **Polish (Phase 11)**: Depends on all User Stories being complete.

### Parallel Opportunities

- **Phase 1 (Setup)**: `T002`, `T003`, `T004`, `T005` can all execute in parallel after `T001`.
- **Phase 2 (Foundational)**: `T006`, `T007`, `T009`, `T010`, `T011` can execute in parallel while `T008` is being implemented.
- **Within Each Story**: All tests marked `[P]` can be authored in parallel before implementation.
- **Across Stories (post-P1)**: User Story 6 (State Persistence) and User Story 7 (Supervisory Reporting) can proceed in parallel once P1 stories are complete.

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1: Setup (`T001`–`T005`).
2. Complete Phase 2: Foundational (`T006`–`T011`).
3. Complete Phase 3: User Story 1 (`T012`–`T016`).
4. **STOP and VALIDATE**: Validate that the harness parses any `tasks.md` file, detects circular dependencies, and displays topological execution order.

### Incremental Delivery (Core P1 Pipeline)
1. Add User Story 2: Model dispatch + Tool Gateway execution (`T017`–`T024`).
2. Add User Story 3: Policy Engine authorization + Human approval (`T025`–`T029`).
3. Add User Story 4: Independent verification + bounded retry loop (`T030`–`T034`).
4. Add User Story 5: Audit ledger hash chaining + Git checkpoints (`T035`–`T038`).
5. **Full Autonomous Implementation Loop Ready**: The harness can now execute real tasks, verify them, commit them, and record tamper-evident audit traces.

### Production Readiness (P2 + P3)
1. Add User Story 6: Crash recovery and Git reconciliation (`T039`–`T042`).
2. Add User Story 7: Supervisory reporting for Gemini (`T043`–`T045`).
3. Add User Story 8: Full 14-command CLI interface (`T046`–`T049`).
4. Polish: E2E quickstart validation, `mypy --strict`, `ruff`, and README (`T050`–`T053`).
