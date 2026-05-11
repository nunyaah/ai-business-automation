from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from src.extractor import extract_invoice
from src.models import ExtractedInvoice, LineItem

_MOCK_JSON = """{
    "vendor": "Acme Supplies Ltd",
    "invoice_number": "INV-20240312",
    "date": "2024-03-12",
    "due_date": "2024-04-12",
    "line_items": [
        {"description": "Office chairs x5", "amount": 1250.00},
        {"description": "Delivery", "amount": 75.00}
    ],
    "total": 1325.00,
    "currency": "USD",
    "po_number": null,
    "confidence": 0.94
}"""


def _make_response(content: str, prompt_tokens: int = 500, completion_tokens: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.choices[0].message.content = content
    mock.usage.prompt_tokens = prompt_tokens
    mock.usage.completion_tokens = completion_tokens
    return mock


@patch("src.extractor.extract_text_from_pdf", return_value="Invoice text content")
@patch("src.extractor.completion")
def test_basic_extraction(mock_completion, mock_text):
    mock_completion.return_value = _make_response(_MOCK_JSON)

    invoice, cost = extract_invoice(b"fake-pdf")

    assert invoice.vendor == "Acme Supplies Ltd"
    assert invoice.invoice_number == "INV-20240312"
    assert invoice.date == "2024-03-12"
    assert invoice.due_date == "2024-04-12"
    assert invoice.total == 1325.00
    assert invoice.po_number is None
    assert invoice.currency == "USD"
    assert invoice.confidence == pytest.approx(0.94)
    assert len(invoice.line_items) == 2
    assert cost == 0.0  # Groq free tier — no per-token charge


@patch("src.extractor.extract_text_from_pdf", return_value="text")
@patch("src.extractor.completion")
def test_extraction_with_po_number(mock_completion, mock_text):
    content = _MOCK_JSON.replace('"po_number": null', '"po_number": "PO-2024-001"')
    mock_completion.return_value = _make_response(content)

    invoice, _ = extract_invoice(b"fake-pdf")

    assert invoice.po_number == "PO-2024-001"


@patch("src.extractor.extract_text_from_pdf", return_value="text")
@patch("src.extractor.completion")
def test_cost_is_zero_on_groq(mock_completion, mock_text):
    mock_completion.return_value = _make_response(
        _MOCK_JSON, prompt_tokens=1000, completion_tokens=500
    )

    _, cost = extract_invoice(b"fake-pdf")

    # Groq free tier: both per-token rates are 0.0
    assert cost == 0.0


@patch("src.extractor.extract_text_from_pdf", return_value="text")
@patch("src.extractor.completion")
def test_line_items_parsed_correctly(mock_completion, mock_text):
    mock_completion.return_value = _make_response(_MOCK_JSON)

    invoice, _ = extract_invoice(b"fake-pdf")

    assert invoice.line_items[0].description == "Office chairs x5"
    assert invoice.line_items[0].amount == pytest.approx(1250.00)
    assert invoice.line_items[1].description == "Delivery"
    assert invoice.line_items[1].amount == pytest.approx(75.00)


@patch("src.extractor.extract_text_from_pdf", return_value="text")
@patch("src.extractor.completion")
def test_missing_fields_default_gracefully(mock_completion, mock_text):
    minimal = '{"vendor": "Mystery Corp", "total": 99.0, "confidence": 0.7}'
    mock_completion.return_value = _make_response(minimal)

    invoice, _ = extract_invoice(b"fake-pdf")

    assert invoice.vendor == "Mystery Corp"
    assert invoice.total == 99.0
    assert invoice.invoice_number is None
    assert invoice.date is None
    assert invoice.line_items == []
    assert invoice.currency == "USD"


@patch("src.extractor.extract_text_from_pdf", return_value="text")
@patch("src.extractor.completion")
def test_confidence_clamped_to_valid_range(mock_completion, mock_text):
    content = _MOCK_JSON.replace('"confidence": 0.94', '"confidence": 1.5')
    mock_completion.return_value = _make_response(content)

    invoice, _ = extract_invoice(b"fake-pdf")

    assert invoice.confidence <= 1.0
