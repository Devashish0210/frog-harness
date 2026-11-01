<!--
# Sync Impact Report
- Version change: Unratified (template) → 1.0.0
- List of modified principles:
  - PRINCIPLE_1: [PRINCIPLE_1_NAME] → I. Deterministic Orchestration
  - PRINCIPLE_2: [PRINCIPLE_2_NAME] → II. Test-First Development (NON-NEGOTIABLE)
  - PRINCIPLE_3: [PRINCIPLE_3_NAME] → III. Bounded Autonomy & Explicit Safeguards
  - PRINCIPLE_4: [PRINCIPLE_4_NAME] → IV. Security & Defensive Design
  - PRINCIPLE_5: [PRINCIPLE_5_NAME] → V. Recoverability & State Resiliency
  - Added PRINCIPLE_6: VI. Minimal Dependencies & Stdlib-First
- Added sections:
  - Core Principles (6 declarative, testable principles)
  - Python Quality & Engineering Standards (SECTION_2)
  - Development Workflow & Verification Gates (SECTION_3)
  - Governance
- Removed sections:
  - None (scaffolded placeholder sections replaced with concrete definitions)
- Follow-up TODOs:
  - None (all core placeholders populated and ratified)
-->

# Frognano Harness Constitution

## Core Principles

### I. Deterministic Orchestration
All workflows, task pipelines, and orchestration loops MUST be modeled as explicit, deterministic state machines or directed execution graphs. Given identical initial state, inputs, and environment configurations, execution order and step transitions MUST produce identical, verifiable outcomes.
- Orchestration components MUST NOT rely on ambient, global, or implicit mutable state.
- State transitions MUST be serialized, monotonic, and recorded in a traceable execution journal.
- Concurrency and asynchronous operations MUST define explicit timeouts, bounded worker pools, and deterministic joining/ordering strategies.
- *Rationale*: Non-deterministic orchestration breeds flaky execution, untraceable race conditions, and debugging nightmares in automated harness environments.

### II. Test-First Development (NON-NEGOTIABLE)
Test-Driven Development (TDD) is strictly mandatory across all modules, drivers, harness controllers, and utility components.
- Implementation code MUST NOT be written until unit or contract tests specifying the expected behavior have been authored, peer-reviewed, and confirmed failing (Red).
- The Red-Green-Refactor cycle MUST be strictly enforced: Red (failing test) → Green (minimal code to pass) → Refactor (clean up while tests stay green).
- Tests MUST validate nominal behavior, boundary conditions, invalid inputs, and simulated fault injection (e.g., timeout, partial write, subprocess failure).
- Automated test suites (`pytest`) MUST maintain 100% passing status on all active branches.
- *Rationale*: Writing tests first forces crisp boundary specification, prevents over-engineering, and provides ironclad regression protection.

### III. Bounded Autonomy & Explicit Safeguards
Autonomous operations, agentic steps, and harness-driven actions MUST operate within strictly bounded, pre-declared limits of authority and resource consumption.
- Every autonomous or automated execution loop MUST declare hard operational ceilings: maximum iteration count, step timeout, memory limits, and retry thresholds.
- Potentially destructive or high-impact operations (including file deletion, process termination, external network communication, and credential access) MUST be gated behind explicit authorization checks or simulation/dry-run verification.
- Autonomous routines MUST NOT self-escalate privileges, dynamically broaden their operational scope, or mutate governance configs.
- Execution MUST immediately halt and surface an actionable alert when any safeguard boundary is breached.
- *Rationale*: Unbounded autonomy risks resource exhaustion, cascading failures, data loss, and uncontrolled side effects.

### IV. Security & Defensive Design
Security is an intrinsic architectural constraint, not an afterthought. The system MUST adhere to the principle of least privilege and zero-trust boundary verification.
- Hardcoded secrets, credentials, API keys, or tokens MUST NEVER be committed to source code or embedded in configuration files; all sensitive material MUST be injected via secure environment variables or vault abstractions.
- All inputs crossing process, network, CLI, or module boundaries MUST be rigorously validated and sanitized against strict schemas before consumption.
- Subprocess invocations MUST use structured argument lists (e.g., `subprocess.run(["cmd", "arg"])`) and MUST NEVER use shell evaluation (`shell=True`) with untrusted or variable input.
- File system operations MUST enforce path sanitization to guard against path traversal vulnerabilities.
- *Rationale*: Harnesses and execution drivers possess significant local system access; defensive programming guarantees safety against malicious payloads and accidental compromise.

