# Feature Specification: Local Agentic Coding Execution Harness

**Feature Branch**: `002-local-execution-harness`

**Created**: 2026-11-01

**Status**: Draft

**Input**: User description: "Build a deterministic, locally operated, resumable software engineering execution harness that connects GitHub SpecKit with a locally hosted coding model through an OpenAI-compatible inference endpoint."

## Clarifications

### Session 2026-11-01
- Q: What interaction protocol should the harness use to receive tool requests and code edits from the local FrogNano-4B model via llama.cpp? (FR-004) → A: Hybrid protocol (prioritize native OpenAI tool calling schemas `tools` / `tool_calls`, falling back to parsing structured markdown action code fences if tool calls are omitted or malformed).
- Q: Where should the SQLite persistence database, audit records, and runtime artifacts be stored within the workspace? (FR-013) → A: Dedicated `.harness/` directory in the project root (`.harness/state.db`, `.harness/logs/`, `.harness/reports/`), automatically excluded from Git tracking via `.gitignore`.
- Q: How should the harness enforce file modification boundaries when an implementation task requires creating or editing a file? (FR-005) → A: Explicit pre-declaration only (bounded autonomy: the planner pre-declares all affected and created files in `allowed_files` in `tasks.md`, and the coder model cannot create or touch undeclared files).
- Q: How should the harness handle human approval requests when running in an interactive terminal versus an unattended session? (FR-013) → A: Hybrid interactive/unattended handling: prompt inline interactively in the terminal (`[y/N]`); if running non-interactively or on prompt timeout (default 60 seconds), pause the task into SQLite `PENDING_APPROVAL` state for external resolution via `harness approve <id>` / `harness reject <id>`.
- Q: How should the Context Manager assemble the prompt envelope when retrying a failed task implementation? (FR-004) → A: Selective error feedback with reset conversation: reset intermediate multi-turn tool dialogue, providing the clean task envelope plus only the immediate prior verification failure outputs (exit code, test stdout/stderr, and current git diff).
- Q: When a task exhausts its retries and transitions to BLOCKED, how should the scheduler handle remaining independent tasks in the dependency graph? (FR-003) → A: Continue independent branches: halt only the blocked task and its downstream dependents; continue executing ready, independent tasks across other branches of the DAG until all runnable work is complete, then generate an escalation report for Gemini.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - SpecKit Discovery, Task Contract Parsing, and Dependency Graph Generation (Priority: P1)

As a software engineer using GitHub SpecKit for project planning, I want the harness to automatically discover project specifications, parse `tasks.md`, extract structured task contracts, and construct a dependency graph, so that tasks are ordered deterministically and execution prerequisites are verified before any model invocation.

**Why this priority**: Foundational prerequisite for all harness operations. The system cannot safely or deterministically dispatch tasks without parsing the contract, validating required fields, detecting circular dependencies, and computing the topological execution order.

**Independent Test**: Can be validated by executing `validate` and `plan` CLI commands against SpecKit projects containing linear, branching, and cyclic task dependencies without requiring an active inference server.

**Acceptance Scenarios**:

1. **Given** a SpecKit project containing a valid `tasks.md` and `constitution.md`, **When** the operator runs `harness validate` or `harness plan`, **Then** the harness parses all task definitions, extracts dependencies and file boundaries, constructs an execution DAG, and renders the ordered execution plan in the console.
2. **Given** a `tasks.md` file containing a circular dependency (e.g., Task A depends on Task B, which depends on Task A), **When** the operator runs `harness validate`, **Then** the harness detects the cycle, halts planning, and reports an error identifying the cyclic loop.
3. **Given** a `tasks.md` file with missing mandatory execution fields (such as acceptance criteria or verification commands), **When** the operator runs `harness validate`, **Then** the harness flags the missing contract elements with clear remediation instructions.

---

### User Story 2 - Controlled Task Dispatch and Bounded Tool Gateway Execution (Priority: P1)

