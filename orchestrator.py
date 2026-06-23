"""
Orchestrator: NBA PEO–Mission Mapping Pipeline
-----------------------------------------------
Coordinates the 4-agent pipeline:

  Document Ingestor  →  Agent 1 (PEO Deconstructor)
                     →  Agent 2 (Mission Deconstructor)
                     →  Agent 3 (Correlation Scorer)
                     →  Agent 4 (Report Formatter)
                     →  Final report dict

Usage:
    from orchestrator import run_pipeline
    result = run_pipeline(
        sar_bytes=..., sar_filename="SAR.docx",
        manual_bytes=..., manual_filename="NBA_Manual.pdf"
    )
"""

import logging
import traceback

from services.document_ingestor import ingest_document, build_context_from_manual
from services import rag_service
from agents.agent1_peo_deconstructor import deconstruct_peos
from agents.agent2_mission_deconstructor import deconstruct_missions
from agents.agent3_correlation_scorer import score_correlations
from agents.agent4_report_formatter import format_report

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline_stream(
    sar_bytes: bytes,
    sar_filename: str,
    manual_bytes: bytes = None,
    manual_filename: str = "",
    extra_peos: list = None,
    extra_missions: list = None,
):
    """
    Run the full 4-agent NBA mapping pipeline as a generator yielding progress.
    """
    result = {
        "status": "error",
        "error": None,
        "peos": [],
        "missions": [],
        "peo_breakdown": {},
        "mission_breakdown": {},
        "scoring_output": {},
        "report": {},
    }

    try:
        # ------------------------------------------------------------------ #
        # Step 0 – Ingest documents
        # ------------------------------------------------------------------ #
        yield {"type": "progress", "step": "ingest", "message": f"Extracting text content from SAR document '{sar_filename}'...", "percentage": 10, "log_type": "system"}
        logger.info("[Pipeline] Step 0: Ingesting SAR document '%s'", sar_filename)
        sar_data = ingest_document(sar_bytes, sar_filename)

        # Ingest and index the full text into RAG service
        yield {"type": "progress", "step": "ingest", "message": "RAG: Initializing local MiniLM model embedding pipeline...", "percentage": 18, "log_type": "info"}
        rag_service.clear()
        if "full_text" in sar_data and sar_data["full_text"]:
            rag_service.ingest_and_index(sar_data["full_text"], source=sar_filename)
        
        # Allow caller to override extracted PEOs / missions
        peos = extra_peos if extra_peos else sar_data.get("peos", [])
        missions = extra_missions if extra_missions else sar_data.get("missions", [])

        yield {"type": "progress", "step": "ingest", "message": f"RAG: Document chunks indexed. Extracted {len(peos)} PEOs and {len(missions)} DMs.", "percentage": 25, "log_type": "info"}

        if not peos:
            err = "No PEOs could be extracted from the document. Please verify the file contains PEO statements or provide them manually."
            yield {"type": "error", "error": err}
            return

        if not missions:
            err = "No Department Mission statements could be extracted. Please verify the file or provide them manually."
            yield {"type": "error", "error": err}
            return

        result["peos"] = peos
        result["missions"] = missions

        logger.info(
            "[Pipeline] Extracted %d PEOs and %d DMs", len(peos), len(missions)
        )

        # ------------------------------------------------------------------ #
        # Step 1 – PEO Deconstruction (Agent 1)
        # ------------------------------------------------------------------ #
        yield {"type": "progress", "step": "a1", "message": "Agent 1 (PEO Deconstructor) activated. Processing PEOs...", "percentage": 30, "log_type": "agent1"}
        logger.info("[Pipeline] Step 1: PEO Deconstruction (Agent 1)")
        yield {"type": "progress", "step": "a1", "message": f"Agent 1: Injecting RAG context & deconstructing {len(peos)} PEOs via Groq LLM...", "percentage": 35, "log_type": "agent1"}
        peo_breakdown = deconstruct_peos(peos)
        result["peo_breakdown"] = peo_breakdown
        yield {"type": "progress", "step": "a1", "message": f"Agent 1: Deconstruction complete for PEOs: {list(peo_breakdown.keys())}", "percentage": 50, "log_type": "agent1"}

        import time
        time.sleep(2)  # Avoid burst rate limits on free-tier APIs

        # ------------------------------------------------------------------ #
        # Step 2 – Mission Deconstruction (Agent 2)
        # ------------------------------------------------------------------ #
        yield {"type": "progress", "step": "a2", "message": "Agent 2 (Mission Deconstructor) activated. Processing Missions...", "percentage": 55, "log_type": "agent2"}
        logger.info("[Pipeline] Step 2: Mission Deconstruction (Agent 2)")
        yield {"type": "progress", "step": "a2", "message": f"Agent 2: Deconstructing {len(missions)} Mission Statements...", "percentage": 60, "log_type": "agent2"}
        mission_breakdown = deconstruct_missions(missions)
        result["mission_breakdown"] = mission_breakdown
        yield {"type": "progress", "step": "a2", "message": f"Agent 2: Deconstruction complete for Missions: {list(mission_breakdown.keys())}", "percentage": 70, "log_type": "agent2"}

        time.sleep(2)  # Avoid burst rate limits on free-tier APIs

        # ------------------------------------------------------------------ #
        # Step 3 – Correlation Scoring (Agent 3)
        # ------------------------------------------------------------------ #
        yield {"type": "progress", "step": "a3", "message": "Agent 3 (Correlation Scorer) activated. Calculating mapping...", "percentage": 75, "log_type": "agent3"}
        logger.info("[Pipeline] Step 3: Correlation Scoring (Agent 3)")
        yield {"type": "progress", "step": "a3", "message": f"Agent 3: Scoring {len(peos)} x {len(missions)} PEO-Mission pairs against NBA rubrics...", "percentage": 80, "log_type": "agent3"}
        scoring_output = score_correlations(
            peos=peos,
            missions=missions,
            peo_breakdown=peo_breakdown,
            mission_breakdown=mission_breakdown,
        )
        result["scoring_output"] = scoring_output
        yield {"type": "progress", "step": "a3", "message": f"Agent 3: Scored {len(scoring_output.get('justifications', []))} pairs successfully.", "percentage": 90, "log_type": "agent3"}

        # ------------------------------------------------------------------ #
        # Step 4 – Report Formatting (Agent 4)
        # ------------------------------------------------------------------ #
        yield {"type": "progress", "step": "a4", "message": "Agent 4 (Report Formatter) activated. Generating report...", "percentage": 92, "log_type": "agent4"}
        logger.info("[Pipeline] Step 4: Report Formatting (Agent 4)")
        yield {"type": "progress", "step": "a4", "message": "Agent 4: Compiling markdown tables and final matrix...", "percentage": 95, "log_type": "agent4"}
        report = format_report(
            peos=peos,
            missions=missions,
            scoring_output=scoring_output,
            source_file=sar_filename,
        )
        result["report"] = report
        yield {"type": "progress", "step": "a4", "message": "Agent 4: Report generation complete.", "percentage": 98, "log_type": "agent4"}

        result["status"] = "success"
        yield {"type": "progress", "step": "a4", "message": "Pipeline completed successfully.", "percentage": 100, "log_type": "success"}
        yield {"type": "complete", "result": result}

    except Exception as exc:
        logger.error("[Pipeline] Fatal error: %s\n%s", exc, traceback.format_exc())
        yield {"type": "error", "error": str(exc)}


def run_pipeline(
    sar_bytes: bytes,
    sar_filename: str,
    manual_bytes: bytes = None,
    manual_filename: str = "",
    extra_peos: list = None,
    extra_missions: list = None,
) -> dict:
    """
    Run the full 4-agent NBA mapping pipeline synchronously.
    """
    generator = run_pipeline_stream(
        sar_bytes=sar_bytes,
        sar_filename=sar_filename,
        manual_bytes=manual_bytes,
        manual_filename=manual_filename,
        extra_peos=extra_peos,
        extra_missions=extra_missions,
    )
    final_result = None
    for item in generator:
        if item.get("type") == "complete":
            final_result = item.get("result")
        elif item.get("type") == "error":
            return {"status": "error", "error": item.get("error")}

    if final_result:
        return final_result
    return {"status": "error", "error": "Pipeline did not return a final result."}
