"""
Database layer for the Cloud Command Broker.
Provides SQLite-based persistence for commands, audit history, and agent statuses.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from cloud.models import CommandRecord, CommandStatus


class Database:
    """Manages SQLite persistence for commands, state, and audit records."""

    def __init__(self, db_path: str = "./command_broker.db") -> None:
        # Strip sqlite:/// prefix if present
        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")
        self.db_path = db_path
        self._mem_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns a connection with Row factory enabled."""
        if self._mem_conn is not None:
            return self._mem_conn
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Creates tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS commands (
                    execution_id TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    dispatched_at REAL,
                    completed_at REAL,
                    result_message TEXT,
                    result_data TEXT,
                    error_category TEXT,
                    agent_id TEXT NOT NULL,
                    idempotency_key TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cmd_status ON commands(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cmd_agent ON commands(agent_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cmd_idempotency ON commands(idempotency_key)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_status (
                    agent_id TEXT PRIMARY KEY,
                    last_heartbeat REAL NOT NULL,
                    connected_via TEXT NOT NULL,
                    metrics TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    details TEXT
                )
            """)
            conn.commit()

    def save_command(self, cmd: CommandRecord) -> None:
        """Inserts or replaces a command record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO commands (
                    execution_id, command_id, parameters, status, created_at, expires_at,
                    dispatched_at, completed_at, result_message, result_data, error_category,
                    agent_id, idempotency_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cmd.execution_id,
                cmd.command_id,
                json.dumps(cmd.parameters),
                cmd.status.value,
                cmd.created_at,
                cmd.expires_at,
                cmd.dispatched_at,
                cmd.completed_at,
                cmd.result_message,
                json.dumps(cmd.result_data) if cmd.result_data else None,
                cmd.error_category,
                cmd.agent_id,
                cmd.idempotency_key,
            ))
            cursor.execute("""
                INSERT INTO audit_logs (execution_id, command_id, agent_id, action, timestamp, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cmd.execution_id,
                cmd.command_id,
                cmd.agent_id,
                f"SAVE_{cmd.status.value.upper()}",
                time.time(),
                f"Status: {cmd.status.value}"
            ))
            conn.commit()

    def get_command(self, execution_id: str) -> Optional[CommandRecord]:
        """Retrieves a command record by execution_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM commands WHERE execution_id = ?", (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[CommandRecord]:
        """Retrieves an existing command by idempotency key."""
        if not idempotency_key:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM commands WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
                (idempotency_key,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)

    def get_pending_commands(self, agent_id: str, limit: int = 10) -> List[CommandRecord]:
        """Fetches pending/queued unexpired commands for an agent."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM commands
                WHERE agent_id = ?
                  AND status IN (?, ?)
                  AND expires_at > ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (agent_id, CommandStatus.QUEUED.value, CommandStatus.RECEIVED.value, now, limit))
            rows = cursor.fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_recent_commands(self, limit: int = 50) -> List[CommandRecord]:
        """Fetches recently created commands for history and dashboard."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM commands ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = cursor.fetchall()
            return [self._row_to_record(r) for r in rows]

    def update_command_result(
        self,
        execution_id: str,
        status: CommandStatus,
        result_message: str,
        result_data: Optional[Dict[str, Any]] = None,
        error_category: Optional[str] = None
    ) -> bool:
        """Updates execution result and sets completed_at timestamp."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands
                SET status = ?,
                    completed_at = ?,
                    result_message = ?,
                    result_data = ?,
                    error_category = ?
                WHERE execution_id = ?
            """, (
                status.value,
                time.time(),
                result_message,
                json.dumps(result_data) if result_data else None,
                error_category,
                execution_id,
            ))
            conn.commit()
            return cursor.rowcount > 0

    def mark_expired_commands(self) -> int:
        """Marks any pending commands past their expiration timestamp as EXPIRED."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands
                SET status = ?,
                    completed_at = ?,
                    result_message = 'Command expired in queue prior to execution'
                WHERE status IN (?, ?) AND expires_at <= ?
            """, (
                CommandStatus.EXPIRED.value,
                now,
                CommandStatus.QUEUED.value,
                CommandStatus.RECEIVED.value,
                now,
            ))
            conn.commit()
            return cursor.rowcount

    def count_pending(self) -> int:
        """Counts pending unexpired commands."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM commands
                WHERE status IN (?, ?) AND expires_at > ?
            """, (CommandStatus.QUEUED.value, CommandStatus.RECEIVED.value, now))
            row = cursor.fetchone()
            return row[0] if row else 0

    def save_agent_heartbeat(self, agent_id: str, connected_via: str, metrics: Dict[str, Any]) -> None:
        """Records agent heartbeat and telemetry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO agent_status (agent_id, last_heartbeat, connected_via, metrics)
                VALUES (?, ?, ?, ?)
            """, (agent_id, time.time(), connected_via, json.dumps(metrics)))
            conn.commit()

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves status and metrics for a specific agent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agent_status WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "agent_id": row["agent_id"],
                "last_heartbeat": row["last_heartbeat"],
                "connected_via": row["connected_via"],
                "metrics": json.loads(row["metrics"]) if row["metrics"] else {},
            }

    def list_all_agents(self) -> List[Dict[str, Any]]:
        """Lists all agents recorded in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agent_status ORDER BY last_heartbeat DESC")
            rows = cursor.fetchall()
            results = []
            for r in rows:
                results.append({
                    "agent_id": r["agent_id"],
                    "last_heartbeat": r["last_heartbeat"],
                    "connected_via": r["connected_via"],
                    "metrics": json.loads(r["metrics"]) if r["metrics"] else {},
                })
            return results

    def _row_to_record(self, row: sqlite3.Row) -> CommandRecord:
        """Converts a SQLite row into a CommandRecord pydantic model."""
        return CommandRecord(
            execution_id=row["execution_id"],
            command_id=row["command_id"],
            parameters=json.loads(row["parameters"]) if row["parameters"] else {},
            status=CommandStatus(row["status"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            dispatched_at=row["dispatched_at"],
            completed_at=row["completed_at"],
            result_message=row["result_message"],
            result_data=json.loads(row["result_data"]) if row["result_data"] else None,
            error_category=row["error_category"],
            agent_id=row["agent_id"],
            idempotency_key=row["idempotency_key"],
        )
