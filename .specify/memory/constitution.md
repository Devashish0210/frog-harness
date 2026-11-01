<!--
# Sync Impact Report
- Version change: 1.0.0 → 2.0.0
- List of modified principles:
  - PRINCIPLE_1: I. Deterministic Orchestration → II. Deterministic Orchestration (re-mapped to programmatic control and dependency enforcement)
  - PRINCIPLE_2: II. Test-First Development (NON-NEGOTIABLE) → VII. Test-Driven and Evidence-Based Development (expanded with independent verification, exit codes, and diff inspection)
  - PRINCIPLE_3: III. Bounded Autonomy & Explicit Safeguards → III. Security by Default & VI. Immutable Task Scope (split into strict Tool Gateway containment and task scope boundaries)
  - PRINCIPLE_4: IV. Security & Defensive Design → III. Security by Default & IV. Independent Authorization and Verification (separated into Policy Engine defense and independent verification)
  - PRINCIPLE_5: V. Recoverability & State Resiliency → IX. Recoverability and State Persistence (explicitly mandates SQLite and Git reconciliation)
  - PRINCIPLE_6: VI. Minimal Dependencies & Stdlib-First → XI. Simplicity and Maintainability (expanded with local Python app and avoidance of unnecessary microservices)
- Added principles & sections:
  - Core Engineering Principle preamble
  - I. Separation of Intelligence and Execution
  - V. Tool Execution Contracts
  - VIII. Auditability and Traceability
  - X. Resource Efficiency
  - XII. Git Integrity
  - XIII. Controlled Evolution
  - SECTION_2: Architectural & Environmental Constraints
  - SECTION_3: Verification Gates & Compliance Workflow
  - Governance: Expanded role boundaries and non-negotiable primacy
- Removed sections:
  - None (previous preliminary standards synthesized into dedicated sections)
- Follow-up TODOs:
  - None (all principles and operational constraints fully defined from consti.txt)
-->

# Frognano Harness Constitution

> **Core Engineering Principle**:
> Gemini plans. SpecKit structures. Python orchestrates. FrogNano implements. The Policy Engine authorizes. The Runtime executes. The Verification Engine verifies. The Audit Ledger remembers.
> No component may silently assume another component's authority.

## Core Principles

### I. Separation of Intelligence and Execution
The system MUST maintain strict separation between planning, implementation, orchestration, authorization, and verification:
- **Gemini/Antigravity** is the planning and supervisory intelligence.
- **GitHub SpecKit** is the source of truth for specifications, plans, and atomic tasks.
- **Python orchestrator** controls execution order, task state, and workflow transitions.
- **FrogNano** is the local implementation agent.
- **Tool Gateway** controls all interactions between the model and the operating environment.
- **Policy Engine** authorizes or denies operations.
- **Verification Engine** independently evaluates implementation results.
- **Audit Ledger** maintains a traceable execution history.
- *Non-negotiable*: No LLM may override deterministic workflow controls or security policies.
- *Rationale*: Blurring execution, authorization, and planning boundaries allows autonomous agents to bypass safeguards, fabricate verification evidence, or self-authorize privileged access.

### II. Deterministic Orchestration
All workflow control MUST be implemented programmatically.
The orchestrator MUST:
- Maintain explicit task states.
- Enforce task dependencies.
- Prevent execution of incomplete dependencies.
- Apply configurable retry limits.
- Persist state across interruptions.
- Support deterministic recovery.
- Prevent duplicate execution of completed tasks.
- Validate all state transitions.
- *Non-negotiable*: LLMs MUST NOT independently determine workflow completion.
- *Rationale*: Programmatic state machines prevent runaway recursion, duplicate executions, and unverified task completion claims.

### III. Security by Default
All model-generated operations MUST pass through the Tool Gateway. Direct, unrestricted shell or filesystem access by the model is prohibited.
The Policy Engine MUST enforce:
- Project-root filesystem boundaries.
- Task-specific read/write permissions.
- Command execution restrictions.
- Global security policies.
- Risk classification.
- Human approval requirements.
- Secret and credential protection.
- *Non-negotiable*: Default permissions MUST follow the principle of least privilege. Denied operations MUST NOT be executed. Human approval MUST be required for operations outside predefined autonomous permissions. Global security policies MUST take precedence over task-level permissions.
- *Rationale*: Restricting access to validated tools and strictly enforcing policy rules prevents local environment compromise and unintended side effects.

### IV. Independent Authorization and Verification
Authorization and verification MUST be separate responsibilities:
- Policy Engine determines whether an operation is permitted.
- Execution Runtime performs authorized operations.
- Verification Engine evaluates their actual effects.
- Audit Ledger records all stages.
- *Non-negotiable*: An LLM cannot authorize its own privileged operations. An LLM cannot declare its own implementation verified. Task completion MUST be based on independently collected evidence.
- *Rationale*: Self-authorization and self-verification create circular trust that invalidates safety and correctness guarantees.

