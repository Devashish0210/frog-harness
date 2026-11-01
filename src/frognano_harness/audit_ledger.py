"""Immutable, hash-chained audit ledger with secret scrubbing."""

from datetime import datetime, timezone
import json
from typing import Any, Optional
import uuid

from frognano_harness.models import AuditEntry
from frognano_harness.state_manager import StateManager


SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "credential",
    "private_key",
)


def scrub_secrets(val: Any) -> Any:
    """Recursively scrub credentials and secrets from dictionaries and argument lists."""
    if isinstance(val, dict):
        scrubbed = {}
        for k, v in val.items():
            k_lower = str(k).lower()
            if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                scrubbed[k] = "[REDACTED]"
            else:
                scrubbed[k] = scrub_secrets(v)
        return scrubbed
    elif isinstance(val, (list, tuple)):
        scrubbed_list = []
        skip_next = False
        for item in val:
            if skip_next:
                scrubbed_list.append("[REDACTED]")
                skip_next = False
                continue
            if isinstance(item, str):
                item_lower = item.lower()
                if any(
                    item_lower.startswith(f"--{s}") or item_lower.startswith(f"-{s}")
                    for s in SENSITIVE_KEY_SUBSTRINGS
                ):
                    if "=" in item:
                        prefix = item.split("=", 1)[0]
                        scrubbed_list.append(f"{prefix}=[REDACTED]")
                    else:
                        scrubbed_list.append(item)
                        skip_next = True
                    continue
            scrubbed_list.append(scrub_secrets(item))
        return scrubbed_list
    return val


class AuditLedger:
    """Manages an append-only, SHA-256 hash-chained audit ledger in SQLite."""

    def __init__(self, state_manager: StateManager) -> None:
        self.state_manager = state_manager

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        created_at: Optional[str] = None,
    ) -> AuditEntry:
        """
        Record a new immutable audit entry, linking it to the previous entry hash.
        Scrubs sensitive fields before serializing.
        """
        scrubbed_payload = scrub_secrets(payload)
        payload_json = json.dumps(scrubbed_payload, sort_keys=True, separators=(",", ":"))
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        entry_id = f"aud_{uuid.uuid4().hex[:12]}"

        with self.state_manager.get_connection() as conn:
            # Fetch latest entry hash
            cursor = conn.cursor()
            cursor.execute("SELECT entry_hash FROM audit_events ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            prev_hash = row["entry_hash"] if row else "0" * 64

            entry_hash = AuditEntry.compute_hash(prev_hash, event_type, payload_json, timestamp)

            cursor.execute(
                """
                INSERT INTO audit_events (
                    entry_id, prev_entry_hash, entry_hash, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entry_id, prev_hash, entry_hash, event_type, payload_json, timestamp),
            )
            row_id = cursor.lastrowid

            return AuditEntry(
                id=row_id,
                entry_id=entry_id,
                prev_entry_hash=prev_hash,
                entry_hash=entry_hash,
                event_type=event_type,
                payload_json=payload_json,
                created_at=timestamp,
            )

    def verify_chain(self) -> tuple[bool, int, Optional[str]]:
        """
        Verify the cryptographic hash chain of all audit entries.
        Returns:
            (is_valid, count_verified, error_message_if_invalid)
        """
        with self.state_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, entry_id, prev_entry_hash, entry_hash, event_type, payload_json, created_at
                FROM audit_events
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()

            if not rows:
                return True, 0, None

            expected_prev_hash = "0" * 64
            for i, row in enumerate(rows):
                entry_id = row["entry_id"]
                db_id = row["id"]
                prev_hash = row["prev_entry_hash"]
                stored_hash = row["entry_hash"]
                event_type = row["event_type"]
                payload_json = row["payload_json"]
                created_at = row["created_at"]

                # 1. Verify link to previous entry
                if prev_hash != expected_prev_hash:
                    return (
                        False,
                        i,
                        f"Previous hash link mismatch at id {db_id} ({entry_id}): "
                        f"expected {expected_prev_hash}, got {prev_hash}",
                    )

                # 2. Verify recalculation of entry hash
                computed_hash = AuditEntry.compute_hash(
                    prev_hash, event_type, payload_json, created_at
                )
                if computed_hash != stored_hash:
                    return (
                        False,
                        i,
                        f"Hash integrity mismatch at id {db_id} ({entry_id}): "
                        f"computed {computed_hash}, stored {stored_hash}",
                    )

                expected_prev_hash = stored_hash

            return True, len(rows), None

    def get_events(
        self,
        limit: Optional[int] = None,
        event_type: Optional[str] = None,
    ) -> list[AuditEntry]:
        """Fetch audit events in chronological order."""
        query = "SELECT id, entry_id, prev_entry_hash, entry_hash, event_type, payload_json, created_at FROM audit_events"
        params: list[Any] = []
        if event_type:
            query += " WHERE event_type = ?"
            params.append(event_type)
        query += " ORDER BY id ASC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self.state_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                AuditEntry(
                    id=row["id"],
                    entry_id=row["entry_id"],
                    prev_entry_hash=row["prev_entry_hash"],
                    entry_hash=row["entry_hash"],
                    event_type=row["event_type"],
                    payload_json=row["payload_json"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]
