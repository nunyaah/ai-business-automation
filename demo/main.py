"""Unified demo interface for all three AI business automation agents."""
from __future__ import annotations
import asyncio
import io
import json
import os
import re
from pathlib import Path
from typing import AsyncGenerator

import pdfplumber
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from litellm import acompletion

load_dotenv()

ROOT = Path(__file__).parent.parent
INVOICE_SAMPLES_DIR = ROOT / "invoice-agent" / "data" / "sample_invoices"
LEAD_SAMPLES_PATH = ROOT / "lead-qualifier" / "data" / "sample_leads.json"
TICKET_SAMPLES_PATH = ROOT / "ticket-triage" / "data" / "sample_tickets.json"
STATIC_DIR = Path(__file__).parent / "static"

MODEL = os.getenv("MODEL", "groq/llama-3.3-70b-versatile")

app = FastAPI(title="AI Business Automation Demo")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _clean_json(raw: str) -> str:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw.strip())
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return m.group(0) if m else raw


# ── Sample listing endpoints ──────────────────────────────────────────────────

@app.get("/api/samples/invoice")
def invoice_samples():
    files = sorted(INVOICE_SAMPLES_DIR.glob("*.pdf"))
    return [{"id": f.stem, "name": f.stem.replace("_", " ").title()} for f in files]


@app.get("/api/samples/lead")
def lead_samples():
    leads = json.loads(LEAD_SAMPLES_PATH.read_text())
    return [
        {
            "index": i,
            "name": l["name"],
            "company": l["company"],
            "role": l["role"],
            "expected": f"{l.get('_expected_qualification', '?')} / {l.get('_expected_priority', '?')}",
        }
        for i, l in enumerate(leads)
    ]


@app.get("/api/samples/ticket")
def ticket_samples():
    tickets = json.loads(TICKET_SAMPLES_PATH.read_text())
    return [
        {
            "index": i,
            "ticket_id": t["ticket_id"],
            "subject": t["subject"],
            "tier": t["customer_tier"],
            "expected_priority": t.get("_expected_priority", "?"),
            "expected_escalate": t.get("_expected_escalate", False),
        }
        for i, t in enumerate(tickets)
    ]


# ── Invoice streaming ─────────────────────────────────────────────────────────

_INVOICE_SYSTEM = """You are an invoice data extraction agent. Extract structured data from invoice text.

Return ONLY a raw JSON object (no markdown, no code fences, no commentary):
{
  "vendor": "company that issued the invoice",
  "invoice_number": "string or null",
  "date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "line_items": [{"description": "string", "amount": number}],
  "total": number,
  "currency": "3-letter ISO code, default USD",
  "po_number": "purchase order number or null",
  "confidence": number 0.1–1.0
}
Rules: extract every line item, use null for missing fields, start with { end with }."""


async def _stream_invoice(sample_id: str) -> AsyncGenerator[str, None]:
    pdf_path = INVOICE_SAMPLES_DIR / f"{sample_id}.pdf"
    if not pdf_path.exists():
        yield _sse({"type": "error", "message": f"Sample '{sample_id}' not found"})
        return

    try:
        yield _sse({"type": "status", "message": "Reading sample invoice PDF..."})
        pdf_bytes = pdf_path.read_bytes()

        yield _sse({"type": "status", "message": "Extracting text from PDF with pdfplumber..."})
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [p.extract_text().strip() for p in pdf.pages if p.extract_text()]
        pdf_text = "\n\n--- PAGE BREAK ---\n\n".join(pages)
        yield _sse({"type": "pdf_preview", "text": pdf_text[:1000]})

        yield _sse({"type": "status", "message": f"Calling {MODEL} for field extraction..."})
        response = await acompletion(
            model=MODEL,
            messages=[
                {"role": "system", "content": _INVOICE_SYSTEM},
                {"role": "user", "content": f"Extract invoice data:\n\n{pdf_text}"},
            ],
            stream=True,
        )

        full_text = ""
        async for chunk in response:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                full_text += delta
                yield _sse({"type": "token", "text": delta})

        yield _sse({"type": "status", "message": "Parsing extracted fields..."})
        data = json.loads(_clean_json(full_text))

        # Deterministic business rule validation
        yield _sse({"type": "status", "message": "Running business rule validation..."})
        flags: list[dict] = []
        if not data.get("po_number"):
            flags.append({"type": "MISSING_PO", "severity": "HIGH",
                          "message": "No PO number found on invoice"})
        total = float(data.get("total", 0))
        if total > 1000:
            flags.append({"type": "AMOUNT_THRESHOLD", "severity": "MEDIUM",
                          "message": f"Invoice total ${total:,.2f} exceeds $1,000 threshold"})
        line_items = data.get("line_items", [])
        line_total = sum(float(i.get("amount", 0)) for i in line_items)
        if line_items and abs(line_total - total) > 0.02:
            flags.append({"type": "LINE_ITEM_MISMATCH", "severity": "HIGH",
                          "message": f"Line items sum ${line_total:,.2f} ≠ invoice total ${total:,.2f}"})

        yield _sse({"type": "status", "message": f"Validation complete — {len(flags)} flag(s) raised"})
        yield _sse({"type": "result", "data": {**data, "flags": flags}})
        yield _sse({"type": "done"})

    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})