### V. Tool Execution Contracts
Every tool MUST have:
- A unique identifier.
- A strict input schema.
- Explicit permissions.
- Defined execution behavior.
- Structured output.
- Error handling.
- Audit events.
- *Non-negotiable*: Tool implementations MUST NOT bypass authorization. Tool calls MUST be validated before execution. The runtime MUST record actual executed arguments, execution status, and resulting artifacts.
- *Rationale*: Explicit tool contracts ensure typed execution, predictable behavior, and complete accountability across all environment mutations.

### VI. Immutable Task Scope
Every implementation task MUST have:
- A defined objective.
- Explicit requirements.
- Acceptance criteria.
- Relevant context.
- Permitted file boundaries.
- Verification requirements.
- Dependencies.
- *Non-negotiable*: FrogNano MUST NOT silently expand task scope. If implementation requires architectural changes or modifications outside its authorized boundaries, it MUST return a `BLOCKED` result. Only the planning agent may propose changes to specifications or task definitions.
- *Rationale*: Bounded task definitions prevent uncontrolled codebase churn and preserve modular, incremental progress.

### VII. Test-Driven and Evidence-Based Development
Implementation MUST be accompanied by appropriate tests. The system MUST independently execute prescribed verification commands.
- A successful model response is NOT evidence of successful implementation.
- The system MUST capture test output.
- The system MUST capture process exit codes.
- The system MUST validate Git diffs.
- The system MUST detect unauthorized modifications.
- The system MUST preserve failed verification evidence.
- The system MUST prevent unsuccessful tasks from being marked complete.
- *Non-negotiable*: Tests MUST NOT be silently skipped to obtain a successful status.
- *Rationale*: Only deterministic verification via test runners, exit codes, and diff inspection provides authentic proof of functionality.

### VIII. Auditability and Traceability
Every execution MUST be traceable.
The Audit Ledger MUST record:
- Execution run identifiers.
- Task identifiers.
- Model identity.
- Tool requests.
- Authorization decisions.
- Human approvals.
- Actual execution arguments.
- Execution results.
- Verification outcomes.
- Git commit references.
- Timestamps.
- Failure information.
- *Non-negotiable*: Audit events MUST be append-only at the application level. The system MUST support reconstruction of a task's execution history. Sensitive credentials MUST never be written into audit logs.
- *Rationale*: Immutable audit logging provides complete post-mortem diagnostics, compliance verification, and execution replayability.

### IX. Recoverability and State Persistence
Execution state MUST survive:
- Application termination.
- Operating system restarts.
- Inference server failures.
- Interrupted model generation.
- Tool execution failures.
- Test failures.
- *Non-negotiable*: SQLite MUST provide initial persistent state storage. Recovery MUST reconcile persisted execution state against the actual repository and Git history before resuming. The system MUST NOT assume that an interrupted operation had no side effects.
- *Rationale*: Resilient persistence ensures that crashes, restarts, and model timeouts do not corrupt the working tree or duplicate side effects.

### X. Resource Efficiency
The system MUST be designed for the target hardware:
- NVIDIA RTX 4060 Laptop GPU, 8 GB VRAM.
- 16 GB system RAM.
- Windows 11.
- Local llama.cpp inference.
- *Non-negotiable*: The implementation MUST minimize unnecessary services, memory consumption, and context usage. The system MUST use task-specific context assembly rather than repeatedly sending entire project histories. Inference configuration MUST remain external and configurable.
- *Rationale*: Running local models under tight memory and VRAM constraints requires aggressive context pruning and lean runtime footprints.

### XI. Simplicity and Maintainability
- Prefer:
  - Python standard library where practical.
  - SQLite for local persistence.
  - Explicit interfaces between components.
  - Small, independently testable modules.
  - Typed data structures.
  - Strict schemas.
  - Clear error handling.
- Avoid:
  - Unnecessary microservices.
  - Premature distributed architecture.
  - Unnecessary frameworks.
  - Hidden execution behavior.
  - Duplicated sources of truth.
- *Non-negotiable*: The initial release MUST operate as a local Python application.
- *Rationale*: Minimal external dependencies and local execution architecture guarantee low latency, easy deployment, and zero external service coupling.

### XII. Git Integrity
Git MUST provide task-level checkpoints.
- Every successfully verified task SHOULD receive an individual commit.
- Existing user modifications MUST be preserved.
- Destructive Git operations MUST require explicit approval.
- Remote pushes MUST remain disabled by default.
- Failed tasks MUST NOT compromise previously completed work.
- *Rationale*: Granular, clean commits provide rollback capabilities, atomic checkpoints, and ensure that failed task attempts can be cleanly aborted.

