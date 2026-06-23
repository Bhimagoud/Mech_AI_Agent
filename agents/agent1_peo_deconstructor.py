"""
Agent 1: PEO Deconstructor
--------------------------
Responsibility:
  Accept a list of raw PEO texts and return a structured JSON object
  that maps each PEO ID to its deconstructed competency components
  (technical skills, soft skills, research, ethics, lifelong learning, etc.).

RAG-enhanced: Retrieves relevant chunks from the indexed SAR document
to provide richer document context alongside the raw PEO texts.

This output feeds Agent 3 (Correlation Scorer) so it can perform
semantic cross-referencing with enriched representations instead of raw text.
"""

import json
import logging
import re

from services.llm_router import call_llm
from services.rag_service import retrieve_as_context, is_indexed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are an expert Outcome-Based Education (OBE) analyst specialising in
engineering accreditation under the Washington Accord (NBA / ABET).

Your SOLE task is to deconstruct Program Educational Objectives (PEOs) into
their atomic competency components.  For each PEO, identify:

1. core_technical_skills  – specific engineering/science knowledge domains
2. applied_skills         – design, analysis, problem-solving, computation
3. professional_skills    – communication, teamwork, leadership, management
4. ethical_social         – ethics, responsibility, sustainability, society
5. research_innovation    – R&D, innovation, multidisciplinary inquiry
6. lifelong_learning      – adaptability, continuous education, upskilling
7. industry_readiness     – employability, industry context, real-world application

Return ONLY a valid JSON object.  Schema:
{
  "PEO1": {
    "core_technical_skills": ["..."],
    "applied_skills": ["..."],
    "professional_skills": ["..."],
    "ethical_social": ["..."],
    "research_innovation": ["..."],
    "lifelong_learning": ["..."],
    "industry_readiness": ["..."],
    "summary": "One-sentence summary of the PEO's primary thrust."
  },
  ...
}

Rules:
- Use exact PEO IDs as keys (e.g., "PEO1", "PEO2").
- Each list may be empty [] if that dimension is not present.
- Do NOT include explanation prose outside the JSON object.
- Do NOT wrap output in markdown fences.
""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deconstruct_peos(peos: list) -> dict:
    """
    Args:
        peos: List of {"id": "PEO1", "text": "..."} dicts.

    Returns:
        dict mapping PEO ID → competency breakdown (parsed from LLM JSON).
    """
    if not peos:
        return {}

    peo_block = "\n\n".join(
        f"{p['id']}: {p['text']}" for p in peos
    )

    # ── RAG context injection ──────────────────────────────────────────────
    rag_context = ""
    if is_indexed():
        rag_context = retrieve_as_context(
            query="Program Educational Objectives PEO competency skills",
            header="## SAR Document Context (retrieved via RAG)",
        )
        logger.info("Agent 1: RAG context injected (%d chars)", len(rag_context))

    user_message = f"""\
{rag_context + chr(10) if rag_context else ""}\
Deconstruct the following Program Educational Objectives:

{peo_block}

Return the JSON object as described in your instructions.
""".strip()

    logger.info("Agent 1 (PEO Deconstructor): Processing %d PEOs", len(peos))
    raw_response = call_llm(_SYSTEM_PROMPT, user_message, temperature=0.0)
    result = _parse_json_response(raw_response, context="PEO deconstruction")

    logger.info("Agent 1: Deconstruction complete for keys: %s", list(result.keys()))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str, context: str = "") -> dict:
    """
    Safely parse a JSON object from the LLM response.
    Handles minor formatting issues (stray fences, trailing commas).
    """
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
        cleaned = text[start_idx:end_idx+1]
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in %s: %s\nRaw text:\n%s", context, exc, text[:500])
            return {}
    else:
        logger.error("No JSON braces found in %s response.\nRaw:\n%s", context, text[:500])
        return {}
