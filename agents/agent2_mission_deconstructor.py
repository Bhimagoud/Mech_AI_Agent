"""
Agent 2: Department Mission Deconstructor
-----------------------------------------
Responsibility:
  Accept a list of Department Mission (DM) statements and return a
  structured JSON object that maps each DM ID to its deconstructed
  objective components — mirroring the same dimensions used for PEOs
  so that Agent 3 can perform aligned semantic comparison.

RAG-enhanced: Retrieves relevant mission/department context from the
indexed SAR document to ground the deconstruction in actual document content.
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

Your SOLE task is to deconstruct Department Mission (DM) statements into
their atomic objective components.  For each DM, identify:

1. industry_readiness     – preparing industry-ready graduates, employability
2. quality_education      – OBE, curriculum quality, teaching-learning process
3. cognitive_skills       – technical knowledge, problem-solving, analysis
4. non_cognitive_skills   – communication, teamwork, leadership, ethics
5. research_ecosystem     – research culture, innovation, R&D infrastructure
6. engineering_competency – depth of engineering specialisation, competency levels
7. multidisciplinary      – cross-domain exposure, interdisciplinary research
8. societal_impact        – sustainability, community, real-world challenges

Return ONLY a valid JSON object.  Schema:
{
  "DM1": {
    "industry_readiness": ["..."],
    "quality_education": ["..."],
    "cognitive_skills": ["..."],
    "non_cognitive_skills": ["..."],
    "research_ecosystem": ["..."],
    "engineering_competency": ["..."],
    "multidisciplinary": ["..."],
    "societal_impact": ["..."],
    "summary": "One-sentence summary of this mission statement's primary focus."
  },
  ...
}

Rules:
- Use the exact DM IDs provided as keys (e.g., "DM1", "DM2").
- Each list may be empty [] if that dimension is absent.
- Do NOT include explanation prose outside the JSON.
- Do NOT wrap output in markdown fences.
""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deconstruct_missions(missions: list) -> dict:
    """
    Args:
        missions: List of {"id": "DM1", "text": "..."} dicts.

    Returns:
        dict mapping DM ID → objective breakdown (parsed from LLM JSON).
    """
    if not missions:
        return {}

    dm_block = "\n\n".join(
        f"{m['id']}: {m['text']}" for m in missions
    )

    # ── RAG context injection ──────────────────────────────────────────────
    rag_context = ""
    if is_indexed():
        rag_context = retrieve_as_context(
            query="Department Mission statement education research industry competency",
            header="## SAR Document Context (retrieved via RAG)",
        )
        logger.info("Agent 2: RAG context injected (%d chars)", len(rag_context))

    user_message = f"""\
{rag_context + chr(10) if rag_context else ""}\
Deconstruct the following Department Mission statements:

{dm_block}

Return the JSON object as described in your instructions.
""".strip()

    logger.info("Agent 2 (Mission Deconstructor): Processing %d DMs", len(missions))
    raw_response = call_llm(_SYSTEM_PROMPT, user_message, temperature=0.0)
    result = _parse_json_response(raw_response, context="Mission deconstruction")

    logger.info("Agent 2: Deconstruction complete for keys: %s", list(result.keys()))
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str, context: str = "") -> dict:
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
        cleaned = text[start_idx:end_idx+1]
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in %s: %s\nRaw:\n%s", context, exc, text[:500])
            return {}
    else:
        logger.error("No JSON braces found in %s response.\nRaw:\n%s", context, text[:500])
        return {}