As an engineer running local models on Windows 11, I want the harness to assemble task-specific context envelopes and dispatch them to the local model endpoint via a strict Tool Gateway, so that the model can inspect code and perform file modifications strictly through validated tool contracts.

**Why this priority**: Core execution capability. Connects the high-level task specification to the local model (FrogNano-4B via llama.cpp) and enforces that no model action directly touches the host operating system, filesystem, or shell.

**Independent Test**: Can be tested by dispatching an atomic task to a local inference endpoint with mock repository files, verifying that prompt envelopes contain relevant specification extracts, file operations are restricted to `allowed_files`, and model tool requests pass through schema validation in the Tool Gateway.

**Acceptance Scenarios**:

1. **Given** an eligible task and an active local inference server at `http://127.0.0.1:8080/v1`, **When** the harness dispatches the task, **Then** it sends a structured task envelope containing the objective, relevant specification sections, and allowed file boundaries within a configurable token context ceiling (default 65,536 tokens).
2. **Given** an active model implementation session, **When** the model requests a registered tool (`read_file`, `list_files`, `search_code`, `write_file`, `apply_patch`), **Then** the Tool Gateway assigns a unique tool-call ID, validates arguments against the tool's JSON schema, checks permissions, and executes the adapter in a controlled project sandbox.
3. **Given** an active model implementation session, **When** the model attempts to invoke an unregistered tool or provides arguments failing schema validation, **Then** the Tool Gateway rejects the call, records an invalid call attempt, and returns structured error feedback to the model.

---

### User Story 3 - Policy-Driven Authorization and Interactive Human Approval (Priority: P1)

As a security-conscious engineer, I want every tool operation evaluated against risk classification policies before execution, with high-risk operations held for human approval, so that autonomous actions cannot harm the host system or exceed permitted boundaries.

**Why this priority**: Implements Article III (Security by Default) and Article IV (Independent Authorization). Guarantees that neither the model nor an external prompt can authorize privileged or destructive operations.

**Independent Test**: Can be tested by simulating tool requests across low-risk (reading permitted files), medium-risk (writing declared files), and high-risk operations (deleting files, installing packages, executing unlisted commands). Validates that low/medium risk actions within boundaries evaluate to `ALLOW`, out-of-boundary actions evaluate to `DENY`, and high-risk actions enter `REQUIRE_APPROVAL` until approved via CLI.

**Acceptance Scenarios**:

1. **Given** a tool request for reading or searching files within pre-declared `allowed_files`, **When** the Policy Engine evaluates the request, **Then** it classifies the operation as low-risk and returns an `ALLOW` decision.
2. **Given** a tool request to modify files outside `allowed_files` or access sensitive secrets (`.env`, credentials, private keys), **When** the Policy Engine evaluates the request, **Then** it immediately returns a `DENY` decision, blocks execution, and logs a boundary violation.
3. **Given** a high-risk tool request (e.g., package installation, file deletion, out-of-scope system modification), **When** the Policy Engine evaluates the request, **Then** it returns `REQUIRE_APPROVAL` and creates a pending approval record; if the session is attached to an interactive terminal, the harness prompts the operator inline (`[y/N]`), and if non-interactive or unattended, it transitions the task to SQLite `PENDING_APPROVAL` state, halting further autonomous progress until resolved.
4. **Given** a pending approval request, **When** the operator runs `harness approve <approval_id>`, **Then** the operation resumes and executes; if the operator runs `harness reject <approval_id>`, **Then** the operation is canceled and a rejection response is returned to the model.

---

### User Story 4 - Independent Verification and Bounded Remediation (Priority: P1)

As a project supervisor, I want the harness to independently verify all code changes using prescribed test commands and deterministic checks rather than trusting the model's assertions, and to automatically initiate bounded corrections on failure, so that incomplete or flawed implementations are never accepted.

