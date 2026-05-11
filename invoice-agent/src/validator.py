from __future__ import annotations
import sqlite3
from datetime import datetime

from .models import ExtractedInvoice, FlagSeverity, FlagType, InvoiceFlag

_DDL = """
CREATE TABLE IF NOT EXISTS invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor        TEXT    NOT NULL,
    invoice_number TEXT,
    date          TEXT,
    total         REAL    NOT NULL,
    processed_at  TEXT    DEFAULT (datetime('now'))
)
"""


class InvoiceValidator:
    def __init__(self, db_path: str = "invoices.db", amount_threshold: float = 1000.0):
        self.db_path = db_path
        self.amount_threshold = amount_threshold
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_DDL)
            conn.commit()

    def validate(self, invoice: ExtractedInvoice) -> list[InvoiceFlag]:
        flags: list[InvoiceFlag] = []

        if not invoice.po_number:
            flags.append(
                InvoiceFlag(
                    type=FlagType.MISSING_PO,
                    severity=FlagSeverity.HIGH,
                    message="No PO number found. Requires approval before processing.",
                )
            )

        if invoice.total > self.amount_threshold:
            flags.append(
                InvoiceFlag(
                    type=FlagType.AMOUNT_THRESHOLD,
                    severity=FlagSeverity.MEDIUM,
                    message=(
                        f"Total ${invoice.total:,.2f} exceeds "
                        f"${self.amount_threshold:,.0f} auto-approval limit."
                    ),
                )
            )

        if invoice.line_items:
            computed = sum(item.amount for item in invoice.line_items)
            if abs(computed - invoice.total) > 0.02:
                flags.append(
                    InvoiceFlag(
                        type=FlagType.LINE_ITEM_MISMATCH,
                        severity=FlagSeverity.HIGH,
                        message=(
                            f"Line items sum to ${computed:,.2f} "
                            f"but invoice total is ${invoice.total:,.2f}."
                        ),
                    )
                )

        if self._is_duplicate(invoice):
            flags.append(
                InvoiceFlag(
                    type=FlagType.DUPLICATE_SUSPECTED,
                    severity=FlagSeverity.HIGH,
                    message=(
                        "Possible duplicate: same vendor and amount "
                        "processed within 30 days."
                    ),
                )
            )

        return flags

    def _is_duplicate(self, invoice: ExtractedInvoice) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT date FROM invoices
                WHERE vendor = ?
                  AND total  = ?
                  AND processed_at >= datetime('now', '-30 days')
                """,
                (invoice.vendor, invoice.total),
            ).fetchall()

        if not rows:
            return False

        if invoice.date:
            try:
                inv_dt = datetime.strptime(invoice.date, "%Y-%m-%d")
                for (date_str,) in rows:
                    if date_str:
                        try:
                            existing_dt = datetime.strptime(date_str, "%Y-%m-%d")
                            if abs((inv_dt - existing_dt).days) <= 30:
                                return True
                        except ValueError:
                            pass
            except ValueError:
                pass

        return len(rows) > 0

    def record_invoice(self, invoice: ExtractedInvoice) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO invoices (vendor, invoice_number, date, total) VALUES (?, ?, ?, ?)",
                (invoice.vendor, invoice.invoice_number, invoice.date, invoice.total),
            )
            conn.commit()
