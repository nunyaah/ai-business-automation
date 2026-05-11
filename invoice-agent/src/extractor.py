from __future__ import annotations
import io
import json
import os
import re

import pdfplumber
from litellm import completion

from .models import ExtractedInvoice, LineItem

MODEL = os.getenv("MODEL", "groq/llama-3.3-70b-versatile")

# Groq is free tier; cost tracking still works for paid models via LiteLLM
_INPUT_COST_PER_TOKEN = 0.0
_OUTPUT_COST_PER_TOKEN = 0.0

_SYSTEM_PROMPT = """You are an invoice data extraction agent. Extract structured data from the invoice text.

Return ONLY a raw JSON object (no markdown, no code fences, no commentary) with this exact schema:
{
  "vendor": "string — company that issued the invoice",
  "invoice_number": "string or null",
  "date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "line_items": [{"description": "string", "amount": number}],
  "total": number,
  "currency": "3-letter ISO code, default USD",
  "po_number": "purchase order number string or null",
  "confidence": number between 0.1 and 1.0 representing extraction certainty
}

Rules:
- Extract EVERY line item. Do not summarise or skip any.
- Concatenate text across page breaks — treat the whole document as one invoice.
- If a field is not present in the document, use null (not empty string).
- Set confidence to 0.9+ for clean machine-readable PDFs, lower for ambiguous content.
- Start your response with { and end with }."""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract and concatenate text from all PDF pages."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages: list[str] = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n--- PAGE BREAK ---\n\n".join(pages)


def extract_invoice(
    pdf_bytes: bytes,
    model: str = MODEL,
) -> tuple[ExtractedInvoice, float]:
    """Return (ExtractedInvoice, cost_usd). Cost is 0.0 on Groq free tier."""
    text = extract_text_from_pdf(pdf_bytes)

    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract invoice data:\n\n{text}"},
        ],
    )

    raw = response.choices[0].message.content or ""

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())

    # Extract the JSON object if extra text surrounds it
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)

    data: dict = json.loads(raw)

    usage = response.usage
    cost = (
        usage.prompt_tokens * _INPUT_COST_PER_TOKEN
        + usage.completion_tokens * _OUTPUT_COST_PER_TOKEN
    )

    line_items = [
        LineItem(description=item["description"], amount=float(item["amount"]))
        for item in data.get("line_items", [])
    ]

    # Some open-source models return 0 or null for confidence — default to 0.85
    raw_confidence = data.get("confidence")
    confidence = float(raw_confidence) if raw_confidence else 0.85

    invoice = ExtractedInvoice(
        vendor=data.get("vendor") or "Unknown",
        invoice_number=data.get("invoice_number"),
        date=data.get("date"),
        due_date=data.get("due_date"),
        line_items=line_items,
        total=float(data.get("total", 0.0)),
        currency=data.get("currency") or "USD",
        po_number=data.get("po_number"),
        confidence=confidence,
    )

    return invoice, cost
