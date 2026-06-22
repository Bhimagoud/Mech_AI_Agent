# NBA PEO–Mission Mapping Engine

**AI-powered multi-agent pipeline for NBA SAR Criterion 1 analysis.**

Automates the PEO ↔ Department Mission correlation matrix and pedagogical justification generation aligned with the Washington Accord / NBA UG Tier-I Manual rubric.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface                           │
│         index.html  (File upload OR manual entry)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP POST
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Flask REST API  (app.py)                   │
│   POST /api/analyze        – file upload                        │
│   POST /api/analyze/manual – JSON PEOs & DMs                   │
│   GET  /api/health                                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Orchestrator  (orchestrator.py)             │
│                                                                 │
│  Step 0 ──► Document Ingestor Service                          │
│             (services/document_ingestor.py)                     │
│             Extracts PEOs & DMs from PDF/DOCX via pdfplumber   │
│             or python-docx                                      │
│                                                                 │
│  Step 1 ──► Agent 1: PEO Deconstructor                         │
│             (agents/agent1_peo_deconstructor.py)               │
│             LLM call → JSON breakdown of each PEO into         │
│             7 competency dimensions                             │
│                                                                 │
│  Step 2 ──► Agent 2: Mission Deconstructor                     │
│             (agents/agent2_mission_deconstructor.py)           │
│             LLM call → JSON breakdown of each DM into          │
│             8 objective dimensions                              │
│                                                                 │
│  Step 3 ──► Agent 3: Correlation Scorer                        │
│             (agents/agent3_correlation_scorer.py)              │
│             LLM call (full rubric prompt) → matrix scores 1–3  │
│             + 2-sentence pedagogical justifications             │
│                                                                 │
│  Step 4 ──► Agent 4: Report Formatter                          │
│             (agents/agent4_report_formatter.py)                │
│             Deterministic → matrix table, averages, Markdown   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
                  JSON response → Frontend
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your API key

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 3a. Start the web server

```bash
python app.py
# Open http://localhost:5000
```

### 3b. Or run the CLI (no browser needed)

```bash
# Use built-in sample data
python run_cli.py --sample

# Use your own SAR document
python run_cli.py --sar path/to/SAR.docx

# With NBA manual
python run_cli.py --sar path/to/SAR.pdf --manual path/to/NBA_Manual.pdf
```

---

## API Reference

### `POST /api/analyze`
Upload SAR document for automatic PEO/DM extraction + scoring.

**Request:** `multipart/form-data`
- `sar_file` (required): PDF or DOCX
- `manual_file` (optional): NBA manual PDF

**Response:**
```json
{
  "status": "success",
  "peos": [{"id": "PEO1", "text": "..."}],
  "missions": [{"id": "DM1", "text": "..."}],
  "report": {
    "matrix_table": [...],
    "averages": {"PEO1": 2.33},
    "justifications": [...],
    "summary_stats": {...},
    "markdown": "# NBA SAR..."
  },
  "peo_breakdown": {...},
  "mission_breakdown": {...}
}
```

### `POST /api/analyze/manual`
Provide PEOs and DMs directly as JSON.

**Request body:**
```json
{
  "peos": [{"id": "PEO1", "text": "..."}],
  "missions": [{"id": "DM1", "text": "..."}]
}
```

### `POST /api/extract`
Extract PEOs and DMs from a document without scoring.

---

## Scoring Rubric (NBA UG Tier-I Manual)

| Score | Level | Description |
|-------|-------|-------------|
| **3** | Substantial/High | Direct semantic overlap; PEO explicitly fulfils core mission element |
| **2** | Moderate/Medium | Indirect/partial support; secondary rather than primary alignment |
| **1** | Slight/Low | Tangential; foundational knowledge marginally assists mission |
| **–** | No Correlation | Concepts entirely unrelated |

---

## File Structure

```
nba_mapper/
├── app.py                          # Flask REST API
├── orchestrator.py                 # Multi-agent pipeline coordinator
├── run_cli.py                      # CLI runner
├── requirements.txt
├── .env.example
├── agents/
│   ├── agent1_peo_deconstructor.py
│   ├── agent2_mission_deconstructor.py
│   ├── agent3_correlation_scorer.py
│   └── agent4_report_formatter.py  # Deterministic (no LLM)
├── services/
│   ├── document_ingestor.py        # PDF/DOCX parser
│   └── llm_client.py               # Anthropic API wrapper
└── templates/
    └── index.html                  # Single-page frontend
```
