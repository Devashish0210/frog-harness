"""Unit tests for AuditLedger."""

import sqlite3
import tempfile
from pathlib import Path
import pytest
from frognano_harness.audit_ledger import AuditLedger
from frognano_harness.state_manager import StateManager


@pytest.fixture
def temp_db() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / ".harness" / "state.db"


def test_audit_ledger_append_and_verify_chain(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    ledger = AuditLedger(sm)

    # 1. Record events
    entry1 = ledger.record_event(
        event_type="RUN_EVENT",
        payload={"action": "start_run", "run_id": "R-1"},
    )
    assert entry1.id == 1
    assert entry1.prev_entry_hash == "0" * 64

    entry2 = ledger.record_event(
        event_type="TOOL_REQUEST",
        payload={"tool": "read_file", "args": {"path": "src/main.py"}},
    )
    assert entry2.id == 2
    assert entry2.prev_entry_hash == entry1.entry_hash

    entry3 = ledger.record_event(
        event_type="GIT_CHECKPOINT",
        payload={"task_id": "T-1", "commit": "a1b2c3d"},
    )
    assert entry3.id == 3
    assert entry3.prev_entry_hash == entry2.entry_hash

    # Verify chain
    is_valid, count, err = ledger.verify_chain()
    assert is_valid is True
    assert count == 3
    assert err is None


def test_audit_ledger_detects_tampering(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    ledger = AuditLedger(sm)

    ledger.record_event("RUN_EVENT", {"action": "start"})
    ledger.record_event("TASK_STATE", {"task": "T-1", "state": "RUNNING"})

    # 1. Physical trigger defense: direct update is aborted by SQLite trigger
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with sm.get_connection() as conn:
            conn.execute("UPDATE audit_events SET payload_json = '{\"tampered\": true}' WHERE id = 1")

    # 2. Cryptographic defense: if trigger is bypassed, hash chain detects tampering
    with sm.get_connection() as conn:
        conn.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_update")
        conn.execute("UPDATE audit_events SET payload_json = '{\"tampered\": true}' WHERE id = 1")

    is_valid, count, err = ledger.verify_chain()
    assert is_valid is False
    assert "mismatch" in (err or "").lower()


def test_audit_ledger_scrubs_secrets(temp_db: Path) -> None:
    sm = StateManager(temp_db)
    ledger = AuditLedger(sm)

    entry = ledger.record_event(
        event_type="TOOL_REQUEST",
        payload={
            "tool": "run_command",
            "api_key": "secret_abc12345",
            "password": "supersecretpassword",
            "args": ["--token", "mytoken123"],
        },
    )

    assert "secret_abc12345" not in entry.payload_json
    assert "supersecretpassword" not in entry.payload_json
    assert "[REDACTED]" in entry.payload_json