**Why this priority**: Implements Article IV and Article VII. Model self-reporting of success is untrusted; task completion requires independently collected evidence of passing tests, zero exit codes, and clean file diffs.

**Independent Test**: Can be tested with mock test scripts that return 0 or non-zero exit codes. Validates that passing tests transition tasks to `PASSED`, while failing tests trigger up to 2 correction attempts before escalating the task to `BLOCKED`.

**Acceptance Scenarios**:

1. **Given** a task implementation completed by FrogNano, **When** the harness enters the verification phase, **Then** the Independent Verification Engine executes prescribed verification commands in isolated subprocesses, capturing exit codes, standard output, standard error, execution duration, and Git diffs.
2. **Given** an implementation where all verification commands exit with code 0 and file modifications strictly match allowed boundaries, **When** verification concludes, **Then** the engine records a `PASSED` outcome and advances the task to Git checkpointing.
3. **Given** an implementation where any verification command fails (non-zero exit code or mismatched diff), **When** the attempt count is less than the retry limit (default 2), **Then** the Context Manager resets intermediate multi-turn tool dialogue and packages the failure logs (exit code, test stdout/stderr, and git diff) into a clean correction envelope for FrogNano.
4. **Given** an implementation that continues to fail after exhausting the retry limit (2 retries), **When** verification fails on the final attempt, **Then** the harness marks the task as `BLOCKED`, halts only its downstream dependent tasks, continues executing any independent ready tasks in the DAG, and generates a consolidated escalation report for Gemini upon run completion.

---

### User Story 5 - Immutable Audit Ledger and Task-Level Git Checkpoints (Priority: P1)

As an auditor and software engineer, I want every tool invocation, policy decision, approval, and verification result recorded in an append-only, hash-linked SQLite ledger, and every successfully verified task committed individually to Git, so that execution history is fully traceable and reproducible.

**Why this priority**: Implements Article VIII (Auditability & Traceability) and Article XII (Git Integrity). Essential for post-mortem analysis, accountability, and atomic rollbacks.

**Independent Test**: Can be tested by running tasks and querying the SQLite audit tables and Git log, confirming that audit records form a verifiable hash chain, distinguish requested from executed arguments, exclude sensitive secrets, and each verified task corresponds to a single Git commit referencing the task ID.

**Acceptance Scenarios**:

1. **Given** any tool call request, **When** it traverses the Tool Gateway and Policy Engine, **Then** the Audit Ledger records an append-only event containing tool-call ID, run ID, task ID, model identity, normalized arguments hash, authorization decision, execution timestamps, exit code, and verification outcome.
2. **Given** an audited tool call, **When** inspected via `harness audit <tool_call_id>`, **Then** the system displays the complete lifecycle of the call, including distinction between requested arguments and actual executed arguments.
3. **Given** a successfully verified task, **When** the harness finalizes the task, **Then** it stages only authorized file modifications, commits them with a standardized message referencing the task ID and title, updates SQLite with the commit hash, and never pushes to a remote repository.

---

### User Story 6 - State Persistence and Crash-Resilient Session Recovery (Priority: P2)

As a developer running long execution sequences, I want all execution states persisted in SQLite and reconciled against the Git repository on startup, so that crashes, restarts, or interruptions do not lose progress or repeat completed work.

**Why this priority**: Implements Article IX (Recoverability & State Persistence). Real-world harness environments suffer disconnections, terminal closures, and reboots; recoverability ensures continuity without duplicate operations.

**Independent Test**: Can be tested by initiating a multi-task run, forcefully terminating the harness process mid-execution, and executing `harness resume`. Validates that the database reconciles with Git commits, completed tasks remain marked complete, and execution resumes cleanly from the exact interrupted task.

**Acceptance Scenarios**:

