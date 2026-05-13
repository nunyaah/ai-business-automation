# AI Business Automation

**Stop paying humans to do what AI can do in under a second.**

This repo contains three production-ready AI agents that automate high-volume, repetitive business operations — invoice processing, sales lead qualification, and support ticket triage. Each agent is a FastAPI service you can drop into your stack today.

---

## The Agents

### Invoice Processing Agent
*From PDF to structured data in 8 seconds. No humans required.*

Your finance team shouldn't be manually keying invoice data. The Invoice Agent reads PDF invoices, extracts every field that matters — vendor, amounts, line items, PO numbers, dates — and runs deterministic business rule validation to flag duplicates, missing POs, and threshold breaches before anything hits your AP system.

- **95.7% extraction accuracy** across diverse invoice formats
- **~$0.01 per invoice** — 200 invoices a month costs less than a coffee
- Replaces a 3-minute manual task with an 8-second automated one: **9.6 hours/month back to your team**

---

### Lead Qualifier Agent
*Score every inbound lead in 650ms. Close the ones that matter.*

Sales reps shouldn't be spending 12 minutes qualifying leads that were never going to buy. The Lead Qualifier scores every lead against the MAN framework (Money, Authority, Need) and outputs a qualification tier plus a personalised follow-up message — ready to send.

- **87% agreement with human qualification decisions**, 91% precision on qualified leads
- **$0/month processing cost** on the Groq free tier
- 200 leads/month = **40 hours of sales time reclaimed**

---

### Ticket Triage Agent
*P1 tickets escalated before your agent finishes their coffee.*

Support queues are chaos without prioritisation. The Ticket Triage Agent classifies every incoming ticket by priority (P1/P2/P3), assigns a category, decides whether to escalate, and drafts an empathetic first response — all before a human eyes it.

- **94% P1 precision, 96% P1 recall** — critical issues almost never slip through
- Deterministic escalation rules in Python mean P1 tickets *always* escalate, no hallucinations
- 1,000 tickets/month with 3 agents = **$1,650/month in labour reclaimed**

---

## Architecture

All three agents follow the same pattern: LLM for judgment (extraction, scoring, classification), deterministic Python for binary business rules (escalation, validation, thresholds). This separation is intentional — you don't want an LLM deciding whether a P1 ticket gets escalated.

| Agent | Model | Port | Cost |
|---|---|---|---|
| Invoice | Claude Haiku 4.5 | 8000 | ~$0.01/invoice |
| Lead Qualifier | Groq llama-3.3-70b | 8001 | Free tier |
| Ticket Triage | Groq llama-3.3-70b | 8002 | Free tier |

Each agent ships with a FastAPI REST interface, Pydantic v2 validation, SQLite logging, Docker support, and a test suite that runs without API keys.

---

## Get Started

```bash
# Run any agent
cd invoice-agent   # or lead-qualifier / ticket-triage
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Each agent folder contains its own README with endpoint docs, example payloads, and deployment notes.
