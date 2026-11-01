# Feature Specification: Local Agentic Coding Execution Harness

**Feature Branch**: `001-local-execution-harness`

**Created**: 2026-11-01

**Status**: Draft

**Input**: User description: "Build a deterministic, task-driven software engineering execution system that connects GitHub SpecKit with a locally hosted coding model (FrogNano-4B) through an OpenAI-compatible llama.cpp server."

## Clarifications

### Session 2026-11-01
- Q: What interaction protocol should the harness use to receive file inspections, edits, and terminal commands from the local FrogNano-4B model via llama.cpp? (FR-004) → A: Hybrid protocol (Option C: prioritize native OpenAI tool calling schemas (`tools` / `tool_calls`), falling back to parsing structured markdown action code fences if tool calls are omitted or malformed).
- Q: Where should the SQLite persistence database and runtime artifacts (execution logs, checkpoints, supervisory reports) be stored within the workspace? (FR-013) → A: Dedicated `.harness/` directory in the project root (`.harness/state.db`, `.harness/logs/`, `.harness/reports/`), automatically excluded from Git tracking via `.gitignore`.
- Q: How should the harness enforce file modification boundaries when an implementation task requires creating a new file? (FR-005) → A: Explicit pre-declaration only (Option A: bounded autonomy; the planner pre-declares all affected and created files in `allowed_files` in `tasks.md`, and the coder model cannot create or touch undeclared files).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - SpecKit Task Discovery, DAG Resolution, and Plan Preview (Priority: P1)

As a software engineer using SpecKit for architecture and planning, I want the execution harness to automatically discover, parse, and validate `tasks.md` and construct an execution dependency graph, so that tasks are ordered deterministically and execution prerequisites are verified before any model invocation.

**Why this priority**: Foundational prerequisite for all harness operations. The system cannot safely or deterministically dispatch tasks without parsing the contract, detecting circular dependencies, and computing the topological execution order.

**Independent Test**: Can be validated by running `harness validate` and `harness plan` against standard SpecKit `tasks.md` files containing linear, branching, and cyclic task dependencies without requiring an active inference server.

**Acceptance Scenarios**:

1. **Given** a SpecKit project containing a valid `tasks.md` file, **When** the user runs the `validate` or `plan` command, **Then** the harness parses all task definitions, extracts dependencies, builds an execution DAG, and renders the ordered execution plan in the terminal.
2. **Given** a `tasks.md` file with a circular dependency (e.g., Task A depends on Task B, and Task B depends on Task A), **When** the user runs `validate`, **Then** the harness detects the cycle, halts execution planning, and displays an unambiguous error highlighting the offending tasks.
3. **Given** a `tasks.md` file missing required task fields (such as acceptance criteria or verification commands), **When** the user runs `validate`, **Then** the harness flags the missing contract elements and reports actionable remediation steps.

---

### User Story 2 - Task Dispatch and Controlled Execution via Local Inference (Priority: P1)

As a developer running local models on Windows 11, I want the harness to construct a task execution envelope with minimal necessary context and dispatch it to FrogNano-4B via a local llama.cpp OpenAI-compatible endpoint, so that the model can inspect code and perform file edits within strictly bounded workspaces.

**Why this priority**: Core execution capability. Connects the high-level task specification to the local model and provides controlled file inspection and code generation while safeguarding the host project.

**Independent Test**: Can be tested by dispatching a single atomic task to a running local llama.cpp endpoint (`http://127.0.0.1:8080/v1`) with mock source files, verifying that prompt envelopes contain relevant specifications, file modifications are restricted to `allowed_files`, and model tool actions are captured into structured traces.

**Acceptance Scenarios**:

1. **Given** an eligible task and an available local llama.cpp server at `http://127.0.0.1:8080/v1`, **When** the harness dispatches the task, **Then** it sends a structured task envelope containing the task objective, relevant specification sections, and allowed file boundaries within a configurable context limit (default 65,536 tokens).
2. **Given** an active model implementation session, **When** the model requests to read or modify files within `allowed_files` (via native tool calls or structured markdown blocks), **Then** the harness safely executes the file operations and captures the changes in the execution log.
3. **Given** an active model implementation session, **When** the model attempts to write outside the project root, create or modify files outside pre-declared `allowed_files`, or access protected secret files (such as `.env`), **Then** the harness immediately blocks the operation under bounded autonomy, records a security violation, and prevents file mutation.

