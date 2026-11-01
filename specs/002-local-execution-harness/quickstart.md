# Quickstart Validation Guide: Frognano Execution Harness

**Feature Branch**: `002-local-execution-harness`
**Date**: 2026-11-01
**Spec**: [spec.md](./spec.md)
**Contracts**: [contracts/](./contracts/)

This guide provides step-by-step runnable scenarios to validate that the Local Agentic Coding Execution Harness works end-to-end on Windows 11.

---

## 1. Prerequisites & Environment Setup

1. **Operating System**: Windows 11 (PowerShell 7+ / `pwsh`).
2. **Python Environment**: Python 3.11+ installed.
   ```powershell
   python --version
   ```
3. **Local Inference Server**: `llama.cpp` server running on port 8080 with OpenAI API emulation:
   ```powershell
   # Test inference endpoint accessibility
   Invoke-RestMethod -Uri "http://127.0.0.1:8080/v1/models" -Method Get
   ```

---

## 2. Validation Scenario 1: SpecKit Project Discovery & Plan DAG

**Objective**: Verify that the harness discovers SpecKit specifications, parses `tasks.md`, checks dependencies, and generates an execution DAG without model invocation.

```powershell
# Step 1: Initialize harness state in workspace
python -m frognano_harness.cli init --endpoint "http://127.0.0.1:8080/v1" --model "frognano"

# Step 2: Validate tasks.md contract and check for dependency cycles
python -m frognano_harness.cli validate

# Expected Output:
# [OK] SpecKit project discovered at C:\Users\Vaing\Frognano-harness
# [OK] Constitution loaded: Frognano Harness Constitution v2.0.0
# [OK] tasks.md parsed: N tasks detected, 0 cycles, 0 missing contract fields

# Step 3: Render execution plan DAG
python -m frognano_harness.cli plan

# Expected Output:
# Topological execution graph displayed with dependencies and ready tasks
```

---

## 3. Validation Scenario 2: Bounded Task Execution & Independent Verification

**Objective**: Verify that task dispatch routes through the Tool Gateway, respects pre-declared `allowed_files`, runs independent verification, and creates an atomic Git commit.

```powershell
# Run the first ready task
python -m frognano_harness.cli run --task "T-001"

# Expected Output sequence:
# 1. Assembling context envelope (under 65k token limit)...
# 2. Dispatching to FrogNano-4B via http://127.0.0.1:8080/v1...
# 3. Tool call requested: write_file -> Policy Engine: ALLOW (target in allowed_files)
# 4. Tool executed: write_file completed (duration 12ms)
# 5. Model signals completion -> Triggering Independent Verification Engine...
# 6. Verification command: pytest tests/... -> Exit code 0 (PASSED)
# 7. Git diff validated: 0 unauthorized file modifications detected
# 8. Git checkpoint committed: [T-001] Task title (hash: a1b2c3d)
# 9. Audit event appended (hash chain verified)
```

---

## 4. Validation Scenario 3: Policy Enforcement & Human Approval Interception

**Objective**: Verify that high-risk actions (e.g., package installation, file deletion) are intercepted by the Policy Engine and require operator approval.

```powershell
# In an interactive terminal, when a high-risk tool is requested:
# [POLICY REQUIRE_APPROVAL] Task T-002 requested high-risk operation: run_command ["pip", "install", "..."]
# Reason: Package management requires human authorization
# Authorize this operation? [y/N]: y

# In an unattended session or when testing CLI commands:
python -m frognano_harness.cli status
# Shows: Pending Approval: APP-1029 (Task T-002: run_command pip install)

# Approve via CLI:
python -m frognano_harness.cli approve APP-1029

# Or Reject via CLI:
python -m frognano_harness.cli reject APP-1029 --reason "External package prohibited"
```

---

## 5. Validation Scenario 4: Crash Resiliency & Session Recovery

**Objective**: Verify that interrupting execution (e.g., Ctrl+C or crash) preserves completed work and resumes seamlessly.

```powershell
# 1. Start execution run
python -m frognano_harness.cli run

# 2. Terminate the process mid-run (Ctrl+C)

# 3. Run resume command
python -m frognano_harness.cli resume

# Expected Output:
# [OK] SQLite database reconciled with Git commits (3 completed tasks verified)
# [OK] Skipping already completed tasks T-001, T-002, T-003
# [OK] Resuming execution from pending task T-004
```

---

## 6. Validation Scenario 5: Audit Ledger Cryptographic Integrity Check

**Objective**: Verify that the append-only SQLite audit ledger maintains an unbroken SHA-256 hash chain.

```powershell
python -m frognano_harness.cli audit --verify-chain

# Expected Output:
# [OK] Verified N audit ledger records. Hash chain intact. Zero tampering detected.
```

---

## 7. Validation Scenario 6: Supervisory Report for Gemini

**Objective**: Verify that machine-readable reports are exported to `.harness/reports/`.

```powershell
python -m frognano_harness.cli report

# Expected Output:
# [OK] Exported JSON report: .harness/reports/run-20261101-report.json
# [OK] Exported Markdown report: .harness/reports/run-20261101-report.md
```
