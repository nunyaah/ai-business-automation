from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator


class FlagType(str, Enum):
    MISSING_PO = "MISSING_PO"
    AMOUNT_THRESHOLD = "AMOUNT_THRESHOLD"
    DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"
    LINE_ITEM_MISMATCH = "LINE_ITEM_MISMATCH"


class FlagSeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class LineItem(BaseModel):
    description: str
    amount: float


class InvoiceFlag(BaseModel):
    type: FlagType
    severity: FlagSeverity
    message: str


class ExtractedInvoice(BaseModel):
    vendor: str
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    line_items: list[LineItem] = []
    total: float
    currency: str = "USD"
    po_number: Optional[str] = None
    confidence: float

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class InvoiceResponse(BaseModel):
    vendor: str
    invoice_number: Optional[str]
    date: Optional[str]
    due_date: Optional[str]
    line_items: list[LineItem]
    total: float
    currency: str
    po_number: Optional[str]
    flags: list[InvoiceFlag]
    confidence: float
    processing_time_ms: int
    cost_usd: float