---

### User Story 3 - Independent Verification and Bounded Retry/Escalation (Priority: P1)

As a project supervisor, I want the harness to independently verify all code changes using prescribed test commands and criteria rather than trusting the model's assertions, and to automatically initiate bounded corrections on failure, so that broken or hallucinated implementations never pollute the codebase.

**Why this priority**: Crucial for deterministic quality. FrogNano-4B cannot mark tasks as completed; only independent test exit codes and file diff verification decide completion.

**Independent Test**: Can be tested with passing and failing test scripts. Validates that passing tests trigger completion, while failing tests trigger up to 2 correction attempts before escalating the task to `BLOCKED`.

**Acceptance Scenarios**:

1. **Given** a task implementation completed by FrogNano, **When** the harness enters verification, **Then** it independently executes prescribed verification commands in a subprocess, capturing exit codes, standard output, and standard error.
2. **Given** an implementation that passes all verification commands and respects file boundaries, **When** verification concludes, **Then** the harness marks the task as `SUCCESS` and advances to commit.
3. **Given** an implementation where a verification command fails (non-zero exit code or mismatched output), **When** the attempt count is less than the retry limit (default 2), **Then** the harness packages the failure logs into a correction prompt and dispatches a follow-up retry to FrogNano.
4. **Given** an implementation that continues to fail after exhausting all retry attempts (2 retries), **When** verification fails on the final attempt, **Then** the harness marks the task as `BLOCKED`, stops execution of dependent tasks, and generates an escalation report for Gemini.

---

### User Story 4 - Atomic Git Checkpointing and State Persistence/Recovery (Priority: P2)

As a developer, I want each verified task to be committed individually to Git and execution state persisted in SQLite, so that progress is durable and runs can be interrupted and resumed without repeating completed work.

**Why this priority**: Ensures recoverability, auditability, and crash tolerance across terminal closures, reboots, and network timeouts.

**Independent Test**: Can be tested by starting a multi-task execution run, terminating the process abruptly mid-run, and executing `harness resume`. Validates that already-committed tasks remain intact and execution seamlessly resumes from the first uncompleted task.

**Acceptance Scenarios**:

1. **Given** a successfully verified task, **When** the harness finalizes the task, **Then** it commits the changes to Git with a message containing the task ID and title, updates SQLite with the commit hash, and transitions task state to `COMPLETED`.
2. **Given** an interrupted execution run (due to process termination or server reboot), **When** the user runs `harness resume`, **Then** the harness inspects the SQLite database, validates the working tree against Git commits, skips all `COMPLETED` tasks, and resumes execution from the next pending task in the DAG.
3. **Given** a failed or aborted task attempt with uncommitted modifications, **When** the task is reset or rolled back, **Then** the harness detects uncommitted artifacts, restores the working tree to the pre-task checkpoint, and preserves unrelated user files.

---

### User Story 5 - Execution Observability, Reporting, and Supervisory Feedback for Gemini (Priority: P2)

As an architect supervising automated development via Gemini and SpecKit, I want the harness to provide real-time CLI status and export structured, machine-readable execution reports, so that I can monitor progress, diagnose blockers, and update specifications without manual copying.

**Why this priority**: Closes the loop between the execution harness and the supervisory agent (Antigravity/Gemini) with zero manual friction.

**Independent Test**: Can be tested by executing tasks and running `harness status` and `harness report`, verifying that console output displays clear progress indicators and generated reports contain machine-readable JSON/Markdown summaries of completed tasks, commits, test traces, and blockers.

**Acceptance Scenarios**:

1. **Given** an ongoing execution run, **When** the user views the terminal CLI, **Then** the harness displays real-time execution telemetry: current task ID, attempt count, model connection status, elapsed time, and task queue status.
2. **Given** a completed or halted execution run, **When** the user runs `harness report`, **Then** the harness generates a structured report containing overall progress percentage, lists of completed/failed/blocked tasks, Git commit references, test outputs, and suggested next actions for Gemini.

---

### User Story 6 - Manual Override, Task Rerun, and Independent Re-Verification (Priority: P3)

As a developer troubleshooting an environmental blocker or updating a dependency, I want to manually retry specific tasks or re-verify existing code without re-invoking the LLM, so that I maintain fine-grained control over the harness.

