from __future__ import annotations
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from ..extractor import extract_invoice
from ..models import InvoiceResponse
from ..validator import InvoiceValidator

app = FastAPI(
    title="Invoice Processing Agent",
    description="AI-powered invoice extraction and validation. POST a PDF, get structured JSON.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_DB_PATH = os.getenv("DB_PATH", "invoices.db")
_THRESHOLD = float(os.getenv("AMOUNT_THRESHOLD", "1000.0"))
_MODEL = os.getenv("MODEL", "anthropic/claude-haiku-4-5-20251001")

_validator = InvoiceValidator(db_path=_DB_PATH, amount_threshold=_THRESHOLD)


@app.post("/process-invoice", response_model=InvoiceResponse, summary="Extract and validate an invoice PDF")
async def process_invoice(file: UploadFile = File(...)) -> InvoiceResponse:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    start = time.perf_counter()

    try:
        invoice, cost = extract_invoice(pdf_bytes, model=_MODEL)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Extraction failed: {exc}") from exc

    flags = _validator.validate(invoice)
    _validator.record_invoice(invoice)

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return InvoiceResponse(
        vendor=invoice.vendor,
        invoice_number=invoice.invoice_number,
        date=invoice.date,
        due_date=invoice.due_date,
        line_items=invoice.line_items,
        total=invoice.total,
        currency=invoice.currency,
        po_number=invoice.po_number,
        flags=flags,
        confidence=invoice.confidence,
        processing_time_ms=elapsed_ms,
        cost_usd=round(cost, 6),
    )


@app.get("/health", summary="Health check")
async def health() -> dict:
    return {"status": "ok", "version": app.version}