@app.get("/api/stream/invoice")
async def stream_invoice(sample: str):
    return StreamingResponse(
        _stream_invoice(sample),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Lead qualifier streaming ──────────────────────────────────────────────────

_LEAD_SYSTEM = """You are a B2B sales qualification expert using the MAN framework (Money, Authority, Need).

Score each dimension 1–10:
MONEY: 1–3 startup/no budget, 4–6 SMB probable budget, 7–9 mid-market clear signals, 10 explicit budget/enterprise urgency
AUTHORITY: 1–3 end-user/no power, 4–6 manager needs approval, 7–9 director can sign off, 10 C-level or "ready to buy"
NEED: 1–3 vague curiosity, 4–6 problem exists not urgent, 7–9 specific pain with urgency, 10 explicit urgency + quantified impact

Return ONLY a raw JSON object (no markdown, no fences):
{
  "money":     {"score": int, "reasoning": "1–2 sentences"},
  "authority": {"score": int, "reasoning": "1–2 sentences"},
  "need":      {"score": int, "reasoning": "1–2 sentences"},
  "recommended_action": "specific next step",
  "suggested_followup": "personalised first-contact message, 2–3 sentences, address by first name"
}"""


def _qualify(total: int) -> tuple[str, str]:
    if total >= 22:
        return "QUALIFIED", "HIGH"
    if total >= 15:
        return "QUALIFIED", "MEDIUM"
    if total >= 8:
        return "UNQUALIFIED", "LOW"
    return "DISQUALIFIED", "LOW"


async def _stream_lead(index: int) -> AsyncGenerator[str, None]:
    leads = json.loads(LEAD_SAMPLES_PATH.read_text())
    if not (0 <= index < len(leads)):
        yield _sse({"type": "error", "message": "Lead index out of range"})
        return

    try:
        lead = leads[index]
        clean = {k: v for k, v in lead.items() if not k.startswith("_")}

        yield _sse({"type": "status", "message": "Loading lead profile..."})
        yield _sse({"type": "input", "data": clean})

        user_msg = (
            f"Name: {lead['name']}\nCompany: {lead['company']}\nRole: {lead['role']}\n"
            f"Company size: {lead.get('company_size', 'unknown')}\nSource: {lead.get('source', 'unknown')}\n\n"
            f"Inquiry:\n{lead['inquiry']}\n\nScore this lead using the MAN framework."
        )

        yield _sse({"type": "status", "message": f"Calling {MODEL} for MAN framework scoring..."})
        response = await acompletion(
            model=MODEL,
            messages=[
                {"role": "system", "content": _LEAD_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            stream=True,
        )

        full_text = ""
        async for chunk in response:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                full_text += delta
                yield _sse({"type": "token", "text": delta})

        yield _sse({"type": "status", "message": "Calculating qualification tier..."})
        data = json.loads(_clean_json(full_text))

        m = int(data["money"]["score"])
        a = int(data["authority"]["score"])
        n = int(data["need"]["score"])
        total = m + a + n
        qualification, priority = _qualify(total)

        yield _sse({"type": "result", "data": {
            "man_score": {"money": data["money"], "authority": data["authority"], "need": data["need"]},
            "total_score": total,
            "max_score": 30,
            "qualification": qualification,
            "priority": priority,
            "recommended_action": data.get("recommended_action", ""),
            "suggested_followup": data.get("suggested_followup", ""),
        }})
        yield _sse({"type": "done"})

    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})


@app.get("/api/stream/lead")
async def stream_lead(index: int = 0):
    return StreamingResponse(
        _stream_lead(index),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Ticket triage streaming ───────────────────────────────────────────────────

_TICKET_SYSTEM = """You are a support ticket triage agent. Classify the ticket and draft a first response.

PRIORITY (top rule wins):
  P1: account access blocked | payment failure | data loss | explicit time constraint | premium customer with any blocker
  P2: feature broken | billing question | non-urgent account issue | integration problem | performance degradation
  P3: feature request | how-to question | documentation | positive feedback | no clear problem

ESCALATION: escalate=true when P1, OR when customer_tier is "premium" AND priority is P2.

CATEGORIES: Authentication | Billing | Data | Performance | Feature Request | Account Management | Integration | Bug Report | General Inquiry

Return ONLY a raw JSON object (no markdown, no fences):
{
  "priority": "P1"|"P2"|"P3",
  "priority_reasoning": "1–2 sentences citing the rule triggered",
  "category": "string from list above",
  "subcategory": "specific sub-topic",
  "escalate": boolean,
  "escalation_reason": "string or null",
  "suggested_response": "empathetic, action-oriented, 2–4 sentences, use [Name] placeholder",
  "confidence": number 0.1–1.0
}"""


async def _stream_ticket(index: int) -> AsyncGenerator[str, None]:
    tickets = json.loads(TICKET_SAMPLES_PATH.read_text())
    if not (0 <= index < len(tickets)):
        yield _sse({"type": "error", "message": "Ticket index out of range"})
        return

    try:
        ticket = tickets[index]
        clean = {k: v for k, v in ticket.items() if not k.startswith("_")}

        yield _sse({"type": "status", "message": "Loading ticket..."})
        yield _sse({"type": "input", "data": clean})

        user_msg = (
            f"Ticket ID: {ticket['ticket_id']}\nCustomer tier: {ticket['customer_tier']}\n"
            f"Submitted at: {ticket.get('submitted_at', 'unknown')}\n\n"
            f"Subject:\n{ticket['subject']}\n\nBody:\n{ticket['body']}\n\nClassify and draft a response."
        )

        yield _sse({"type": "status", "message": f"Calling {MODEL} for triage classification..."})
        response = await acompletion(
            model=MODEL,
            messages=[
                {"role": "system", "content": _TICKET_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            stream=True,
        )

        full_text = ""
        async for chunk in response:
            delta = (chunk.choices[0].delta.content or "") if chunk.choices else ""
            if delta:
                full_text += delta
                yield _sse({"type": "token", "text": delta})

        data = json.loads(_clean_json(full_text))

        # Enforce escalation deterministically — don't rely on LLM alone
        priority = data["priority"]
        is_premium = ticket["customer_tier"] == "premium"
        should_escalate = priority == "P1" or (is_premium and priority == "P2")
        escalation_reason = data.get("escalation_reason")
        if should_escalate and not escalation_reason:
            escalation_reason = "P1 priority" if priority == "P1" else "Premium customer with P2 issue"

        yield _sse({"type": "status", "message": f"Escalation rules enforced — escalate={should_escalate}"})
        yield _sse({"type": "result", "data": {
            "ticket_id": ticket["ticket_id"],
            "priority": priority,
            "priority_reasoning": data.get("priority_reasoning", ""),
            "category": data.get("category", "General Inquiry"),
            "subcategory": data.get("subcategory", ""),
            "escalate": should_escalate,
            "escalation_reason": escalation_reason if should_escalate else None,
            "suggested_response": data.get("suggested_response", ""),
            "confidence": float(data.get("confidence", 0.85)),
        }})
        yield _sse({"type": "done"})

    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})


@app.get("/api/stream/ticket")
async def stream_ticket(index: int = 0):
    return StreamingResponse(
        _stream_ticket(index),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Serve the UI ──────────────────────────────────────────────────────────────

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