**Why this priority**: Provides operational flexibility for developers to fix external prerequisites (e.g., missing local tool or environment variable) and unblock tasks manually.

**Independent Test**: Can be tested by running `harness retry <task_id>` and `harness verify <task_id>` on specific tasks, confirming that states transition appropriately and verification runs standalone.

**Acceptance Scenarios**:

1. **Given** a task in `BLOCKED` status where an external configuration was manually corrected, **When** the user executes `harness retry <task_id>`, **Then** the harness resets the task's attempt counter and re-queues it for execution.
2. **Given** an already implemented task, **When** the user executes `harness verify <task_id>`, **Then** the harness re-executes all verification commands against the current workspace and reports the results without dispatching prompts to the LLM.

---

### Edge Cases

- **Inference Server Disconnection**: If the llama.cpp server at `http://127.0.0.1:8080/v1` becomes unreachable or drops connection during model generation, the harness MUST capture the connection error, apply bounded exponential backoff retries, and escalate to `BLOCKED` if the server does not recover within a configurable timeout.
- **Malformed Model Output**: If FrogNano produces invalid tool call syntax, unclosed JSON blocks, or truncated responses, the harness MUST detect the structural error, attempt fallback parsing via structured markdown code fences, and if unparseable, record an invalid output attempt and provide targeted formatting guidance in the retry prompt.
- **Dirty Pre-Execution Working Tree**: If the Git repository contains uncommitted changes before task execution starts, the harness MUST warn the user and refuse to execute until the user explicitly commits or stashes existing changes, preventing accidental data loss.
- **Non-Terminating Verification Tests**: If a verification command hangs (e.g., infinite loop, waiting on stdin), the harness MUST enforce a mandatory per-command execution timeout (default 120 seconds), terminate the hung subprocess, and record a timeout failure.
- **Path Traversal Attacks**: If the model attempts to read or write paths containing relative traversal (`../` or `..\`) resolving outside the workspace root, the harness MUST abort the operation immediately and log a security violation.
- **Context Window Saturation**: If accumulated task instructions and source files approach the 65,536 token context ceiling, the harness MUST apply deterministic truncation to observation history while strictly preserving task objectives, acceptance criteria, and system constraints.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST automatically discover and parse standard GitHub SpecKit `tasks.md` files, extracting task metadata, objectives, dependencies, file boundaries, acceptance criteria, and verification commands.
- **FR-002**: System MUST construct a Directed Acyclic Graph (DAG) representing task dependencies, detect circular dependencies, and compute topological execution sequence.
- **FR-003**: System MUST assemble a structured task execution envelope for each atomic task containing only relevant specification extracts, allowed file contents, and essential task history without overflowing the configurable context limit (default 65,536 tokens).
- **FR-004**: System MUST communicate with local llama.cpp via its OpenAI-compatible endpoint (`http://127.0.0.1:8080/v1`) using model alias `frognano`, supporting a hybrid interaction protocol that prioritizes native OpenAI tool calling schemas (`tools` / `tool_calls`) and deterministically falls back to parsing structured markdown action code fences if tool calls are missing or malformed.
- **FR-005**: System MUST strictly restrict model file operations (read/write/create) to the project repository root and explicitly enforce task `allowed_files` boundaries; any file to be created or modified MUST be pre-declared by the planner in `allowed_files`, and attempts to create or touch undeclared files MUST be blocked immediately.
- **FR-006**: System MUST enforce protection for sensitive configuration files (`.env`, credentials, private keys), rejecting any attempt to read, write, or expose secrets to the model prompt.
- **FR-007**: System MUST provide a configurable command allowlist for model-initiated commands, strictly preventing unrestricted administrative or dangerous commands (`rmdir /s`, `format`, network egress).
- **FR-008**: System MUST execute verification commands in an isolated subprocess, capturing standard output, standard error, execution duration, and process exit codes.
- **FR-009**: System MUST enforce that a task is marked `SUCCESS` only when all prescribed verification commands exit with code 0 and file modifications strictly match acceptance criteria.
- **FR-010**: System MUST automatically initiate bounded correction retries (default 2 retries per task) upon verification failure, feeding test failure output back to the model.
- **FR-011**: System MUST escalate a task to `BLOCKED` when retries are exhausted or when the model explicitly reports a blockage, halting dependent downstream tasks while allowing independent branches to proceed.
- **FR-012**: System MUST create an individual Git commit for each successfully verified task, formatting the commit message with the task ID and title, and NEVER push automatically to remote repositories.
- **FR-013**: System MUST persist all execution metadata (runs, task states, attempts, logs, verification outcomes, commit hashes) in a local SQLite database located in a dedicated `.harness/` directory at the project root (`.harness/state.db`), keeping execution logs (`.harness/logs/`) and runtime state isolated from Git tracking.
- **FR-014**: System MUST reconcile persisted SQLite state with the Git working tree upon restart, enabling seamless resumption via `resume` without re-executing completed tasks.
- **FR-015**: System MUST generate structured machine-readable reports (JSON and Markdown) summarizing run progress, task outcomes, commit hashes, test results, and recommendations for Antigravity/Gemini, outputting to `.harness/reports/` by default and printing human-readable summaries to stdout.
- **FR-016**: System MUST provide a comprehensive CLI for Windows PowerShell supporting `init`, `validate`, `plan`, `run`, `resume`, `status`, `task`, `retry`, `report`, `logs`, and `verify`.

### Key Entities *(include if feature involves data)*

- **Task**: The declarative unit of work parsed from SpecKit `tasks.md`. Attributes: `task_id`, `title`, `description`, `objective`, `dependencies`, `allowed_files`, `acceptance_criteria`, `verification_commands`, `status` (`PENDING`, `READY`, `RUNNING`, `SUCCESS`, `FAILED`, `BLOCKED`).
- **Execution Run**: A single invocation session of the execution harness. Attributes: `run_id`, `project_root`, `start_time`, `end_time`, `status`, `model_endpoint`, `total_tasks`, `completed_tasks`, `failed_tasks`.
- **Task Attempt**: An individual execution cycle for a task. Attributes: `attempt_id`, `run_id`, `task_id`, `attempt_number`, `prompt_tokens`, `completion_tokens`, `model_response`, `diff`, `created_at`.
- **Verification Record**: The recorded outcome of verification commands for an attempt. Attributes: `verification_id`, `attempt_id`, `command`, `exit_code`, `stdout`, `stderr`, `passed`, `timestamp`.
- **State Checkpoint**: The durable tracking record in SQLite mapping tasks to their Git commit hashes, completion timestamps, and operational status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tasks defined in standard SpecKit `tasks.md` are discovered, parsed, and converted into an execution DAG without requiring manual reformatting or duplication.
- **SC-002**: 100% of code modifications are independently verified against automated test commands and file boundaries before any Git commit is created.
- **SC-003**: 0 unauthorized file modifications occur outside `allowed_files` or project boundaries, and 0 secrets or `.env` contents are leaked into model prompts.
- **SC-004**: System recovers from abrupt process interruption within 5 seconds upon invoking `resume`, resuming from the exact pending task without re-running completed tasks.
- **SC-005**: Bounded retry loop strictly enforces maximum attempts (default 2), preventing infinite execution loops and escalating to `BLOCKED` with full diagnostic logs.
- **SC-006**: Structured execution reports for Gemini supervisory analysis are generated in under 3 seconds with complete machine-readable task summaries and commit traceability.
- **SC-007**: Operates 100% locally on Windows 11 with 0 paid external API calls required for execution.

## Assumptions

- **Local Inference Environment**: A llama.cpp server is hosted locally at `http://127.0.0.1:8080/v1` serving model alias `frognano` with OpenAI API compatibility; server lifecycle, weights, and CUDA/GPU allocation are managed outside of this application.
- **Execution Mode**: Tasks execute sequentially in single-threaded mode for the initial release; concurrent execution via parallel Git worktrees is deferred to future milestones.
- **Operating System & Shell**: Primary operational target is Windows 11 with PowerShell (pwsh) as the command environment.
- **Supervisory Architecture**: Gemini/Antigravity operates as an asynchronous supervisory and architectural agent, consuming generated reports and generating SpecKit plans rather than directly controlling the Python runtime process.
- **Minimal Dependencies**: The Python runtime relies on Python 3.11+ standard library capabilities (`sqlite3`, `subprocess`, `pathlib`, `json`, `argparse`, `dataclasses`, `urllib.request` or minimal HTTP client) in accordance with the project constitution.
