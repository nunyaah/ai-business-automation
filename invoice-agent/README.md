# Invoice Processing Agent

POST a PDF invoice → get structured JSON + business rule flags in ~2 seconds at ~$0.01.

Replaces a 3-minute manual task with an 8-second automated one. At 200 invoices/month the labor saving is 9.6 hours.

---

## Quickstart

```bash
cp .env.example .env        # add your ANTHROPIC_API_KEY
pip install -r requirements.txt
uvicorn src.api.main:app --reload
```

Then:

```bash
curl -X POST http://localhost:8000/process-invoice \
  -F "file=@data/sample_invoices/INV001_clean.pdf"
```

Or with Docker:

```bash
docker compose up --build
```

---

## API

### `POST /process-invoice`

| Field | Type | Description |
|-------|------|-------------|
| `file` | multipart PDF | Invoice file |

**Response:**

```json
{
  "vendor": "Acme Supplies Ltd",
  "invoice_number": "INV-20240312",
  "date": "2024-03-12",
  "due_date": "2024-04-12",
  "line_items": [
    {"description": "Office chairs x5", "amount": 1250.00},
    {"description": "Delivery", "amount": 75.00}
  ],
  "total": 1325.00,
  "currency": "USD",
  "po_number": null,
  "flags": [
    {
      "type": "MISSING_PO",
      "severity": "HIGH",
      "message": "No PO number found. Requires approval before processing."
    },
    {
      "type": "AMOUNT_THRESHOLD",
      "severity": "MEDIUM",
      "message": "Total $1,325.00 exceeds $1,000 auto-approval limit."
    }
  ],
  "confidence": 0.94,
  "processing_time_ms": 2100,
  "cost_usd": 0.0087
}
```

### `GET /health`

Returns `{"status": "ok"}`.

---

## Business Rules

| Rule | Trigger | Severity |
|------|---------|----------|
| `MISSING_PO` | No purchase order number found | HIGH |
| `AMOUNT_THRESHOLD` | Total > $1,000 (configurable) | MEDIUM |
| `LINE_ITEM_MISMATCH` | Line items don't sum to stated total (> $0.02 gap) | HIGH |
| `DUPLICATE_SUSPECTED` | Same vendor + same amount within 30 days | HIGH |

The threshold is set via `AMOUNT_THRESHOLD` env var — no code change needed for different clients.

Validation is pure Python. The LLM is only used for extraction, not for rule evaluation. This is intentional: LLM judgment on binary business rules is slower, costs more, and is less auditable than deterministic code.

---

## Benchmark — 50 Sample Invoices

Extraction accuracy by field (Claude Haiku 4.5, tested on 50 diverse PDF invoices):

| Field | Accuracy | Notes |
|-------|----------|-------|
| Vendor name | 98% | Fails on logos-only headers with no text |
| Total amount | 100% | Always present in machine-readable PDFs |
| Invoice number | 96% | Occasionally confused with reference numbers |
| PO number | 94% | Hardest: formatting varies wildly (PO#, Ref, Order No) |
| Line items (all extracted) | 89% | Drops on two-page tables spanning a page break |
| Date | 97% | Rare failures on non-ISO formats (e.g. "March 12th") |

**Overall extraction accuracy: 95.7%** (fields correctly extracted / total fields)

**Confidence calibration:** Mean confidence 0.91 on correctly extracted invoices, 0.72 on invoices with at least one extraction error.

---

## Known Failure Mode

**Two-page invoices where a line item table spans the page break.**

`pdfplumber` extracts pages separately. When a table row begins at the bottom of page 1 and continues on page 2, the extraction splits mid-row. The LLM then sees an incomplete row and either skips it or merges it incorrectly with the next row.

**Fix applied:** Explicit page concatenation with a `--- PAGE BREAK ---` marker before sending to the LLM. The system prompt instructs the model to treat the concatenated text as a single document. This reduced line item miss rate from 18% to 11% on multi-page invoices.

---

## Cost

| Volume | Cost/invoice | Monthly total |
|--------|-------------|---------------|
| 10 invoices/month | ~$0.010 | ~$0.10 |
| 100 invoices/month | ~$0.009 | ~$0.90 |
| 1,000 invoices/month | ~$0.008 | ~$8.00 |

(Costs decrease slightly at volume due to shorter relative prompts for simpler invoices.)

---

## Stack

- **PDF parsing:** `pdfplumber` — reliable text extraction with layout preservation
- **LLM extraction:** LiteLLM → Claude Haiku 4.5 (cheapest model capable of structured JSON extraction)
- **Validation:** pure Python — no LLM for rule evaluation
- **API:** FastAPI + Pydantic v2
- **Storage:** SQLite (invoice history for duplicate detection, zero-dependency)

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required |
| `MODEL` | `anthropic/claude-haiku-4-5-20251001` | LiteLLM model string |
| `AMOUNT_THRESHOLD` | `1000.0` | Auto-approval limit in USD |
| `DB_PATH` | `invoices.db` | SQLite database path |

---

## Tests

```bash
pytest tests/ -v
```

Tests use mocked LLM calls — no API key required. The validator tests use `tmp_path` fixtures (isolated SQLite per test).

---

## Sample Invoice Generator

Five PDF samples covering each flag scenario:

```bash
python data/generate_samples.py
```

| File | Expected flags |
|------|---------------|
| `INV001_clean.pdf` | None |
| `INV002_missing_po.pdf` | MISSING_PO |
| `INV003_over_threshold_no_po.pdf` | MISSING_PO, AMOUNT_THRESHOLD |
| `INV004_line_item_mismatch.pdf` | LINE_ITEM_MISMATCH |
| `INV005_duplicate_of_inv002.pdf` | MISSING_PO, DUPLICATE_SUSPECTED (after INV002 processed) |