### XIII. Controlled Evolution
Future capabilities MUST preserve the existing security boundaries.
The architecture SHOULD support:
- Parallel execution through isolated Git worktrees.
- Additional local models.
- Alternative inference engines.
- Additional tool adapters.
- External audit storage.
- Richer verification strategies.
- *Non-negotiable*: These capabilities MUST NOT compromise deterministic orchestration or least-privilege execution.
- *Rationale*: System evolution must be forward-compatible with multi-model and multi-worktree execution without degrading foundational safety invariants.

## Architectural & Environmental Constraints

### 1. Hardware & Runtime Budget
- **Operating System**: Windows 11.
- **Hardware Targets**: NVIDIA RTX 4060 Laptop GPU (8 GB VRAM), 16 GB system RAM.
- **Inference Runtime**: Local `llama.cpp` instance; model context sizes, prompt formatting, and sampling parameters MUST be configurable externally without code modification.
- **Application Structure**: Local standalone Python 3.11+ application using standard library modules and SQLite. Distributed services, microservices, and multi-node architectures are strictly prohibited for initial releases.

### 2. Tool Gateway & Policy Enforcement
- **Interface Boundary**: All interactions with the filesystem, process execution, and network MUST pass through the Tool Gateway.
- **Schema Contracts**: Every tool input and output MUST validate against explicit, strict JSON schemas.
- **Filesystem Isolation**: File access MUST be confined to the project root. Tasks MUST operate strictly within pre-declared, task-specific file path allowances.
- **Command Whitelisting**: Process and shell executions MUST adhere to strict policy allowlists; raw, unrestricted shell interpretation is prohibited.
- **Least Privilege**: Any action exceeding predefined autonomous scopes MUST halt and demand explicit human approval.

### 3. State Reconciliation & Audit
- **SQLite Persistence**: Execution state, task graph metadata, retry counts, and status flags MUST be persisted transactionally in SQLite.
- **Reconciliation on Recovery**: Following unexpected termination, the orchestrator MUST inspect Git status and filesystem diffs to reconcile SQLite records with disk realities before continuing.

## Verification Gates & Compliance Workflow

### 1. Verification Workflow
Every task execution MUST traverse mandatory deterministic gates:
1. **Scope Gate**: SpecKit specification and task boundaries are checked for completeness, dependencies, and explicit file limits.
2. **Policy Gate**: Policy Engine evaluates every tool request against global and task-specific rules prior to invocation.
3. **Execution Gate**: Runtime executes authorized tools, capturing execution parameters, return payloads, exit codes, and timestamps.
4. **Independent Verification Gate**: Verification Engine executes configured test suites (`pytest`), validates exit codes, and checks Git diffs. Model claims of success are rejected without verifiable external evidence.
5. **Audit Gate**: Audit Ledger commits append-only records of all requests, decisions, executions, and verification evidence.
6. **Git Checkpoint Gate**: Upon passing all verification checks, the system creates an isolated task commit.

### 2. Scope Violations & Blocked State
- When FrogNano or any component encounters an architectural conflict or requires file modifications outside its assigned boundaries, it MUST immediately yield a `BLOCKED` status.
- Scope adjustments or specification amendments MUST originate exclusively from the planning agent (Gemini/Antigravity) via SpecKit.

## Governance

This Constitution represents the supreme architectural and operational standard for the Frognano Harness project. All design specifications, implementation plans, task breakdowns, pull requests, and runtime components MUST strictly adhere to its principles and constraints.

### Amendment Procedure
- Amendments to this Constitution MUST be proposed through a dedicated Pull Request modifying `.specify/memory/constitution.md`.
- Proposed amendments MUST include detailed rationale, an impact assessment across all runtime components, and necessary migration guidance.
- Version numbering adheres strictly to Semantic Versioning:
  - **MAJOR** (e.g., 3.0.0): Breaking alterations, redefinitions, or removals of core principles, security models, or governance rules.
  - **MINOR** (e.g., 2.1.0): Introduction of new principles, new runtime adapters, or material expansion of operational constraints.
  - **PATCH** (e.g., 2.0.1): Clarifications, non-semantic wording enhancements, and typographical corrections.

### Compliance & Review
- No component or LLM may bypass or override this Constitution.
- In any conflict between prompt instructions, model preferences, and this Constitution, this Constitution MUST prevail.
- Verification Engine checks and Audit Ledger logs MUST be reviewed for constitutional compliance during development and CI evaluations.

**Version**: 2.0.0 | **Ratified**: 2026-11-01 | **Last Amended**: 2026-11-01
