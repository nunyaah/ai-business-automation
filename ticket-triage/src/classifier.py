from __future__ import annotations
import json
import os
import re

from litellm import completion

from .models import CustomerTier, Priority, TicketInput, TriageResult

MODEL = os.getenv("MODEL", "groq/llama-3.3-70b-versatile")

_SYSTEM_PROMPT = """You are a support ticket triage agent. Classify the ticket and draft a first response.

PRIORITY RULES — apply strictly, top rule wins:
  P1 : account cannot be accessed | payment failure | data loss or corruption |
       customer states explicit time constraint | premium customer with any blocker
  P2 : feature not working correctly | billing question | non-urgent account issue |
       integration problem | performance degradation
  P3 : feature request | general how-to question | documentation query |
       positive feedback | no clear problem stated

ESCALATION: escalate=true when priority is P1, OR when customer_tier is "premium" AND priority is P2.

CATEGORIES (pick the single best fit):
  Authentication | Billing | Data | Performance | Feature Request |
  Account Management | Integration | Bug Report | General Inquiry

Return ONLY a raw JSON object (no markdown, no fences):
{
  "priority": "P1" | "P2" | "P3",
  "priority_reasoning": "1–2 sentences citing the specific rule triggered",
  "category": "string from the list above",
  "subcategory": "specific sub-topic string",
  "escalate": boolean,
  "escalation_reason": "string or null",
  "suggested_response": "empathetic, action-oriented response, 2–4 sentences, use [Name] placeholder",
  "confidence": number 0.1–1.0
}"""


def _clean_json(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return m.group(0) if m else raw


def classify_ticket(ticket: TicketInput, model: str = MODEL) -> tuple[TriageResult, float]:
    """Return (TriageResult, cost_usd)."""
    user_msg = f"""Ticket ID     : {ticket.ticket_id}
Customer tier : {ticket.customer_tier.value}
Submitted at  : {ticket.submitted_at or 'unknown'}

Subject:
{ticket.subject}

Body:
{ticket.body}

Classify and draft a response."""

    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )

    raw = response.choices[0].message.content or ""
    data: dict = json.loads(_clean_json(raw))

    # Enforce escalation rule deterministically — don't trust the LLM alone
    priority = Priority(data["priority"])
    is_premium = ticket.customer_tier == CustomerTier.PREMIUM
    should_escalate = priority == Priority.P1 or (is_premium and priority == Priority.P2)

    escalation_reason = data.get("escalation_reason")
    if should_escalate and not escalation_reason:
        escalation_reason = (
            "P1 priority" if priority == Priority.P1
            else "Premium customer with P2 issue"
        )

    raw_conf = data.get("confidence")
    confidence = float(raw_conf) if raw_conf else 0.85

    result = TriageResult(
        priority=priority,
        priority_reasoning=data.get("priority_reasoning", ""),
        category=data.get("category", "General Inquiry"),
        subcategory=data.get("subcategory", ""),
        escalate=should_escalate,
        escalation_reason=escalation_reason if should_escalate else None,
        suggested_response=data.get("suggested_response", ""),
        confidence=confidence,
    )

    return result, 0.0  # Groq free tier