### V. Recoverability & State Resiliency
Systems and orchestration workflows MUST be designed for crash tolerance, graceful degradation, and lossless recoverability.
- Long-running orchestrations MUST implement atomic checkpointing of execution state, enabling clean resumption from the latest valid checkpoint without restarting from scratch.
- State mutations MUST be idempotent; re-executing a previously interrupted step MUST NOT corrupt system state or create duplicate artifacts.
- Errors MUST be categorized into recoverable (transient) and fatal (terminal) failures, with explicit, bounded retry policies (exponential backoff with jitter) applied only to recoverable conditions.
- System crashes or abnormal shutdowns MUST leave a diagnostic post-mortem log detailing the failure site, stack trace, and serialized state at time of death.
- *Rationale*: Real-world harness environments suffer disconnections, process kills, and infrastructure disruptions; recoverability ensures operational continuity without manual intervention.

### VI. Minimal Dependencies & Stdlib-First
The codebase MUST maintain a lean, deliberate dependency footprint, prioritizing Python's standard library for all standard system, file, text, and operational capabilities.
- Standard library modules (`pathlib`, `json`, `dataclasses`, `logging`, `typing`, `subprocess`, `asyncio`, `argparse`, `hashlib`) MUST be preferred over third-party alternatives unless standard library solutions are demonstrably inadequate.
- Every external dependency added to the project MUST be explicitly justified in terms of necessity, maintenance health, security track record, and license compatibility.
- Transitive dependency bloat and heavy omnibus frameworks MUST be avoided.
- Dependencies MUST be pinned with exact versions and cryptographic hashes in standard dependency lockfiles.
- *Rationale*: Every external dependency increases vulnerability attack surface, introduces supply-chain risk, inflates installation overhead, and risks future version incompatibilities.

## Python Quality & Engineering Standards

### 1. Language & Typing
- Code MUST target modern Python (3.11+) and leverage modern language features (such as pattern matching, `ExceptionGroup`, and `typing.Self`).
- Strict static type hinting is required for all function signatures, return values, and module interfaces; code MUST pass `mypy` or `pyright` in strict mode without errors or unchecked `Any` escapes.
- Domain models and configuration objects MUST use immutable dataclasses (`@dataclass(frozen=True)`) or strongly typed schemas to guarantee data integrity.

### 2. Code Organization & Architecture
- Code MUST follow SOLID principles, separation of concerns, and clean architectural boundaries (decoupling interface/CLI, domain logic, orchestration engine, and external adapters).
- Functions MUST be small, single-purpose, and free of unexpected side effects.
- Formatting and style MUST be enforced via automated tooling (`ruff` for formatting and linting), adhering to PEP 8 standards with zero tolerance for lint warnings in CI.

### 3. Observability & Logging
- Logging MUST utilize structured formatting with consistent context keys (timestamp, level, component, run_id, task_id).
- Application logging MUST write to `stderr` or structured log files; standard output (`stdout`) is reserved for machine-readable output (e.g., JSON) in CLI interfaces.
- Secrets, tokens, and sensitive personal information MUST NEVER appear in log entries.

## Development Workflow & Verification Gates

### 1. Verification Gates
Every change proposed to the codebase MUST satisfy all quality gates before merge or deployment:
1. **Contract/Unit Test Suite**: 100% of unit and contract tests MUST pass (`pytest`).
2. **Static Type Verification**: Strict type checking MUST pass with zero errors (`mypy --strict`).
3. **Style & Linting**: Zero errors reported by `ruff check` and `ruff format --check`.
4. **Boundary & Security Checks**: No detected secrets, unvetted external dependencies, or insecure subprocess calls.
5. **State Transition & Idempotency Tests**: Workflows and orchestration steps MUST pass replay and recovery verification tests.

### 2. Code Review & Compliance
- Pull requests and code contributions MUST explicitly cite the principle(s) supported by the change.
- Any architectural deviation or introduction of an external dependency requires explicit constitutional review and justification in the pull request description.

## Governance

This Constitution represents the supreme architectural and operational standard for the Frognano Harness project. All design specifications, implementation plans, task breakdowns, pull requests, and code modifications MUST comply with its principles.

### Amendment Procedure
- Amendments to this Constitution may be proposed through a dedicated Pull Request updating `.specify/memory/constitution.md`.
- Amendments require explicit documentation of rationale, potential impact analysis, and updates to dependent guidelines or templates.
- Version numbering follows strict Semantic Versioning:
  - **MAJOR** (e.g., 2.0.0): Removal, breaking redefinition, or fundamental restructuring of core principles or governance policies.
  - **MINOR** (e.g., 1.1.0): Addition of new principles, material expansion of quality standards, or new verification gates.
  - **PATCH** (e.g., 1.0.1): Clarifications, phrasing improvements, typographical fixes, and non-semantic refinements.

### Compliance & Review
- Automated CI workflows and manual review checklists MUST verify compliance with this Constitution on every feature branch.
- In any conflict between ad-hoc conventions and this Constitution, the provisions of this Constitution prevail.

**Version**: 1.0.0 | **Ratified**: 2026-11-01 | **Last Amended**: 2026-11-01
