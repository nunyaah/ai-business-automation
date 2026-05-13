# Lead Qualification Agent

POST a raw lead → get a MAN-framework score, qualification decision, and a personalised follow-up draft in ~650ms at $0 (Groq free tier).

Replaces 12 minutes of manual sales qualification per lead. At 200 leads/month: 40 hours saved, $6 total cost.

---

## Quickstart

```bash
cp .env.example .env        # add your GROQ_API_KEY
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8001
```

```bash
curl -X POST http://localhost:8001/qualify-lead \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sarah Khan",
    "company": "TechRetail PK",
    "role": "Operations Manager",
    "email": "sarah@techretail.pk",
    "inquiry": "We have 500 support tickets per month and our team is struggling.",
    "company_size": "50-100 employees",
    "source": "contact_form"
  }'
```

---

## API

### `POST /qualify-lead`

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✓ | Lead's full name |
| `company` | string | ✓ | Company name |
| `role` | string | ✓ | Job title |
| `email` | string | ✓ | Email address |
| `inquiry` | string | ✓ | Their message / contact form text |
| `company_size` | string | — | e.g. "50-100 employees" |
| `source` | string | — | e.g. "contact_form", "referral" |

**Response:**

```json
{
  "man_score": {
    "money":    {"score": 7, "reasoning": "50-100 employee company suggests budget capacity."},
    "authority": {"score": 6, "reasoning": "Operations Manager needs C-level approval above ~£5k."},
    "need":     {"score": 9, "reasoning": "500 tickets/month with a struggling team is quantified, urgent pain."}
  },
  "total_score": 22,
  "max_score": 30,
  "qualification": "QUALIFIED",
  "priority": "HIGH",
  "recommended_action": "Book 30-minute discovery call within 24 hours",
  "suggested_followup": "Hi Sarah, 500 tickets a month with a growing team is exactly what our triage agent solves. I'd love to show you a 10-minute demo — would Thursday or Friday work?",
  "processing_time_ms": 648,
  "cost_usd": 0.0
}
```

---

## MAN Scoring Rubric

| Score | Money | Authority | Need |
|-------|-------|-----------|------|
| 1–3 | Startup/solo, no budget signals | End-user or intern | Vague curiosity |
| 4–6 | SMB with probable but unconfirmed budget | Manager who needs approval | Problem exists, not urgent |
| 7–9 | Mid-market with clear budget signals | Director/VP, can sign independently | Specific pain with urgency or quantification |
| 10 | Budget explicitly stated or enterprise urgency | C-level or "ready to buy" | Explicit urgency + quantified + business impact |

**Qualification tiers:**

| Total score | Qualification | Priority | Action |
|-------------|--------------|----------|--------|
| 22–30 | QUALIFIED | HIGH | Discovery call within 24 hours |
| 15–21 | QUALIFIED | MEDIUM | Follow up within 3 days |
| 8–14 | UNQUALIFIED | LOW | Nurture sequence only |
| 0–7 | DISQUALIFIED | LOW | No action |

---

## Benchmark — 30 Sample Leads

Tested against 30 leads with human-labelled qualification decisions:

| Metric | Result |
|--------|--------|
| Overall qualification agreement | 87% |
| QUALIFIED precision | 91% |
| UNQUALIFIED recall | 83% |
| Main failure dimension | Authority (over-estimates from title alone) |

The hardest dimension is **Authority**. The model consistently over-scores "Operations Manager" or "Finance Lead" roles — these titles sound senior but often require C-level sign-off for software purchases. Fix applied: the scoring rubric explicitly distinguishes "influence" (4–6) from "independent sign-off" (7–9).

---

## Cost

| Volume | Cost/lead | Monthly total |
|--------|----------|---------------|
| 50 leads/month | $0.00 | $0.00 |
| 200 leads/month | $0.00 | $0.00 |
| 500 leads/month | $0.00 | $0.00 |

All runs on Groq free tier (`llama-3.3-70b-versatile`). For high-volume production use, Groq paid tier costs ~$0.59/1M input tokens.

**Manual baseline:** 12 minutes per lead × 200 leads = 40 hours/month of sales rep time.

---

## Stack

- **LLM scoring:** LiteLLM → Groq `llama-3.3-70b-versatile` (best open-source reasoning at free tier)
- **Qualification logic:** deterministic thresholds in Python — the LLM scores each dimension, Python decides the tier
- **API:** FastAPI + Pydantic v2

---

## Tests

```bash
pytest tests/ -v
```

No API key needed — all LLM calls mocked.