1. **Given** an ongoing execution run, **When** the process is terminated abruptly (e.g., Ctrl+C or machine restart), **Then** all previously committed tasks and SQLite checkpoint records remain durable and consistent.
2. **Given** an interrupted execution run, **When** the operator runs `harness resume`, **Then** the harness inspects the SQLite database, validates the working tree against Git commits, skips all `COMPLETED` tasks, and resumes execution from the next pending task in the DAG.
3. **Given** an interrupted task with uncommitted or partial workspace modifications, **When** recovery occurs, **Then** the harness detects uncommitted artifacts, prompts or resets to the last clean task checkpoint, and prevents duplicate side effects.

---

### User Story 7 - Real-Time Telemetry and Supervisory Reporting for Gemini (Priority: P2)

As a system architect supervising automated implementation via Gemini, I want real-time CLI status and structured machine-readable reports exported to `.harness/reports/`, so that I can monitor progress, diagnose blockers, and update SpecKit specifications without manual copying.

**Why this priority**: Implements Article I (Separation of Intelligence and Execution). Closes the loop between the execution harness and the supervisory planning intelligence (Gemini/Antigravity).

**Independent Test**: Can be tested by running tasks and executing `harness status` and `harness report`, verifying that terminal outputs display active task telemetry and report files in `.harness/reports/` contain structured JSON and Markdown summaries of completed tasks, commits, test traces, and blockers.

**Acceptance Scenarios**:

1. **Given** an active execution run, **When** viewing the CLI terminal, **Then** the harness displays real-time execution progress: active task ID, attempt counter, model response latency, tool call count, and queue status.
2. **Given** a completed, interrupted, or blocked execution run, **When** the operator runs `harness report`, **Then** the harness exports comprehensive JSON and Markdown reports containing overall progress percentage, completed tasks, failed/blocked tasks, Git commit hashes, authorization denials, and actionable recommendations for Gemini replanning.

---

### User Story 8 - Operator Command Line Interface (Priority: P3)

As an engineer managing the execution lifecycle, I want a complete set of CLI commands compatible with Windows PowerShell, so that I can initialize, inspect, execute, approve, retry, and audit the entire system from the terminal.

**Why this priority**: Provides the primary user-facing control surface for the local execution harness on Windows 11.

**Independent Test**: Can be tested by executing each of the 14 commands in Windows PowerShell (`pwsh`) with `--help` and standard argument fixtures, verifying exit codes and expected outputs.

**Acceptance Scenarios**:

1. **Given** a Windows 11 terminal running PowerShell, **When** the operator runs any of the 14 commands (`init`, `validate`, `plan`, `run`, `resume`, `status`, `task`, `retry`, `approve`, `reject`, `report`, `logs`, `verify`, `audit`), **Then** the CLI executes correctly, returns standardized exit codes (0 for success, non-zero for failure), and provides clear human-readable output.

---

### Edge Cases

