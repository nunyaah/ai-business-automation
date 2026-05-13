from __future__ import annotations
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from ..classifier import classify_ticket
from ..models import TicketInput, TriageResponse
from ..storage import TicketStore

app = FastAPI(
    title="Support Ticket Triage Agent",
    description="AI-powered ticket priority, category classification, and response drafting.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_MODEL = os.getenv("MODEL", "groq/llama-3.3-70b-versatile")
_DB_PATH = os.getenv("DB_PATH", "tickets.db")

_store = TicketStore(db_path=_DB_PATH)


@app.post("/triage-ticket", response_model=TriageResponse, summary="Triage a support ticket")
async def triage_ticket(ticket: TicketInput) -> TriageResponse:
    start = time.perf_counter()

    try:
        result, cost = classify_ticket(ticket, model=_MODEL)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Classification failed: {exc}") from exc

    _store.record(ticket.ticket_id, result)

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return TriageResponse(
        ticket_id=ticket.ticket_id,
        priority=result.priority,
        priority_reasoning=result.priority_reasoning,
        category=result.category,
        subcategory=result.subcategory,
        escalate=result.escalate,
        escalation_reason=result.escalation_reason,
        suggested_response=result.suggested_response,
        confidence=result.confidence,
        processing_time_ms=elapsed_ms,
        cost_usd=round(cost, 6),
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": app.version}
