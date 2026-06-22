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

def run_pipeline(
    sar_bytes: bytes,
    sar_filename: str,
    manual_bytes: bytes = None,
    manual_filename: str = "",
    extra_peos: list = None,
    extra_missions: list = None,
) -> dict:
    """
    Run the full 4-agent NBA mapping pipeline.

    Args:
        sar_bytes:        Raw bytes of the SAR document (PDF or DOCX).
        sar_filename:     Original filename (used for format detection).
        manual_bytes:     Optional NBA manual PDF bytes for rubric context.
        manual_filename:  Manual filename.
        extra_peos:       Optional manual PEO overrides [{"id":"PEO1","text":"..."}].
        extra_missions:   Optional manual DM overrides  [{"id":"DM1","text":"..."}].

    Returns:
        {
            "status": "success" | "error",
            "error":  str | None,
            "peos":   [...],
            "missions": [...],
            "peo_breakdown": {...},
            "mission_breakdown": {...},
            "scoring_output": {...},
            "report": {...}       ← the final formatted report
        }
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
        logger.info("[Pipeline] Step 0: Ingesting SAR document '%s'", sar_filename)
        sar_data = ingest_document(sar_bytes, sar_filename)

        # Ingest and index the full text into RAG service
        rag_service.clear()
        if "full_text" in sar_data and sar_data["full_text"]:
            rag_service.ingest_and_index(sar_data["full_text"], source=sar_filename)

        # Allow caller to override extracted PEOs / missions
        peos = extra_peos if extra_peos else sar_data["peos"]
        missions = extra_missions if extra_missions else sar_data["missions"]

        if not peos:
            result["error"] = (
                "No PEOs could be extracted from the document. "
                "Please verify the file contains PEO statements or provide them manually."
            )
            return result

        if not missions:
            result["error"] = (
                "No Department Mission statements could be extracted. "
                "Please verify the file or provide them manually."
            )
            return result

        result["peos"] = peos
        result["missions"] = missions

        logger.info(
            "[Pipeline] Extracted %d PEOs and %d DMs", len(peos), len(missions)
        )

        # ------------------------------------------------------------------ #
        # Step 1 – PEO Deconstruction (Agent 1)
        # ------------------------------------------------------------------ #
        logger.info("[Pipeline] Step 1: PEO Deconstruction (Agent 1)")
        peo_breakdown = deconstruct_peos(peos)
        result["peo_breakdown"] = peo_breakdown

        # ------------------------------------------------------------------ #
        # Step 2 – Mission Deconstruction (Agent 2)
        # ------------------------------------------------------------------ #
        logger.info("[Pipeline] Step 2: Mission Deconstruction (Agent 2)")
        mission_breakdown = deconstruct_missions(missions)
        result["mission_breakdown"] = mission_breakdown

        # ------------------------------------------------------------------ #
        # Step 3 – Correlation Scoring (Agent 3)
        # ------------------------------------------------------------------ #
        logger.info("[Pipeline] Step 3: Correlation Scoring (Agent 3)")
        scoring_output = score_correlations(
            peos=peos,
            missions=missions,
            peo_breakdown=peo_breakdown,
            mission_breakdown=mission_breakdown,
        )
        result["scoring_output"] = scoring_output

        # ------------------------------------------------------------------ #
        # Step 4 – Report Formatting (Agent 4)
        # ------------------------------------------------------------------ #
        logger.info("[Pipeline] Step 4: Report Formatting (Agent 4)")
        report = format_report(
            peos=peos,
            missions=missions,
            scoring_output=scoring_output,
            source_file=sar_filename,
        )
        result["report"] = report

        result["status"] = "success"
        logger.info("[Pipeline] Completed successfully.")

    except Exception as exc:
        logger.error("[Pipeline] Fatal error: %s\n%s", exc, traceback.format_exc())
        result["error"] = str(exc)

    return result
