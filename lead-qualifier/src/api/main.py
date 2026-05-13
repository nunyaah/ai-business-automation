from __future__ import annotations
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from ..models import LeadInput, LeadResponse
from ..scorer import score_lead

app = FastAPI(
    title="Lead Qualification Agent",
    description="MAN-framework lead scoring. POST a lead, get a qualification decision.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_MODEL = os.getenv("MODEL", "groq/llama-3.3-70b-versatile")


@app.post("/qualify-lead", response_model=LeadResponse, summary="Score and qualify a lead")
async def qualify_lead(lead: LeadInput) -> LeadResponse:
    start = time.perf_counter()

    try:
        result, cost = score_lead(lead, model=_MODEL)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Scoring failed: {exc}") from exc

    result.processing_time_ms = int((time.perf_counter() - start) * 1000)
    result.cost_usd = round(cost, 6)
    return result


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": app.version}
