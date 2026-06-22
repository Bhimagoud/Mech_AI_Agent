"""
Agent 4: Report Formatter
--------------------------
Responsibility:
  Consume the raw scoring output from Agent 3 and produce two artefacts:
    1. A structured dict suitable for JSON API responses & frontend rendering.
    2. A clean Markdown report matching the NBA SAR format exactly.

This agent does NOT call the LLM – it is a deterministic formatting service.
"""

import logging
from statistics import mean

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_report(
    peos: list,
    missions: list,
    scoring_output: dict,
    source_file: str = "",
) -> dict:
    """
    Args:
        peos:           [{"id": "PEO1", "text": "..."}, ...]
        missions:       [{"id": "DM1",  "text": "..."}, ...]
        scoring_output: {"matrix": {...}, "justifications": {...}}
        source_file:    Original filename for report header.

    Returns:
        {
            "matrix_table":  list of dicts (rows) for frontend table rendering,
            "averages":       {"PEO1": 2.33, ...},
            "justifications": list of formatted justification objects,
            "markdown":       str (full NBA-format Markdown report),
            "summary_stats":  {"total_pairs": N, "avg_overall": X.XX, ...}
        }
    """
    matrix = scoring_output.get("matrix", {})
    raw_just = scoring_output.get("justifications", {})
    dm_ids = [m["id"] for m in missions]
    peo_ids = [p["id"] for p in peos]

    # --- Build matrix table rows ---
    matrix_rows, averages = _build_matrix_table(peo_ids, dm_ids, matrix)

    # --- Format justifications ---
    just_list = _format_justifications(raw_just, peos, missions)

    # --- Summary stats ---
    numeric_scores = [
        v for row in matrix.values()
        for v in row.values()
        if isinstance(v, int)
    ]
    summary = {
        "total_peos": len(peo_ids),
        "total_dms": len(dm_ids),
        "total_pairs": len(peo_ids) * len(dm_ids),
        "mapped_pairs": len(numeric_scores),
        "avg_overall": round(mean(numeric_scores), 2) if numeric_scores else 0,
        "high_correlations": sum(1 for s in numeric_scores if s == 3),
        "medium_correlations": sum(1 for s in numeric_scores if s == 2),
        "low_correlations": sum(1 for s in numeric_scores if s == 1),
        "no_correlations": len(peo_ids) * len(dm_ids) - len(numeric_scores),
    }

    # --- Markdown report ---
    markdown = _build_markdown(
        peos, missions, matrix_rows, dm_ids, just_list, summary, source_file
    )

    return {
        "matrix_table": matrix_rows,
        "averages": averages,
        "justifications": just_list,
        "markdown": markdown,
        "summary_stats": summary,
        "dm_ids": dm_ids,
        "peo_ids": peo_ids,
    }


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_matrix_table(peo_ids, dm_ids, matrix):
    rows = []
    averages = {}

    for pid in peo_ids:
        row = {"peo_id": pid, "scores": {}}
        numeric = []
        for did in dm_ids:
            score = matrix.get(pid, {}).get(did, "-")
            row["scores"][did] = score
            if isinstance(score, int):
                numeric.append(score)
        avg = round(mean(numeric), 2) if numeric else "-"
        row["average"] = avg
        averages[pid] = avg
        rows.append(row)

    return rows, averages


def _format_justifications(raw_just: dict, peos: list, missions: list) -> list:
    peo_map = {p["id"]: p["text"] for p in peos}
    dm_map = {m["id"]: m["text"] for m in missions}
    results = []

    for key, val in raw_just.items():
        # key format: "PEO1_DM2"
        parts = key.split("_")
        if len(parts) != 2:
            continue
        pid, did = parts
        results.append({
            "key": key,
            "peo_id": pid,
            "dm_id": did,
            "score": val.get("score", "?"),
            "text": val.get("text", ""),
            "peo_text": peo_map.get(pid, ""),
            "dm_text": dm_map.get(did, ""),
        })

    # Sort by PEO then DM
    results.sort(key=lambda x: (
        int("".join(filter(str.isdigit, x["peo_id"])) or "0"),
        int("".join(filter(str.isdigit, x["dm_id"])) or "0"),
    ))
    return results


def _build_markdown(peos, missions, matrix_rows, dm_ids, just_list, summary, source):
    lines = []

    lines.append("# NBA SAR — PEO ↔ Department Mission Mapping")
    if source:
        lines.append(f"\n**Source:** {source}")
    lines.append("")

    # --- Section 1: Matrix ---
    lines.append("## SECTION 1: Correlation Matrix\n")

    # Header row
    header = "| PEO | " + " | ".join(dm_ids) + " | **Average** |"
    sep = "|-----|" + "------|" * len(dm_ids) + "-------------|"
    lines.append(header)
    lines.append(sep)

    for row in matrix_rows:
        cells = [row["scores"].get(did, "-") for did in dm_ids]
        avg = row["average"]
        row_str = (
            f"| **{row['peo_id']}** | "
            + " | ".join(str(c) for c in cells)
            + f" | **{avg}** |"
        )
        lines.append(row_str)

    lines.append("")
    lines.append(
        "_Note: 1 = Slight (Low) | 2 = Moderate (Medium) | "
        "3 = Substantial (High) | - = No Correlation_"
    )
    lines.append("")

    # --- Section 2: Justifications ---
    lines.append("## SECTION 2: Pedagogical Justifications\n")
    for j in just_list:
        lines.append(
            f"- **{j['peo_id']} - {j['dm_id']} (Score: {j['score']}):** {j['text']}"
        )
    lines.append("")

    # --- Summary ---
    lines.append("## SECTION 3: Summary Statistics\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total PEOs | {summary['total_peos']} |")
    lines.append(f"| Total DMs | {summary['total_dms']} |")
    lines.append(f"| Total PEO–DM Pairs | {summary['total_pairs']} |")
    lines.append(f"| Mapped Pairs | {summary['mapped_pairs']} |")
    lines.append(f"| Unmapped (–) Pairs | {summary['no_correlations']} |")
    lines.append(f"| High Correlations (3) | {summary['high_correlations']} |")
    lines.append(f"| Moderate Correlations (2) | {summary['medium_correlations']} |")
    lines.append(f"| Low Correlations (1) | {summary['low_correlations']} |")
    lines.append(f"| Overall Average Score | **{summary['avg_overall']}** |")

    return "\n".join(lines)
