from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class CustomerTier(str, Enum):
    PREMIUM = "premium"
    STANDARD = "standard"
    FREE = "free"


class TicketInput(BaseModel):
    ticket_id: str
    subject: str
    body: str
    customer_tier: CustomerTier = CustomerTier.STANDARD
    submitted_at: Optional[str] = None


class TriageResult(BaseModel):
    priority: Priority
    priority_reasoning: str
    category: str
    subcategory: str
    escalate: bool
    escalation_reason: Optional[str]
    suggested_response: str
    confidence: float

    @field_validator("confidence")
    @classmethod
    def clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class TriageResponse(BaseModel):
    ticket_id: str
    priority: Priority
    priority_reasoning: str
    category: str
    subcategory: str
    escalate: bool
    escalation_reason: Optional[str]
    suggested_response: str
    confidence: float
    processing_time_ms: int
    cost_usd: float