- **Inference Server Disconnection**: If the llama.cpp server at `http://127.0.0.1:8080/v1` becomes unreachable or drops connection during generation, the harness MUST capture the connection error, apply bounded exponential backoff (e.g., 3 retries over 30s), and transition to `BLOCKED` if unreachable, alerting the operator without crashing.
- **Malformed Model Output**: If FrogNano produces unparseable JSON or invalid tool schemas, the harness MUST attempt fallback parsing via structured markdown code fences. If still invalid, it MUST count an attempt failure and provide targeted schema error diagnostics in the retry prompt.
- **Dirty Pre-Execution Working Tree**: If uncommitted changes exist in the Git repository before task execution starts, the harness MUST warn the user and refuse to run until changes are committed, stashed, or discarded.
- **Hanging Verification Commands**: If a test command hangs (e.g., infinite loop, waiting on stdin), the harness MUST enforce a strict per-command execution timeout (default 120 seconds), forcefully terminate the subprocess, and record a timeout failure.
- **Path Traversal & Symlink Attacks**: If a tool request contains relative path traversal (`../` or `..\`) or symlinks that resolve outside the project root, the Policy Engine MUST immediately deny the request and record a security violation.
- **Context Window Token Ceiling**: If accumulated task instructions and source files approach the 65,536 token context limit, the Context Manager MUST truncate historical tool observation outputs while strictly preserving task objectives, acceptance criteria, and system constraints.
- **Database / Repository Inconsistency**: If SQLite records a task as `COMPLETED` but the corresponding Git commit is missing, the recovery manager MUST flag the discrepancy, halt automatic resumption, and request operator review.
- **Approval Prompt Timeout in Unattended Mode**: If an approval-required operation triggers while running non-interactively or if an interactive terminal prompt times out (default 60 seconds without operator input), the harness MUST transition the task to `PENDING_APPROVAL` in SQLite, release the current run worker, and log the approval ID for later resolution via `harness approve <approval_id>`.
- **Secret & Credential Exposure**: Any tool request attempting to read, write, or transmit `.env` files, API keys, or certificates MUST be denied unconditionally; the Audit Ledger MUST scrub sensitive values before persisting.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST discover the project root, read `constitution.md`, `spec.md`, and `plan.md`, and parse standard GitHub SpecKit `tasks.md` files.
- **FR-002**: System MUST extract structured task envelopes from `tasks.md`, including Task ID, title, objective, description, dependencies, allowed read/write paths, requirements, acceptance criteria, and verification commands.
- **FR-003**: System MUST construct a Directed Acyclic Graph (DAG) of task dependencies, detect dependency cycles, flag malformed definitions, compute topological execution sequence, and support partial graph execution where a `BLOCKED` task halts only its transitive dependents while allowing independent DAG branches to continue executing to completion.
- **FR-004**: System MUST assemble task-specific context envelopes within a configurable token limit (default 65,536 tokens per slot) and dispatch them to the local inference server (`http://127.0.0.1:8080/v1`) using model alias `frognano`.
- **FR-005**: System MUST support a hybrid model interaction protocol: prioritizing native OpenAI tool calling schemas (`tools` / `tool_calls`) and falling back to parsing structured markdown action code fences if tool calls are omitted or malformed.
- **FR-006**: System MUST route 100% of model-requested operations through an independent Tool Gateway; direct filesystem, process, or network access by the model is strictly prohibited.
- **FR-007**: Tool Gateway MUST implement an extensible registry containing at least:
  - Filesystem: `read_file`, `list_files`, `search_code`, `write_file`, `apply_patch`
  - Terminal: `run_command`
  - Testing: `run_tests`
  - Git: `git_status`, `git_diff`, `git_commit`
- **FR-008**: Every tool MUST have a unique identifier, strict JSON input schema, explicit permissions, defined execution behavior, structured output, error handling, and audit events.
- **FR-009**: System MUST evaluate every tool request via a deterministic Policy Engine considering tool identity, arguments, project root, task identity, allowed file boundaries, command allowlists, and risk classification before execution.
- **FR-010**: Policy Engine decisions MUST be strictly one of `ALLOW`, `DENY`, or `REQUIRE_APPROVAL`. Low-risk operations (reading permitted files) MAY execute automatically; medium-risk operations (writing allowed files, running permitted tests) MAY execute within boundaries; high-risk operations (deleting files, modifying dependencies, running unlisted commands) MUST require human approval.
- **FR-011**: System MUST strictly confine file operations to the project root and enforce task-specific `allowed_files` boundaries; any file created or modified MUST be pre-declared in `allowed_files`, and attempts to touch undeclared files MUST be blocked immediately.
- **FR-012**: System MUST sanitize and normalize all file paths on Windows 11, guarding against path traversal (`..`), alternate data streams, and symbolic link escape.
- **FR-013**: System MUST provide a Human Approval Manager that generates unique approval IDs, captures exact operations and arguments, and supports hybrid approval resolution: prompting inline interactively in the terminal (`[y/N]`) during attached sessions, or pausing the task into a SQLite `PENDING_APPROVAL` state for external resolution via `harness approve <id>` / `harness reject <id>` when running unattended, non-interactively, or on prompt timeout (default 60 seconds).
- **FR-014**: Changing arguments after approval MUST invalidate the approval and require a new authorization decision.
- **FR-015**: System MUST execute authorized operations via controlled execution adapters, capturing stdout, stderr, exit codes, execution duration, and affected files while enforcing execution timeouts.
- **FR-016**: System MUST independently verify task implementations via an Independent Verification Engine; model self-attestation of completion MUST NOT be accepted.
- **FR-017**: Verification Engine MUST independently execute prescribed test commands in isolated subprocesses, validate exit codes, check Git diffs, detect unauthorized file modifications, and verify that acceptance criteria are satisfied.
- **FR-018**: Verification outcomes MUST be strictly `PASSED`, `FAILED`, `INCOMPLETE`, or `NEEDS_HUMAN_REVIEW`.
- **FR-019**: System MUST support bounded correction retries (default 2 retries per task) upon verification failure; retry envelopes MUST reset intermediate tool conversation dialogue and provide only the clean task envelope with the immediate preceding attempt's failure diagnostics (exit codes, test stdout/stderr, and git diff). Tasks failing after retry exhaustion MUST transition to `BLOCKED` and escalate to Gemini.
- **FR-020**: System MUST record all tool requests, arguments, policy decisions, approvals, actual executed arguments, results, timestamps, and verification outcomes in an append-only, hash-linked SQLite Audit Ledger in `.harness/state.db`.
- **FR-021**: Sensitive credentials, keys, and tokens MUST be detected and excluded from Audit Ledger records and model prompts.
- **FR-022**: System MUST create an individual Git commit for each successfully verified task, formatting the message with the task ID and title, and MUST NEVER push automatically to remote repositories.
- **FR-023**: System MUST persist all run metadata, task states, attempt counts, checkpoints, and commit hashes in SQLite (`.harness/state.db`), keeping execution logs in `.harness/logs/`.
- **FR-024**: System MUST reconcile persisted SQLite state with the Git working tree upon startup, enabling safe resumption via `harness resume` without re-running completed tasks.
- **FR-025**: System MUST generate structured machine-readable reports (JSON and Markdown) in `.harness/reports/` summarizing run progress, completed tasks, failed tasks, Git commits, test results, and recommendations for Gemini replanning.
- **FR-026**: System MUST provide a unified Windows PowerShell CLI supporting 14 commands: `init`, `validate`, `plan`, `run`, `resume`, `status`, `task`, `retry`, `approve`, `reject`, `report`, `logs`, `verify`, and `audit`.
- **FR-027**: All runtime configuration (inference endpoints, model aliases, context ceilings, retry limits, timeouts) MUST be externalized and configurable without modifying application source code.

### Key Entities *(include if feature involves data)*

- **Task**: The atomic work unit parsed from SpecKit `tasks.md`. Attributes: `task_id`, `title`, `description`, `objective`, `dependencies`, `allowed_files`, `acceptance_criteria`, `verification_commands`, `status` (`PENDING`, `READY`, `RUNNING`, `SUCCESS`, `FAILED`, `BLOCKED`).
- **Execution Run**: A single session of the execution harness. Attributes: `run_id`, `project_root`, `start_time`, `end_time`, `status`, `model_endpoint`, `total_tasks`, `completed_tasks`, `failed_tasks`, `blocked_tasks`.
- **Task Attempt**: An individual execution cycle for a task. Attributes: `attempt_id`, `run_id`, `task_id`, `attempt_number`, `prompt_tokens`, `completion_tokens`, `model_response`, `diff`, `created_at`.
- **Tool Call Request**: A model-generated request to execute an operational tool. Attributes: `tool_call_id`, `task_id`, `tool_name`, `raw_arguments`, `normalized_arguments`, `arguments_hash`, `timestamp`.
- **Authorization Decision**: A deterministic policy ruling for a tool request. Attributes: `decision_id`, `tool_call_id`, `decision` (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`), `risk_level`, `policy_rule`, `reason`.
- **Approval Request**: An interactive hold on a high-risk operation. Attributes: `approval_id`, `tool_call_id`, `task_id`, `operation`, `exact_arguments`, `risk_level`, `status` (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`), `created_at`, `resolved_at`.
- **Tool Execution Event**: The recorded execution of an authorized tool. Attributes: `execution_id`, `tool_call_id`, `exit_code`, `stdout_ref`, `stderr_ref`, `affected_files`, `duration_ms`, `result_hash`.
- **Verification Record**: The recorded outcome of verification checks for an attempt. Attributes: `verification_id`, `attempt_id`, `command`, `exit_code`, `stdout`, `stderr`, `outcome` (`PASSED`, `FAILED`, `INCOMPLETE`), `timestamp`.
- **Audit Entry**: An immutable, hash-linked log entry in SQLite. Attributes: `entry_id`, `prev_entry_hash`, `entry_hash`, `event_type`, `payload_json`, `timestamp`.
- **State Checkpoint**: Durable tracking mapping tasks to their Git commit hashes, completion timestamps, and operational status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tasks defined in valid SpecKit `tasks.md` files are discovered, parsed, and scheduled into an execution DAG without manual data re-entry.
- **SC-002**: 100% of model-initiated filesystem, shell, and Git operations pass through the Tool Gateway; 0 operations bypass gateway schema and authorization checks.
- **SC-003**: 100% of code modifications are independently verified against test commands and file boundaries before any Git commit is generated.
- **SC-004**: 0 unauthorized file modifications occur outside pre-declared `allowed_files` or project boundaries, and 0 secrets or `.env` contents leak into model prompts or audit logs.
- **SC-005**: System recovers from abrupt process termination within 5 seconds upon invoking `harness resume`, resuming from the exact pending task without duplicating completed work.
- **SC-006**: Bounded retry loop strictly enforces maximum attempts (default 2), preventing infinite execution loops and escalating failed tasks to `BLOCKED` with diagnostic failure evidence.
- **SC-007**: Every tool call produces a complete, hash-linked audit record in SQLite distinguishing requested from executed arguments.
- **SC-008**: Structured execution reports for Gemini supervisory analysis are generated in under 3 seconds in both JSON and Markdown formats.
- **SC-009**: Operates 100% locally on Windows 11 with 0 paid external API calls required for implementation.
- **SC-010**: All 14 CLI commands execute reliably in Windows PowerShell, returning standard exit codes (0 for success, non-zero for failure).

## Assumptions

- **Target Hardware**: NVIDIA RTX 4060 Laptop GPU (8 GB VRAM), Intel Core i7-13620H, 16 GB DDR5 RAM, Windows 11.
- **Local Inference Environment**: An externally managed llama.cpp server is running at `http://127.0.0.1:8080/v1` serving model alias `frognano` with 2 available inference slots and 65,536 tokens per slot; model weights and server lifecycle are managed externally.
- **Execution Concurrency**: Sequential task execution for initial release; parallel execution through isolated Git worktrees is architecturally supported but disabled initially.
- **Architecture & Runtime**: Local Python 3.11+ application prioritizing the Python standard library and SQLite; no unnecessary microservices, external message queues, or web servers.
- **Supervisory Architecture**: Gemini/Antigravity operates as the supervisory planning intelligence, consuming generated reports from `.harness/reports/` and updating SpecKit specifications rather than directly invoking Python runtime internals.
- **Shell & Tool Environment**: Windows PowerShell (`pwsh`) is the primary shell environment; external build/test tools (`pytest`, `git`) are installed and available on PATH.
