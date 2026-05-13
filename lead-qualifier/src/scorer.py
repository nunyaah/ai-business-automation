from __future__ import annotations
import json
import os
import re

from litellm import completion

from .models import (
    DimensionScore,
    LeadInput,
    LeadResponse,
    MANScore,
    Priority,
    Qualification,
)

MODEL = os.getenv("MODEL", "groq/llama-3.3-70b-versatile")

_SYSTEM_PROMPT = """You are a B2B sales qualification expert using the MAN framework (Money, Authority, Need).

Score each dimension 1–10 using these rubrics:

MONEY — budget likelihood:
  1–3  : Startup/solo operator, no budget signals
  4–6  : SMB with probable but unconfirmed budget
  7–9  : Mid-market/enterprise with clear budget signals (team size, explicit spend)
  10   : Budget explicitly mentioned or enterprise urgency with clear ROI

AUTHORITY — decision-making power:
  1–3  : End-user, intern, or clearly no purchasing power
  4–6  : Manager/team lead with influence but needs approval above them
  7–9  : Director/VP who can likely sign off independently
  10   : C-level or an explicit "we are ready to buy" statement

NEED — urgency and specificity of pain:
  1–3  : Vague curiosity, no specific problem
  4–6  : Problem exists but not urgent or not quantified
  7–9  : Specific pain with some urgency or quantification
  10   : Explicit urgency + quantified problem + stated business impact

Return ONLY a raw JSON object (no markdown, no fences):
{
  "money":    {"score": int, "reasoning": "1–2 sentences"},
  "authority": {"score": int, "reasoning": "1–2 sentences"},
  "need":     {"score": int, "reasoning": "1–2 sentences"},
  "recommended_action": "specific next step string",
  "suggested_followup": "personalised first-contact message, 2–3 sentences, address by first name"
}"""


def _clean_json(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return m.group(0) if m else raw


def _qualify(total: int) -> tuple[Qualification, Priority]:
    if total >= 22:
        return Qualification.QUALIFIED, Priority.HIGH
    if total >= 15:
        return Qualification.QUALIFIED, Priority.MEDIUM
    if total >= 8:
        return Qualification.UNQUALIFIED, Priority.LOW
    return Qualification.DISQUALIFIED, Priority.LOW


def score_lead(lead: LeadInput, model: str = MODEL) -> tuple[LeadResponse, float]:
    """Return (LeadResponse, cost_usd)."""
    user_msg = f"""Lead details:
Name        : {lead.name}
Company     : {lead.company}
Role        : {lead.role}
Company size: {lead.company_size or 'unknown'}
Source      : {lead.source or 'unknown'}

Inquiry:
{lead.inquiry}

Score this lead using the MAN framework."""

    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )

    raw = response.choices[0].message.content or ""
    data: dict = json.loads(_clean_json(raw))

    usage = response.usage
    cost = 0.0  # Groq free tier

    money = DimensionScore(**data["money"])
    authority = DimensionScore(**data["authority"])
    need = DimensionScore(**data["need"])

    total = money.score + authority.score + need.score
    qualification, priority = _qualify(total)

    return (
        LeadResponse(
            man_score=MANScore(money=money, authority=authority, need=need),
            total_score=total,
            max_score=30,
            qualification=qualification,
            priority=priority,
            recommended_action=data.get("recommended_action", "Follow up within 48 hours"),
            suggested_followup=data.get("suggested_followup", ""),
            processing_time_ms=0,  # set by caller
            cost_usd=cost,
        ),
        cost,
    )
