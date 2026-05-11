from __future__ import annotations
import os
import tempfile

import pytest

from src.models import ExtractedInvoice, FlagType, LineItem
from src.validator import InvoiceValidator


@pytest.fixture
def validator(tmp_path):
    db = tmp_path / "test_invoices.db"
    return InvoiceValidator(db_path=str(db), amount_threshold=1000.0)


def _invoice(**overrides) -> ExtractedInvoice:
    defaults = dict(
        vendor="Acme Ltd",
        invoice_number="INV-001",
        date="2024-03-12",
        due_date="2024-04-12",
        line_items=[LineItem(description="Widget A", amount=500.0)],
        total=500.0,
        currency="USD",
        po_number="PO-2024-001",
        confidence=0.95,
    )
    defaults.update(overrides)
    return ExtractedInvoice(**defaults)


# ── PO number rules ─────────────────────────────────────────────────────────

def test_flags_missing_po(validator):
    flags = validator.validate(_invoice(po_number=None))
    assert FlagType.MISSING_PO in [f.type for f in flags]


def test_no_missing_po_flag_when_present(validator):
    flags = validator.validate(_invoice(po_number="PO-001"))
    assert FlagType.MISSING_PO not in [f.type for f in flags]


# ── Amount threshold rules ───────────────────────────────────────────────────

def test_flags_amount_over_threshold(validator):
    flags = validator.validate(
        _invoice(total=1500.0, line_items=[LineItem(description="Big item", amount=1500.0)])
    )
    assert FlagType.AMOUNT_THRESHOLD in [f.type for f in flags]


def test_no_threshold_flag_at_exact_limit(validator):
    flags = validator.validate(
        _invoice(total=1000.0, line_items=[LineItem(description="Item", amount=1000.0)])
    )
    assert FlagType.AMOUNT_THRESHOLD not in [f.type for f in flags]


def test_no_threshold_flag_below_limit(validator):
    flags = validator.validate(_invoice(total=999.99, line_items=[LineItem(description="Item", amount=999.99)]))
    assert FlagType.AMOUNT_THRESHOLD not in [f.type for f in flags]


# ── Line item mismatch rules ─────────────────────────────────────────────────

def test_flags_line_item_mismatch(validator):
    flags = validator.validate(
        _invoice(
            line_items=[
                LineItem(description="A", amount=300.0),
                LineItem(description="B", amount=100.0),
            ],
            total=500.0,  # actual sum is 400.0
        )
    )
    assert FlagType.LINE_ITEM_MISMATCH in [f.type for f in flags]


def test_no_mismatch_flag_when_correct(validator):
    flags = validator.validate(
        _invoice(
            line_items=[
                LineItem(description="A", amount=250.0),
                LineItem(description="B", amount=250.0),
            ],
            total=500.0,
        )
    )
    assert FlagType.LINE_ITEM_MISMATCH not in [f.type for f in flags]


def test_no_mismatch_within_rounding_tolerance(validator):
    flags = validator.validate(
        _invoice(
            line_items=[LineItem(description="Item", amount=499.99)],
            total=500.0,  # $0.01 diff — within $0.02 tolerance
        )
    )
    assert FlagType.LINE_ITEM_MISMATCH not in [f.type for f in flags]


def test_no_mismatch_flag_when_no_line_items(validator):
    flags = validator.validate(_invoice(line_items=[], total=500.0))
    assert FlagType.LINE_ITEM_MISMATCH not in [f.type for f in flags]


# ── Duplicate detection rules ────────────────────────────────────────────────

def test_flags_duplicate_same_vendor_and_amount(validator):
    inv = _invoice()
    validator.record_invoice(inv)

    duplicate = _invoice(invoice_number="INV-002")
    flags = validator.validate(duplicate)
    assert FlagType.DUPLICATE_SUSPECTED in [f.type for f in flags]


def test_no_duplicate_different_vendor(validator):
    validator.record_invoice(_invoice(vendor="Vendor A"))

    flags = validator.validate(_invoice(vendor="Vendor B"))
    assert FlagType.DUPLICATE_SUSPECTED not in [f.type for f in flags]


def test_no_duplicate_different_amount(validator):
    validator.record_invoice(_invoice(total=500.0, line_items=[LineItem(description="X", amount=500.0)]))

    flags = validator.validate(
        _invoice(total=600.0, line_items=[LineItem(description="X", amount=600.0)])
    )
    assert FlagType.DUPLICATE_SUSPECTED not in [f.type for f in flags]


def test_first_invoice_never_flagged_as_duplicate(validator):
    flags = validator.validate(_invoice())
    assert FlagType.DUPLICATE_SUSPECTED not in [f.type for f in flags]


# ── Clean invoice — no flags ─────────────────────────────────────────────────

def test_clean_invoice_has_no_flags(validator):
    flags = validator.validate(
        _invoice(
            po_number="PO-999",
            total=500.0,
            line_items=[LineItem(description="Item", amount=500.0)],
        )
    )
    assert flags == []
