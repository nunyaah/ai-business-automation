from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from src.models import LeadInput, Qualification, Priority
from src.scorer import score_lead, _qualify

# ── Qualification threshold logic ────────────────────────────────────────────

@pytest.mark.parametrize("total,expected_qual,expected_pri", [
    (30, Qualification.QUALIFIED,    Priority.HIGH),
    (22, Qualification.QUALIFIED,    Priority.HIGH),
    (21, Qualification.QUALIFIED,    Priority.MEDIUM),
    (15, Qualification.QUALIFIED,    Priority.MEDIUM),
    (14, Qualification.UNQUALIFIED,  Priority.LOW),
    (8,  Qualification.UNQUALIFIED,  Priority.LOW),
    (7,  Qualification.DISQUALIFIED, Priority.LOW),
    (1,  Qualification.DISQUALIFIED, Priority.LOW),
])
def test_qualify_thresholds(total, expected_qual, expected_pri):
    qual, pri = _qualify(total)
    assert qual == expected_qual
    assert pri == expected_pri


# ── Mock LLM response ────────────────────────────────────────────────────────

_MOCK_JSON = """{
  "money":    {"score": 7, "reasoning": "50-100 employee company suggests budget capacity."},
  "authority": {"score": 6, "reasoning": "Operations Manager has influence but may need C-level sign-off."},
  "need":     {"score": 9, "reasoning": "500 tickets/month with team struggling is quantified and urgent."},
  "recommended_action": "Book 30-minute discovery call within 24 hours",
  "suggested_followup": "Hi Sarah, 500 tickets a month is exactly the problem we solve. Would Thursday or Friday work for a 10-minute demo?"
}"""


def _make_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.choices[0].message.content = content
    mock.usage.prompt_tokens = 300
    mock.usage.completion_tokens = 150
    return mock


def _sample_lead(**overrides) -> LeadInput:
    defaults = dict(
        name="Sarah Khan",
        company="TechRetail PK",
        role="Operations Manager",
        email="sarah@techretail.pk",
        inquiry="We have around 500 support tickets per month and our team is struggling to keep up.",
        company_size="50-100 employees",
        source="contact_form",
    )
    defaults.update(overrides)
    return LeadInput(**defaults)


@patch("src.scorer.completion")
def test_score_lead_qualified_high(mock_completion):
    mock_completion.return_value = _make_response(_MOCK_JSON)

    result, cost = score_lead(_sample_lead())

    assert result.man_score.money.score == 7
    assert result.man_score.authority.score == 6
    assert result.man_score.need.score == 9
    assert result.total_score == 22
    assert result.max_score == 30
    assert result.qualification == Qualification.QUALIFIED
    assert result.priority == Priority.HIGH
    assert result.recommended_action != ""
    assert result.suggested_followup != ""
    assert cost == 0.0


@patch("src.scorer.completion")
def test_score_lead_unqualified(mock_completion):
    low_json = """{
      "money":    {"score": 2, "reasoning": "Individual freelancer, no budget signals."},
      "authority": {"score": 2, "reasoning": "No purchasing authority stated."},
      "need":     {"score": 4, "reasoning": "Vague interest, no specific problem."},
      "recommended_action": "Send product overview email only",
      "suggested_followup": "Hi there, thanks for reaching out. Here is some info about our product."
    }"""
    mock_completion.return_value = _make_response(low_json)

    result, _ = score_lead(_sample_lead())

    assert result.total_score == 8
    assert result.qualification == Qualification.UNQUALIFIED
    assert result.priority == Priority.LOW


@patch("src.scorer.completion")
def test_score_lead_disqualified(mock_completion):
    low_json = """{
      "money":    {"score": 1, "reasoning": "Student project."},
      "authority": {"score": 1, "reasoning": "Student."},
      "need":     {"score": 1, "reasoning": "Exploring options only."},
      "recommended_action": "No action — nurture sequence only",
      "suggested_followup": "Thanks for your interest!"
    }"""
    mock_completion.return_value = _make_response(low_json)

    result, _ = score_lead(_sample_lead())

    assert result.qualification == Qualification.DISQUALIFIED
    assert result.total_score == 3


@patch("src.scorer.completion")
def test_dimension_scores_clamped(mock_completion):
    json_out_of_range = """{
      "money":    {"score": 15, "reasoning": "Off the scale."},
      "authority": {"score": 0,  "reasoning": "Below minimum."},
      "need":     {"score": 8,  "reasoning": "OK."},
      "recommended_action": "Follow up",
      "suggested_followup": "Hi."
    }"""
    mock_completion.return_value = _make_response(json_out_of_range)

    result, _ = score_lead(_sample_lead())

    assert result.man_score.money.score == 10     # clamped from 15
    assert result.man_score.authority.score == 1   # clamped from 0


@patch("src.scorer.completion")
def test_cost_is_zero(mock_completion):
    mock_completion.return_value = _make_response(_MOCK_JSON)
    _, cost = score_lead(_sample_lead())
    assert cost == 0.0


@patch("src.scorer.completion")
def test_reasoning_preserved(mock_completion):
    mock_completion.return_value = _make_response(_MOCK_JSON)
    result, _ = score_lead(_sample_lead())
    assert "500 tickets" in result.man_score.need.reasoning


@patch("src.scorer.completion")
def test_medium_priority_band(mock_completion):
    medium_json = """{
      "money":    {"score": 5, "reasoning": "SMB, probable budget."},
      "authority": {"score": 5, "reasoning": "Manager level."},
      "need":     {"score": 6, "reasoning": "Problem exists but not urgent."},
      "recommended_action": "Send case study and follow up in 3 days",
      "suggested_followup": "Hi, thanks for reaching out."
    }"""
    mock_completion.return_value = _make_response(medium_json)
    result, _ = score_lead(_sample_lead())
    assert result.total_score == 16
    assert result.qualification == Qualification.QUALIFIED
    assert result.priority == Priority.MEDIUM
