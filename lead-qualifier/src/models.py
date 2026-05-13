from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator


class Qualification(str, Enum):
    QUALIFIED = "QUALIFIED"
    UNQUALIFIED = "UNQUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DimensionScore(BaseModel):
    score: int  # 1–10
    reasoning: str

    @field_validator("score")
    @classmethod
    def clamp(cls, v: int) -> int:
        return max(1, min(10, v))


class MANScore(BaseModel):
    money: DimensionScore
    authority: DimensionScore
    need: DimensionScore


class LeadInput(BaseModel):
    name: str
    company: str
    role: str
    email: str
    inquiry: str
    company_size: Optional[str] = None
    source: Optional[str] = None


class LeadResponse(BaseModel):
    man_score: MANScore
    total_score: int
    max_score: int = 30
    qualification: Qualification
    priority: Priority
    recommended_action: str
    suggested_followup: str
    processing_time_ms: int
    cost_usd: float
