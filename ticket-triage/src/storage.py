from __future__ import annotations
import sqlite3

from .models import Priority, TriageResult

_DDL = """
CREATE TABLE IF NOT EXISTS tickets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id    TEXT    NOT NULL,
    priority     TEXT    NOT NULL,
    category     TEXT,
    escalated    INTEGER NOT NULL DEFAULT 0,
    processed_at TEXT    DEFAULT (datetime('now'))
)
"""


class TicketStore:
    def __init__(self, db_path: str = "tickets.db"):
        self.db_path = db_path
        with sqlite3.connect(db_path) as conn:
            conn.execute(_DDL)
            conn.commit()

    def record(self, ticket_id: str, result: TriageResult) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tickets (ticket_id, priority, category, escalated) VALUES (?, ?, ?, ?)",
                (ticket_id, result.priority.value, result.category, int(result.escalate)),
            )
            conn.commit()

    def p1_count_last_hour(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE priority='P1' AND processed_at >= datetime('now','-1 hour')"
            ).fetchone()
        return row[0] if row else 0
