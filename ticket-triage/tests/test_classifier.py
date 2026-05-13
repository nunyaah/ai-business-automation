from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from src.models import CustomerTier, Priority, TicketInput
from src.classifier import classify_ticket


def _make_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.choices[0].message.content = content
    mock.usage.prompt_tokens = 250
    mock.usage.completion_tokens = 120
    return mock


def _ticket(**overrides) -> TicketInput:
    defaults = dict(
        ticket_id="TKT-001",
        subject="Cannot log in",
        body="I cannot access my account.",
        customer_tier=CustomerTier.STANDARD,
        submitted_at="2024-03-12T09:15:00Z",
    )
    defaults.update(overrides)
    return TicketInput(**defaults)


_P1_JSON = """{
  "priority": "P1",
  "priority_reasoning": "Account cannot be accessed — direct authentication blocker.",
  "category": "Authentication",
  "subcategory": "Login Failure",
  "escalate": true,
  "escalation_reason": "P1 priority",
  "suggested_response": "Hi [Name], I am prioritising your case right now and have escalated it to the technical team. Someone will contact you within 30 minutes.",
  "confidence": 0.95
}"""

_P2_JSON = """{
  "priority": "P2",
  "priority_reasoning": "Feature not working correctly — export button unresponsive.",
  "category": "Bug Report",
  "subcategory": "UI Bug",
  "escalate": false,
  "escalation_reason": null,
  "suggested_response": "Hi [Name], thanks for reporting this. Our team is investigating the export button issue and will have a fix deployed shortly.",
  "confidence": 0.88
}"""

_P3_JSON = """{
  "priority": "P3",
  "priority_reasoning": "General how-to question — no product issue.",
  "category": "General Inquiry",
  "subcategory": "How-To",
  "escalate": false,
  "escalation_reason": null,
  "suggested_response": "Hi [Name], great question! You can export reports by navigating to Reports > Export > Choose format.",
  "confidence": 0.92
}"""


# ── Priority classification ──────────────────────────────────────────────────

@patch("src.classifier.completion")
def test_p1_classification(mock_completion):
    mock_completion.return_value = _make_response(_P1_JSON)
    result, _ = classify_ticket(_ticket())
    assert result.priority == Priority.P1
    assert result.escalate is True
    assert result.category == "Authentication"


@patch("src.classifier.completion")
def test_p2_classification(mock_completion):
    mock_completion.return_value = _make_response(_P2_JSON)
    result, _ = classify_ticket(_ticket(subject="Export not working", body="The export button does nothing."))
    assert result.priority == Priority.P2
    assert result.escalate is False


@patch("src.classifier.completion")
def test_p3_classification(mock_completion):
    mock_completion.return_value = _make_response(_P3_JSON)
    result, _ = classify_ticket(_ticket(subject="How do I export?", body="How do I export my reports?"))
    assert result.priority == Priority.P3
    assert result.escalate is False


# ── Deterministic escalation enforcement ────────────────────────────────────

@patch("src.classifier.completion")
def test_premium_p2_always_escalated(mock_completion):
    """P2 for a premium customer must be escalated regardless of LLM output."""
    p2_no_escalate = _P2_JSON  # LLM says escalate=false
    mock_completion.return_value = _make_response(p2_no_escalate)

    result, _ = classify_ticket(_ticket(customer_tier=CustomerTier.PREMIUM))

    assert result.escalate is True
    assert result.escalation_reason is not None


@patch("src.classifier.completion")
def test_standard_p2_not_escalated(mock_completion):
    mock_completion.return_value = _make_response(_P2_JSON)
    result, _ = classify_ticket(_ticket(customer_tier=CustomerTier.STANDARD))
    assert result.escalate is False


@patch("src.classifier.completion")
def test_p1_always_escalated_regardless_of_tier(mock_completion):
    mock_completion.return_value = _make_response(_P1_JSON)
    result, _ = classify_ticket(_ticket(customer_tier=CustomerTier.FREE))
    assert result.escalate is True


# ── Confidence fallback ──────────────────────────────────────────────────────

@patch("src.classifier.completion")
def test_confidence_null_defaults_to_085(mock_completion):
    json_no_conf = _P2_JSON.replace('"confidence": 0.88', '"confidence": null')
    mock_completion.return_value = _make_response(json_no_conf)
    result, _ = classify_ticket(_ticket())
    assert result.confidence == pytest.approx(0.85)


@patch("src.classifier.completion")
def test_confidence_clamped_to_1(mock_completion):
    json_high_conf = _P1_JSON.replace('"confidence": 0.95', '"confidence": 1.5')
    mock_completion.return_value = _make_response(json_high_conf)
    result, _ = classify_ticket(_ticket())
    assert result.confidence <= 1.0


# ── Cost ─────────────────────────────────────────────────────────────────────

@patch("src.classifier.completion")
def test_cost_is_zero(mock_completion):
    mock_completion.return_value = _make_response(_P1_JSON)
    _, cost = classify_ticket(_ticket())
    assert cost == 0.0


# ── Escalation reason auto-filled ────────────────────────────────────────────

@patch("src.classifier.completion")
def test_escalation_reason_auto_set_for_p1(mock_completion):
    json_no_reason = _P1_JSON.replace('"escalation_reason": "P1 priority"', '"escalation_reason": null')
    mock_completion.return_value = _make_response(json_no_reason)
    result, _ = classify_ticket(_ticket())
    assert result.escalate is True
    assert result.escalation_reason == "P1 priority"


# ── Suggested response ────────────────────────────────────────────────────────

@patch("src.classifier.completion")
def test_suggested_response_not_empty(mock_completion):
    mock_completion.return_value = _make_response(_P1_JSON)
    result, _ = classify_ticket(_ticket())
    assert len(result.suggested_response) > 10
