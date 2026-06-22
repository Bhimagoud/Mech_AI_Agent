"""
Agent 3: Correlation Scorer
----------------------------
Responsibility:
  Cross-reference every PEO against every DM using the enriched
  deconstructions from Agents 1 & 2, then assign a correlation score
  (1, 2, 3 or "-") per the NBA rubric, plus a 2-sentence justification
  for every non-zero mapping.

RAG-enhanced: Retrieves scoring-rubric and correlation-related document
sections from the indexed SAR to ground the scoring in actual accreditation
language used in the institution's own document.

Output Schema (JSON):
{
  "matrix": {
    "PEO1": {"DM1": 3, "DM2": 2, "DM3": 1},
    "PEO2": {"DM1": "-", "DM2": 3, "DM3": 2},
    ...
  },
  "justifications": {
    "PEO1_DM1": {"score": 3, "text": "Sentence 1. Sentence 2."},
    ...
  }
}
"""

import json
import logging
import re

from services.llm_router import call_llm
from services.rag_service import retrieve_as_context, is_indexed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — the full rubric is embedded here
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are an elite NBA (National Board of Accreditation) Mapping & Consistency
Analyst and a recognised expert in Outcome-Based Education (OBE) aligned with
the Washington Accord frameworks.

## SCORING RUBRIC (STRICT ENFORCEMENT)
- Level 3 (Substantial/High): Direct semantic overlap and strong pedagogical
  alignment. The PEO directly and explicitly fulfils the core element of the
  Mission statement.
- Level 2 (Moderate/Medium): Indirect or partial support. The PEO contributes
  to the Mission, but as a secondary rather than primary outcome.
- Level 1 (Slight/Low): Tangential support. Foundational knowledge that might
  marginally assist the Mission, but lacks explicit alignment.
- "-" (No Correlation): Concepts are entirely unrelated.

## JUSTIFICATION RULES
For every mapping scored 1, 2, or 3:
- Sentence 1 (Anchor): Identify the specific keywords/concepts in the PEO
  that overlap with the specific keywords/concepts in the DM.
- Sentence 2 (Synthesis): Explain how achieving this PEO structurally
  supports the realisation of that Mission from an OBE perspective.

## OUTPUT FORMAT — RETURN ONLY VALID JSON
{
  "matrix": {
    "<PEO_ID>": {
      "<DM_ID>": <integer 1/2/3 or string "-">,
      ...
    },
    ...
  },
  "justifications": {
    "<PEO_ID>_<DM_ID>": {
      "score": <integer>,
      "text": "<Sentence 1>. <Sentence 2>."
    },
    ...
  }
}

Rules:
- Use exact IDs from the input (e.g., "PEO1", "DM2").
- Every non-"-" score MUST have a justification entry.
- "-" scores do NOT need justification entries.
- Do NOT include prose outside the JSON.
- Do NOT wrap in markdown fences.
""".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_correlations(
    peos: list,
    missions: list,
    peo_breakdown: dict,
    mission_breakdown: dict,
) -> dict:
    """
    Args:
        peos:              Raw PEO list [{"id": "PEO1", "text": "..."}, ...]
        missions:          Raw DM list  [{"id": "DM1",  "text": "..."}, ...]
        peo_breakdown:     Output of Agent 1 – enriched PEO decompositions
        mission_breakdown: Output of Agent 2 – enriched DM decompositions

    Returns:
        dict with "matrix" and "justifications" keys.
    """
    if not peos or not missions:
        return {"matrix": {}, "justifications": {}}

    # ── RAG context injection ──────────────────────────────────────────────
    rag_context = ""
    if is_indexed():
        rag_context = retrieve_as_context(
            query="correlation scoring rubric PEO mission alignment NBA accreditation",
            header="## SAR Document Context for Scoring (retrieved via RAG)",
        )
        logger.info("Agent 3: RAG context injected (%d chars)", len(rag_context))

    user_message = _build_user_message(
        peos, missions, peo_breakdown, mission_breakdown, rag_context
    )

    logger.info(
        "Agent 3 (Scorer): Scoring %d PEOs x %d DMs", len(peos), len(missions)
    )
    raw_response = call_llm(_SYSTEM_PROMPT, user_message, temperature=0.15)
    result = _parse_json_response(raw_response)

    matrix         = result.get("matrix", {})
    justifications = result.get("justifications", {})
    logger.info(
        "Agent 3: Matrix produced for %d PEOs; %d justifications",
        len(matrix), len(justifications),
    )
    return result


# ---------------------------------------------------------------------------
# Message builder
# ---------------------------------------------------------------------------

def _build_user_message(
    peos: list,
    missions: list,
    peo_breakdown: dict,
    mission_breakdown: dict,
    rag_context: str = "",
) -> str:
    sections = []

    if rag_context:
        sections.append(rag_context)
        sections.append("")

    sections.append("## PEOs (Raw + Breakdown)\n")
    for p in peos:
        pid = p["id"]
        breakdown = peo_breakdown.get(pid, {})
        sections.append(f"### {pid}")
        sections.append(f"Text: {p['text']}")
        if breakdown:
            sections.append(f"Breakdown: {json.dumps(breakdown, ensure_ascii=False)}")
        sections.append("")

    sections.append("## Department Mission Statements (Raw + Breakdown)\n")
    for m in missions:
        mid = m["id"]
        breakdown = mission_breakdown.get(mid, {})
        sections.append(f"### {mid}")
        sections.append(f"Text: {m['text']}")
        if breakdown:
            sections.append(f"Breakdown: {json.dumps(breakdown, ensure_ascii=False)}")
        sections.append("")

    sections.append(
        "Perform the full PEO x DM cross-referencing and return the JSON object."
    )
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Agent 3 JSON parse error: %s\nRaw:\n%s", exc, text[:800])
        return {"matrix": {}, "justifications": {}}
