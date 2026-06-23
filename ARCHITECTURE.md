# NBA PEO-Mission Mapping Engine — Architecture & Workflow

This document provides a detailed, step-by-step technical explanation of how the NBA PEO-Mission Mapping Engine operates, including the multi-agent orchestration pipeline.

## 🏗 High-Level Architecture

The system is built as a highly decoupled, AI-driven web application consisting of three main layers:

1. **Frontend UI (`templates/index.html`)**: A modern, responsive web interface that allows users to upload their Self-Assessment Report (SAR), select their preferred LLM provider, and monitor the pipeline's progress in real-time via Server-Sent Events (SSE).
2. **Flask Backend (`app.py` & `orchestrator.py`)**: A Python-based REST API that acts as the control plane. It streams execution logs back to the frontend and orchestrates the agentic workflow.
3. **Multi-Agent Pipeline**: A sequence of four specialised agents (3 LLM-driven, 1 deterministic) that sequentially process the accreditation data using a RAG (Retrieval-Augmented Generation) pattern.

---

## 🤖 Step-by-Step Agent Workflow

When a user initiates a run, `orchestrator.py` fires up the pipeline. Here is exactly what happens under the hood:

### Step 0: Document Ingestion & RAG Indexing (`services/document_ingestor.py`)
- The user's SAR document (PDF/Word) is uploaded.
- The **Document Ingestor** extracts the raw text and specifically hunts for the "Program Educational Objectives" (PEOs) and "Department Missions" (DMs) using heuristic parsing.
- The entire document text is chunked and embedded into a local vector database using `all-MiniLM-L6-v2`. This allows the downstream agents to perform RAG (Retrieval-Augmented Generation), querying the specific language and context of the institution's own document.

### Step 1: Agent 1 - PEO Deconstructor (`agents/agent1_peo_deconstructor.py`)
- **Input**: Raw text strings of the extracted PEOs.
- **RAG Context**: Retrieves relevant document context about the program's objectives.
- **Task**: The LLM is instructed to act as an Outcome-Based Education (OBE) expert. It breaks down each PEO into 7 atomic competency components (e.g., *core_technical_skills*, *lifelong_learning*, *professional_skills*).
- **Output**: A strict JSON object containing the enriched, multi-dimensional breakdown of each PEO.

### Step 2: Agent 2 - Mission Deconstructor (`agents/agent2_mission_deconstructor.py`)
- **Input**: Raw text strings of the Department Missions.
- **RAG Context**: Retrieves relevant institutional mission context.
- **Task**: Similar to Agent 1, it deconstructs the Mission statements into 8 specific objective categories (e.g., *industry_readiness*, *societal_impact*, *research_ecosystem*).
- **Output**: A strict JSON object containing the enriched breakdown of each Mission.

### Step 3: Agent 3 - Correlation Scorer (`agents/agent3_correlation_scorer.py`)
- **Input**: The enriched PEOs (from Agent 1) and enriched Missions (from Agent 2).
- **RAG Context**: Retrieves specific NBA accreditation scoring rubrics and contextual definitions.
- **Task**: This is the core cognitive engine. The LLM performs a semantic cross-referencing of every PEO against every DM. It uses the strict NBA rubric to assign a correlation score (`3` = Substantial, `2` = Moderate, `1` = Slight, `-` = None). For every mapped pair, it must also generate a pedagogical justification explaining *why* the PEO structurally supports the mission.
- **Output**: A complex JSON schema containing the `matrix` scores and a `justifications` dictionary.

### Step 4: Agent 4 - Report Formatter (`agents/agent4_report_formatter.py`)
- **Input**: The raw JSON matrix and justifications from Agent 3.
- **Task**: This is a **deterministic (non-LLM)** agent. It does not call an AI model. Instead, it uses standard Python logic to safely parse the scoring output, calculate mathematical averages for each PEO, sort the justifications, and generate summary statistics.
- **Output**: It generates the final, NBA-compliant Markdown report and a structured dictionary that is sent back to the frontend for UI rendering.

---

## 🔀 The LLM Router (`services/llm_router.py`)

A critical component of this system is the **LLM Router**. Instead of hardcoding API calls inside the agents, all agents import a single `call_llm()` function. 

Based on the frontend dropdown selection, the router dynamically forwards the request to:
1. **Groq (`_call_groq`)**: Uses `llama-3.1-70b-versatile` for ultra-fast inference.
2. **OpenAI (`_call_openai`)**: Uses `gpt-4o` for high-reasoning tasks.
3. **Google Gemini (`_call_gemini`)**: Uses `gemini-1.5-flash` with strict JSON-mode enforcement (`response_mime_type="application/json"`).

The router automatically handles rate-limiting, quota errors, and implements an exponential backoff retry mechanism (sleeping and retrying up to 3 times) to ensure pipeline resilience against transient network or API failures.

---

## 🔌 Dual Server Architecture

The application can be run via the `run.bat` script, which spins up two simultaneous servers:
1. **Flask Web Server** (Port 5000): Serves the human-facing UI and coordinates the AI pipeline.
2. **FastMCP Server** (Port 8080): Runs the Model Context Protocol (MCP) server. This allows external AI IDEs (like Cursor or Windsurf) or other MCP-compliant clients to connect to this engine programmatically, treating the local pipeline as an executable tool. Both servers can be gracefully terminated via the frontend UI's "Terminate Servers" button, which triggers the `/api/shutdown` endpoint.
